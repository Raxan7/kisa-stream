"""Admin flow: browser TUS upload is authorized and Stream credentials remain secret."""
import hashlib
import jwt
from tests.test_api import client


def _login(monkeypatch, api):
    from app import main
    monkeypatch.setenv('ADMIN_DASHBOARD_PASSWORD', 'test-bunny-admin-password-strong-2026')
    r = api.post('/admin/login', data={'password': 'test-bunny-admin-password-strong-2026'}, follow_redirects=False)
    assert r.status_code == 303
    csrf = jwt.decode(r.cookies['kisa_admin_session'], main.JWT_SECRET,
                      algorithms=['HS256'], audience='kisa-app')['csrf']
    return r.cookies, csrf


def test_tus_signature_uses_backend_secret_only(monkeypatch):
    from app import bunny_stream
    video = 'bbaa11aa-bbaa-4aaa-aaaa-aabbccddeeff'
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID', '54321')
    monkeypatch.setenv('BUNNY_STREAM_API_KEY', 'extremely-secret-library-upload-key')
    monkeypatch.setattr(bunny_stream.time, 'time', lambda: 1700000000)
    ticket = bunny_stream.tus_upload_ticket(video, ttl=3600)
    assert ticket['expires'] == 1700003600
    assert ticket['signature'] == hashlib.sha256(
        f'54321extremely-secret-library-upload-key1700003600{video}'.encode()).hexdigest()
    assert 'extremely-secret-library-upload-key' not in str(ticket)
    assert ticket['tus_endpoint'] == 'https://video.bunnycdn.com/tusupload'


def test_admin_upload_rbac_csrf_resumable_status_publish(monkeypatch):
    from app import main, bunny_stream
    from fastapi.testclient import TestClient
    api = TestClient(main.app)
    guid = 'bbaa11aa-bbaa-4aaa-aaaa-aabbccddeeff'
    calls=[]
    remote = {'status': 0, 'guid': guid, 'videoLibraryId': 54321, 'encodeProgress': 0}
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID', '54321')
    monkeypatch.setenv('BUNNY_STREAM_API_KEY', 'another-hidden-stream-api-key')
    monkeypatch.setattr(main, 'VIDEO_DELIVERY_MODE', 'bunny_stream', raising=False)
    monkeypatch.setattr(bunny_stream, 'create', lambda title: (calls.append(title) or {'guid': guid}))
    monkeypatch.setattr(bunny_stream, 'status', lambda _vid: remote.copy())
    with main.writing() as db:
        if db.get(main.Show, 'admin-upload-check') is None:
            db.add(main.Show(id='admin-upload-check', title='Bunny Upload Check',
                             synopsis='A nice long test synopsis for our story', genre='Drama', is_published=False))
        if db.get(main.Episode, 'admin-upload-check-1') is None:
            db.add(main.Episode(id='admin-upload-check-1', show_id='admin-upload-check', number=1,
                                title='First draft', duration_seconds=75, is_published=False))
    cookies, csrf = _login(monkeypatch, api)
    api.cookies.clear()  # Explicitly pass admin cookies only to authorized requests.
    data = {'episode_id':'admin-upload-check-1','filename':'first.mp4','size_bytes':1024}
    url='/admin/videos/bunny/start'
    assert api.post(url, json=data).status_code == 401
    assert api.post(url, cookies=cookies, headers={'X-CSRF-Token':'bad'},json=data).status_code == 403
    assert api.post(url, cookies=cookies, headers={'X-CSRF-Token':csrf},json={**data, 'filename':'../evil.mp4'}).status_code == 422
    assert api.post(url, cookies=cookies, headers={'X-CSRF-Token':csrf},json={**data, 'size_bytes':2**40}).status_code == 422
    started=api.post(url, cookies=cookies, headers={'X-CSRF-Token':csrf},json=data)
    assert started.status_code == 200, started.text
    assert started.json()['video_id'] == guid
    assert started.json()['signature']
    assert 'another-hidden-stream-api-key' not in started.text
    assert len(calls) == 1
    # Refreshing or resuming uses the same Bunny video, not a duplicate.
    resume=api.post(url, cookies=cookies,headers={'X-CSRF-Token':csrf},json=data)
    assert resume.status_code == 200 and resume.json()['video_id'] == guid and len(calls) == 1
    assert api.get('/admin/assets/bunny-upload.js').status_code == 200
    assert 'Upload to Bunny' in api.get('/admin', cookies=cookies).text
    assert api.get('/admin/videos/bunny/status/admin-upload-check-1').status_code == 401
    assert api.get('/admin/videos/bunny/preview/admin-upload-check-1').status_code == 401
    status=api.get('/admin/videos/bunny/status/admin-upload-check-1',cookies=cookies)
    assert status.status_code == 200 and status.json()['ready'] is False
    before=api.post('/admin/episodes/publish',cookies=cookies,
                       data={'episode':'admin-upload-check-1','publish':'1','csrf':csrf})
    assert before.status_code == 409
    assert api.get('/admin/videos/bunny/preview/admin-upload-check-1',cookies=cookies).status_code == 200
    remote['status']=4
    remote['encodeProgress']=100
    assert api.get('/admin/videos/bunny/status/admin-upload-check-1',cookies=cookies).json()['ready'] is True
    monkeypatch.setenv('BUNNY_STREAM_TOKEN_KEY', 'a-different-token-signing-secret')
    preview=api.get('/admin/videos/bunny/preview/admin-upload-check-1', cookies=cookies, follow_redirects=False)
    assert preview.status_code == 302
    assert preview.headers['location'].startswith('https://player.mediadelivery.net/embed/54321/')
    pub=api.post('/admin/episodes/publish', cookies=cookies,
                    data={'episode':'admin-upload-check-1','publish':'1','csrf':csrf},follow_redirects=False)
    assert pub.status_code == 303,pub.text
    denied=api.post(url,cookies=cookies,headers={'X-CSRF-Token':csrf},json=data)
    assert denied.status_code == 409
