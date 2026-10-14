"""KISA Studio bulk upload and publishing safety regressions."""
import pytest
from tests.test_api import client

ADMIN_PASSWORD = 'a-secure-long-test-admin-password-24'

@pytest.fixture(autouse=True)
def clean_cookies():
    client.cookies.clear()
    yield
    client.cookies.clear()


def auth(monkeypatch):
    from app import main
    import jwt
    monkeypatch.setenv('ADMIN_DASHBOARD_PASSWORD',ADMIN_PASSWORD)
    result=client.post('/admin/login', data={'password':ADMIN_PASSWORD}, follow_redirects=False)
    assert result.status_code==303
    cookie=result.cookies
    claim=jwt.decode(cookie['kisa_admin_session'],main.JWT_SECRET,algorithms=['HS256'],audience='kisa-app')
    return cookie,claim['csrf']


def data(name='01-intro.mp4'):
    return {'filename':name,'size_bytes':450_000,'title':'Intro','duration_seconds':77}


def post(cookie,csrf,body):
    return client.post('/admin/bulk/prepare',cookies=cookie, headers={'X-CSRF-Token':csrf},json=body)


def test_batch_requires_session_and_csrf(monkeypatch):
    body={'slug':'borrowed-heart','start_number':1,'files':[data()], 'replace_unlinked':True}
    assert client.post('/admin/bulk/prepare',json=body).status_code==401
    cookie,csrf=auth(monkeypatch)
    assert post(cookie,'bad',body).status_code==403
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anonymous:
        assert anonymous.get('/admin/assets/automation.js').status_code==401
    assert client.get('/admin/assets/automation.js',cookies=cookie).status_code==200
    assert client.get('/admin/assets/automation.css',cookies=cookie).status_code==200


def test_bulk_new_movie_atomic_creation(monkeypatch):
    from app import main
    cookie,csrf=auth(monkeypatch)
    body={'slug':'weekend-plot','create_series':True,'series_title':'Weekend Plot',
          'synopsis':'A very strange weekend changes every friendship.', 'genre':'Thriller',
          'start_number':1,'files':[data('001.mp4'),data('002.mp4')]}
    r=post(cookie,csrf,body)
    assert r.status_code==200,r.text
    assert [x['number'] for x in r.json()['items']]==[1,2]
    with main.SessionLocal() as db:
        show=db.get(main.Show,'weekend-plot')
        assert show is not None and not show.is_published
        assert db.get(main.Episode,'weekend-plot-1').is_published is False
        assert db.get(main.Episode,'weekend-plot-2').bunny_video_id is None


def test_reusing_seeded_placeholders_requires_explicit_consent(monkeypatch):
    from app import main
    cookie,csrf=auth(monkeypatch)
    body={'slug':'borrowed-heart','start_number':1,'files':[data()]}
    denied=post(cookie,csrf,body)
    assert denied.status_code==409
    with main.SessionLocal() as db:
        assert db.get(main.Episode,'borrowed-heart-1').is_published
    body['replace_unlinked']=True
    changed=post(cookie,csrf,body)
    assert changed.status_code==200,changed.text
    assert changed.json()['items'][0]['action']=='placeholder-reused'
    with main.SessionLocal() as db:
        ep=db.get(main.Episode,'borrowed-heart-1')
        assert not ep.is_published and ep.title=='Intro'
        assert db.get(main.Episode,'borrowed-heart-2').is_published
    with main.writing() as db:
        ep=db.get(main.Episode,'borrowed-heart-1')
        ep.is_published=True
        ep.title='The Unexpected Meeting'
        ep.duration_seconds=75


def test_existing_live_video_not_overwritten_and_batch_rollback(monkeypatch):
    from app import main
    cookie,csrf=auth(monkeypatch)
    existing_id='6a311d1e-02e2-4b12-8b50-4cfbe2a0276f'
    with main.writing() as db:
        ep=db.get(main.Episode,'borrowed-heart-4')
        old=ep.bunny_video_id
        ep.bunny_video_id=existing_id
    try:
        body={'slug':'borrowed-heart','start_number':3,'files':[data('03.mp4'),data('04.mp4')], 'replace_unlinked':True}
        response=post(cookie,csrf,body)
        assert response.status_code==409,response.text
        with main.SessionLocal() as db:
            # No partial mutation of episode 3 if episode 4 is protected.
            assert db.get(main.Episode,'borrowed-heart-3').is_published
            assert db.get(main.Episode,'borrowed-heart-4').bunny_video_id==existing_id
    finally:
        with main.writing() as db:db.get(main.Episode,'borrowed-heart-4').bunny_video_id=old


def test_input_validation(monkeypatch):
    cookie,csrf=auth(monkeypatch)
    for item in [dict(data(),filename='../bad.mp4'),dict(data(),size_bytes=0),dict(data(),size_bytes=1024**3+1)]:
        r=post(cookie,csrf,{'slug':'borrowed-heart','start_number':20,'files':[item]})
        assert r.status_code==422,r.text
    assert post(cookie,csrf,{'slug':'bad/name','files':[data()]}).status_code==422
    assert post(cookie,csrf,{'slug':'borrowed-heart','start_number':10001,'files':[data()]}).status_code==422


def test_batch_publishes_only_ready_bunny_assets(monkeypatch):
    from app import main, bunny_stream
    cookie,csrf=auth(monkeypatch)
    ready='63b102ca-65c0-4d38-9e0c-c0fc32ddc4f1'
    processing='955df4df-ea88-4f76-bcd7-4d4b0edc9f6f'
    with main.writing() as db:
        ep1=db.get(main.Episode,'midnight-heir-1')
        ep2=db.get(main.Episode,'midnight-heir-2')
        old1=(ep1.bunny_video_id,ep1.is_published)
        old2=(ep2.bunny_video_id,ep2.is_published)
        ep1.bunny_video_id=ready;ep1.is_published=False
        ep2.bunny_video_id=processing;ep2.is_published=False
    monkeypatch.setattr(bunny_stream,'status',lambda id:{'status':4 if id==ready else 2})
    try:
        r=client.post('/admin/bulk/publish-ready',json={'slug':'midnight-heir'},cookies=cookie,headers={'X-CSRF-Token':csrf})
        assert r.status_code==200,r.text
        assert 'midnight-heir-1' in r.json()['published']
        assert 'midnight-heir-2' in r.json()['waiting']
        with main.SessionLocal() as db:
            assert db.get(main.Episode,'midnight-heir-1').is_published
            assert not db.get(main.Episode,'midnight-heir-2').is_published
        # Idempotent re-run cannot publish the still-processing episode.
        second=client.post('/admin/bulk/publish-ready',json={'slug':'midnight-heir'},cookies=cookie,headers={'X-CSRF-Token':csrf})
        assert second.status_code==200 and second.json()['published']==[]
    finally:
        with main.writing() as db:
            ep1=db.get(main.Episode,'midnight-heir-1');ep1.bunny_video_id,ep1.is_published=old1
            ep2=db.get(main.Episode,'midnight-heir-2');ep2.bunny_video_id,ep2.is_published=old2


def test_admin_ui_reports_missing_bunny_video(monkeypatch):
    cookie,csrf=auth(monkeypatch)
    page=client.get('/admin',cookies=cookie)
    assert page.status_code==200
    assert 'Upload episodes' in page.text
    assert 'Missing video' in page.text
    assert 'Publish ready drafts' in page.text
    assert 'automation.js' in page.text
