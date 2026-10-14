"""KISA: expected Bunny processing is not a client error; actual failures remain errors."""
import jwt
import pytest
from tests.test_api import client


def login(monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'limit_auth_requests', lambda *a,**k: None)  # rate limit tested elsewhere
    pw = 'very-long-test-admin-password-processing'
    monkeypatch.setenv('ADMIN_DASHBOARD_PASSWORD',pw)
    r=client.post('/admin/login',data={'password':pw},follow_redirects=False)
    assert r.status_code==303
    cookies=r.cookies
    token=jwt.decode(cookies['kisa_admin_session'],main.JWT_SECRET,algorithms=['HS256'],audience='kisa-app')
    return cookies,token['csrf']


def make_episode(slug):
    from app import main
    with main.writing() as db:
        if not db.get(main.Show,slug):
            db.add(main.Show(id=slug,title='Automated publishing test',synopsis='Story to test video processing',is_published=False))
        if not db.get(main.Episode,f'{slug}-1'):
            db.add(main.Episode(id=f'{slug}-1',show_id=slug,number=1,title='Part One',is_published=False))


def test_missing_video_status_is_normal_and_assets_load(monkeypatch):
    cookies,csrf=login(monkeypatch)
    make_episode('processing-empty')
    r=client.get('/admin/videos/bunny/status/processing-empty-1',cookies=cookies)
    assert r.status_code==200 and r.json()['state']=='awaiting_upload'
    assert 'media-src' in client.get('/admin',cookies=cookies).headers['content-security-policy']
    assert 'blob:' in client.get('/admin',cookies=cookies).headers['content-security-policy']
    assert client.get('/favicon.ico').status_code==200
    assert client.get('/manifest.json').status_code==200


def test_pending_auto_publish_is_durable_and_idempotent(monkeypatch):
    from app import main,bunny_stream
    cookies,csrf=login(monkeypatch)
    guid='616f3ff8-2b2d-4e88-b21e-e01f240ad9e9'
    make_episode('processing-auto')
    with main.writing() as db:
        ep=db.get(main.Episode,'processing-auto-1')
        ep.bunny_video_id=guid
        ep.auto_publish_when_ready=True
    monkeypatch.setattr(bunny_stream,'status',lambda _id:{'status':2,'encodeProgress':33})
    r=client.get('/admin/videos/bunny/status/processing-auto-1',cookies=cookies)
    assert r.status_code==200 and r.json()['state']=='processing' and not r.json()['ready']
    with main.SessionLocal() as db:
        assert not db.get(main.Episode,'processing-auto-1').is_published
    preview=client.get('/admin/videos/bunny/preview/processing-auto-1',cookies=cookies)
    assert preview.status_code==200 and 'being processed' in preview.text
    monkeypatch.setattr(bunny_stream,'status',lambda _id:{'status':4,'encodeProgress':100})
    from app.admin_bulk import reconcile_auto_publish
    assert reconcile_auto_publish()>=1
    r=client.get('/admin/videos/bunny/status/processing-auto-1',cookies=cookies)
    assert r.status_code==200 and r.json()['ready'] and r.json()['published']
    with main.SessionLocal() as db:
        assert db.get(main.Episode,'processing-auto-1').is_published
        assert db.get(main.Show,'processing-auto').is_published
    assert reconcile_auto_publish()==0


def test_already_uploaded_returns_processing_not_409(monkeypatch):
    from app import main,bunny_stream
    cookies,csrf=login(monkeypatch)
    make_episode('processing-resume')
    guid='9bb0dfee-9a79-4d1b-8e30-5caf79910284'
    with main.writing() as db:
        db.get(main.Episode,'processing-resume-1').bunny_video_id=guid
    monkeypatch.setattr(main,'VIDEO_DELIVERY_MODE','bunny_stream',raising=False)
    monkeypatch.setattr(bunny_stream,'status',lambda vid:{'status':2})
    r=client.post('/admin/videos/bunny/start',cookies=cookies,headers={'X-CSRF-Token':csrf},json={
        'episode_id':'processing-resume-1','filename':'one.mp4','size_bytes':4096})
    assert r.status_code==200 and r.json()['state']=='processing'


def test_no_secret_in_bunny_provider_failures(monkeypatch):
    import httpx
    from app import bunny_stream
    monkeypatch.setenv('BUNNY_STREAM_API_KEY','should-remain-hidden-test-secret')
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID','54321')
    def fail(*args,**kwargs):
        resp=httpx.Response(401,request=httpx.Request('POST','https://video.bunnycdn.com/library/54321/videos'))
        raise httpx.HTTPStatusError('401',request=resp.request,response=resp)
    monkeypatch.setattr(bunny_stream.httpx,'request',fail)
    with pytest.raises(bunny_stream.BunnyError) as exc:
        bunny_stream.create('One movie')
    assert '401' in str(exc.value)
    assert 'should-remain-hidden' not in str(exc.value)
