"""PWA release tests: Bunny signature, gatekeeping, email login and verification."""
import hashlib
import time
from tests.test_api import account, client


def test_bunny_signature_matches_spec(monkeypatch):
    from app import bunny_stream
    guid='e49556cd-8870-457d-8d43-e4b6f546138b'
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID','123456')
    monkeypatch.setenv('BUNNY_STREAM_TOKEN_KEY','secret-signer')
    monkeypatch.setattr(bunny_stream.time,'time', lambda: 1_700_000_000)
    signed = bunny_stream.embed_url(guid)
    token=hashlib.sha256(f'secret-signer{guid}1700001200'.encode()).hexdigest()
    assert signed.startswith(f'https://player.mediadelivery.net/embed/123456/{guid}?')
    assert f'token={token}' in signed
    assert 'expires=1700001200' in signed
    assert not bunny_stream.valid_id('https://bad.example/')


def test_bunny_locked_episode_refuses_playback_even_when_ready(monkeypatch):
    from app import main
    guid='e49556cd-8870-457d-8d43-e4b6f546138b'
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID','1111')
    monkeypatch.setenv('BUNNY_STREAM_TOKEN_KEY','signing-secret')
    monkeypatch.setattr(main.bunny_stream,'status',lambda v: {'status':4})
    from app.main import Episode, writing
    with writing() as db:
        ep=db.get(Episode,'borrowed-heart-1'); before=ep.bunny_video_id; ep.bunny_video_id=guid
    try:
        guest=account()
        free=client.post('/v1/episodes/borrowed-heart-1/play',headers=guest)
        assert free.status_code==200,free.text
        assert free.json()['player_type']=='bunny_embed'
        locked=client.post('/v1/episodes/borrowed-heart-9/play',headers=guest)
        assert locked.status_code==402
    finally:
        with writing() as db:db.get(Episode,'borrowed-heart-1').bunny_video_id=before


def test_bunny_admin_video_link_validated_by_library(monkeypatch):
    from app import main
    guid='0eab70a2-9dc7-47a9-a1cd-4d691d5fa3be'
    monkeypatch.setenv('BUNNY_STREAM_LIBRARY_ID','5678')
    monkeypatch.setattr(main.bunny_stream,'status',lambda v: {
        'guid':v,'videoLibraryId':5678,'status':4})
    uri='/v1/admin/episodes/midnight-heir-2/bunny-link'
    assert client.post(uri,json={'video_id':guid}).status_code==403
    key={'X-Admin-Key':main.ADMIN_KEY}
    assert client.post(uri,headers=key,json={'video_id':'not-a-uuid'}).status_code==422
    res=client.post(uri,headers=key,json={'video_id':guid})
    assert res.status_code==200,res.text
    assert res.json()['ready'] is True
    from app.main import Episode, writing
    with writing() as db:db.get(Episode,'midnight-heir-2').bunny_video_id=None


def test_email_otp_invalid_code_attempts_are_persisted(monkeypatch):
    from app import main
    captured=[]
    monkeypatch.setattr(main.email_login,'send_code',lambda email,code:captured.append((email,code)))
    guest=account()
    email='episode-fan-otp@testing.example'
    started=client.post('/v1/auth/email/request',json={'email':email})
    assert started.status_code==200,started.text
    assert captured and len(captured[0][1])==6
    bad=client.post('/v1/auth/email/verify',headers=guest,json={'email':email,'code':'999999' if captured[0][1]!='999999' else '888888'})
    assert bad.status_code==400
    from app.main import EmailCode, SessionLocal
    with SessionLocal() as db:
        assert db.get(EmailCode,email).attempts==1
    valid=client.post('/v1/auth/email/verify',headers=guest,json={'email':email,'code':captured[0][1]})
    assert valid.status_code==200,valid.text
    assert valid.json()['user_id']==client.get('/v1/me',headers=guest).json()['user_id']
    token={'Authorization':'Bearer '+valid.json()['access_token']}
    assert client.get('/v1/me',headers=token).json()['email_verified'] is True


def test_code_request_rate_limit_and_missing_mail_provider(monkeypatch):
    from app import main
    captured=[]
    monkeypatch.setattr(main.email_login,'send_code',lambda email,code:captured.append(code))
    body={'email':'slow-down@testing.example'}
    assert client.post('/v1/auth/email/request',json=body).status_code==200
    assert client.post('/v1/auth/email/request',json=body).status_code==429


def test_no_production_payments_from_unverified_guest(monkeypatch):
    from app import main
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main,'PAYMENT_MODE','clickpesa')
    result=client.post('/v1/payments',headers=account())
    assert result.status_code==403


def test_admin_html_cookie_csrf_and_draft_publishing(monkeypatch):
    from app import main
    monkeypatch.setenv('ADMIN_DASHBOARD_PASSWORD','strong-very-long-admin-password-123456789')
    assert client.get('/admin').status_code==200
    assert 'password' in client.get('/admin').text
    assert client.post('/admin/login',data={'password':'wrong'}).status_code==403
    login=client.post('/admin/login',data={'password':'strong-very-long-admin-password-123456789'},
                      follow_redirects=False)
    assert login.status_code==303
    assert 'httponly' in login.headers['set-cookie'].lower()
    cookie=login.cookies
    from app.admin_web import _ctx
    from starlette.requests import Request
    # Decode cookie in isolated test; no password/token is embedded in web app.
    import jwt
    session=jwt.decode(cookie['kisa_admin_session'],main.JWT_SECRET,algorithms=['HS256'],audience='kisa-app')
    csrf=session['csrf']
    assert client.post('/admin/shows',cookies=cookie,
        data={'slug':'bad-series','title':'Broken','synopsis':'An adequate synopsis here',
              'genre':'Drama','csrf':'forged'}).status_code==403
    saved=client.post('/admin/shows',cookies=cookie,
        data={'slug':'great-series','title':'Great story','synopsis':'A truly exciting series synopsis',
              'genre':'Drama','csrf':csrf},follow_redirects=False)
    assert saved.status_code==303,saved.text
    with main.SessionLocal() as db:
        new=db.get(main.Show,'great-series')
        assert new is not None and new.is_published is False
    created=client.post('/admin/episodes',cookies=cookie,data={
        'slug':'great-series','number':'1','title':'A new episode',
        'duration':'75','csrf':csrf},follow_redirects=False)
    assert created.status_code==303,created.text
    assert client.post('/admin/episodes/publish',cookies=cookie,data={
        'episode':'great-series-1','publish':'1','csrf':csrf}).status_code==409


def test_verified_account_restores_to_new_device(monkeypatch):
    from app import main
    captured=[]
    monkeypatch.setattr(main.email_login,'send_code',lambda email,code:captured.append(code))
    first=account()
    email='restore-on-new-phone@testing.example'
    assert client.post('/v1/auth/email/request',json={'email':email}).status_code==200
    linked=client.post('/v1/auth/email/verify',headers=first,json={
        'email':email,'code':captured[-1]}).json()
    second=account()
    from app.main import EmailCode, writing
    with writing() as db:
        existing=db.get(EmailCode,email)
        if existing:existing.sent_at-=120
    assert client.post('/v1/auth/email/request',json={'email':email}).status_code==200
    restored=client.post('/v1/auth/email/verify',headers=second,json={
        'email':email,'code':captured[-1]}).json()
    assert restored['user_id']==linked['user_id']
