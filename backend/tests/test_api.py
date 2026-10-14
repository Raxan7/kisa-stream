import os
import tempfile
from pathlib import Path

DB = Path(tempfile.mkdtemp(prefix='kisa_tests_')) / 'tests.db'
os.environ['DATABASE_URL'] = f'sqlite:///{DB}'
os.environ['JWT_SECRET'] = 'test-secret-64-characters-secret-64-characters-very-long'
os.environ['ADMIN_API_KEY'] = 'admin-secret-64-characters-admin-secret-64-characters-long'
os.environ['DEMO_ADMIN_KEY'] = 'some-other-demo-secret'
os.environ['PAYMENT_MODE'] = 'demo'
os.environ['DEMO_MODE'] = 'true'

from fastapi.testclient import TestClient
from app.main import app, SessionLocal, Payment

client = TestClient(app)

def account():
    tok=client.post('/v1/auth/guest').json()['access_token']
    return {'Authorization':f'Bearer {tok}'}

def bootstrap():
    headers=account()
    show=client.get('/v1/shows/the-last-promise',headers=headers).json()
    return headers, show

def test_health_and_catalog():
    r=client.get('/health');assert r.status_code==200
    a=client.get('/v1/shows').json()['items'];assert len(a)>=3

def test_first_eight_are_free_and_ninth_locked():
    h,s=bootstrap();eps=s['episodes']
    assert len(eps)==12
    assert all(ep['is_free'] and ep['is_unlocked'] for ep in eps[:8])
    assert eps[8]['is_free'] is False and eps[8]['cost_coins']==10
    assert client.post(f"/v1/episodes/{eps[7]['id']}/play",headers=h).json()['ready'] is True
    assert client.post(f"/v1/episodes/{eps[8]['id']}/play",headers=h).status_code==402
    assert client.post(f"/v1/episodes/{eps[8]['id']}/unlock",headers=h).status_code==402

def test_demo_topup_unlock_idempotent_and_balance():
    h,s=bootstrap();eid=s['episodes'][8]['id']
    assert client.post('/v1/dev/me/demo-topup',headers=h).json()['balance']==30
    a=client.post(f'/v1/episodes/{eid}/unlock',headers=h).json()
    assert a['balance']==20 and a['spent']==10
    b=client.post(f'/v1/episodes/{eid}/unlock',headers=h).json()
    assert b['balance']==20 and b['spent']==0
    assert client.get('/v1/me',headers=h).json()['balance']==20
    assert client.get('/v1/shows/the-last-promise',headers=h).json()['episodes'][8]['is_unlocked']
    assert client.post(f'/v1/episodes/{eid}/play',headers=h).status_code==200
    entries=client.get('/v1/wallet',headers=h).json()['entries']
    assert len([e for e in entries if e['kind']=='episode'])==1

def test_progress_cannot_skip_a_locked_episode():
    h,s=bootstrap();sid=s['id']
    assert client.post(f'/v1/shows/{sid}/progress',headers=h,json={'episode_number':9}).status_code==402
    assert client.post(f'/v1/shows/{sid}/progress',headers=h,json={'episode_number':8}).status_code==200
    saved=client.get('/v1/library',headers=h).json()['continue_watching']
    assert saved[0]['episode_number']==8

def test_media_range_and_signed_access():
    h,s=bootstrap();eid=s['episodes'][0]['id']
    url=client.post(f'/v1/episodes/{eid}/play',headers=h).json()['url']
    path=url.replace('http://127.0.0.1:8000','')
    a=client.get(path,headers={'Range':'bytes=0-99'})
    assert a.status_code==206 and len(a.content)==100 and a.headers['accept-ranges']=='bytes'
    assert client.get(path,headers={'Range':'bytes=999999999-'}).status_code==416
    assert client.get(f'/v1/media/{eid}?ticket=invalid').status_code==401
    other=client.get(path.replace(eid,'borrowed-heart-1'))
    assert other.status_code==401

def test_payment_cannot_credit_from_creation_or_unauthorized_settlement():
    h=account()
    p=client.post('/v1/payments',headers=h).json()
    assert p['status']=='pending'
    assert client.get('/v1/me',headers=h).json()['balance']==0
    url=f"/v1/dev/payments/{p['id']}/settle"
    assert client.post(url).status_code==403
    assert client.post(url,headers={'X-Admin-Key':os.environ['ADMIN_API_KEY']}).status_code==403
    keys={'X-Admin-Key':os.environ['ADMIN_API_KEY'],'X-Demo-Key':os.environ['DEMO_ADMIN_KEY']}
    assert client.post(url,headers=keys).json()['credited'] is True
    assert client.post(url,headers=keys).json()['credited'] is False
    assert client.get('/v1/me',headers=h).json()['balance']==30
    assert client.get(f"/v1/payments/{p['id']}",headers=account()).status_code==404

def test_concurrent_unlock_does_not_double_debit():
    from concurrent.futures import ThreadPoolExecutor
    h,s=bootstrap();e=s['episodes'][8]['id']
    client.post('/v1/dev/me/demo-topup',headers=h)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:client.post(f'/v1/episodes/{e}/unlock',headers=h),range(8)))
    assert all(r.status_code==200 for r in results)
    assert sum(r.json()['spent'] for r in results)==10
    assert client.get('/v1/me',headers=h).json()['balance']==20

def test_unauthenticated_denied_and_saved_toggle():
    assert client.get('/v1/me').status_code==401
    h,s=bootstrap();sid=s['id']
    assert client.post(f'/v1/shows/{sid}/favourite',headers=h).json()['favourite'] is True
    assert len(client.get('/v1/library',headers=h).json()['saved'])==1
    assert client.post(f'/v1/shows/{sid}/favourite',headers=h).json()['favourite'] is False
    assert len(client.get('/v1/library',headers=h).json()['saved'])==0

def test_admin_requires_key_and_valid_video_name():
    payload={'id':'my-series','title':'New Movie','synopsis':'Some thrilling story arc.','genre':'Drama'}
    assert client.post('/v1/admin/shows',json=payload).status_code==403
    key={'X-Admin-Key':os.environ['ADMIN_API_KEY']}
    assert client.post('/v1/admin/shows',json=payload,headers=key).status_code==200
    assert client.post('/v1/admin/shows',json=payload,headers=key).status_code==409
    invalid={'number':1,'title':'New Episode','duration_seconds':80,'filename':'../../etc/passwd.mp4'}
    assert client.post('/v1/admin/shows/my-series/episodes',json=invalid,headers=key).status_code==422
    valid={'number':1,'title':'New Episode','duration_seconds':80,'filename':'sample.mp4'}
    assert client.post('/v1/admin/shows/my-series/episodes',json=valid,headers=key).status_code==200

def test_admin_upload_real_video_and_range():
    import io
    h, s=bootstrap();eid=s['episodes'][0]['id']
    from app.main import VIDEO_DIR
    movie=(VIDEO_DIR/'sample.mp4').read_bytes()
    key={'X-Admin-Key':os.environ['ADMIN_API_KEY']}
    r=client.put(f'/v1/admin/episodes/{eid}/video',headers=key,
        files={'video':('episode.mp4',io.BytesIO(movie),'video/mp4')})
    assert r.status_code==200, r.text
    assert r.json()['duration_seconds']>=1
    assert client.post(f'/v1/episodes/{eid}/play',headers=h).json()['ready']
    # Restore sample video to reduce side-effects in other tests.
    from app.main import Episode, writing
    with writing() as db:
        db.get(Episode,eid).filename='sample.mp4'
    (VIDEO_DIR/r.json()['filename']).unlink(missing_ok=True)

def test_clickpass_payment_requires_provider_verified_settlement(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'PAYMENT_MODE','clickpass')
    monkeypatch.setattr(main.clickpass,'create_checkout',lambda pid,amt,uid,url:('https://checkout.example/pay','provider-abc'))
    h=account()
    result=client.post('/v1/payments',headers=h)
    assert result.status_code==200,result.text
    pid=result.json()['id']
    assert client.get('/v1/me',headers=h).json()['balance']==0
    monkeypatch.setattr(main.clickpass,'verify_order',lambda pid,ref,amt:None)
    assert client.post(f'/v1/payments/{pid}/refresh',headers=h).json()['status']=='pending'
    assert client.get('/v1/me',headers=h).json()['balance']==0
    monkeypatch.setattr(main.clickpass,'verify_order',lambda pid,ref,amt:'clickpass:unique-verified-123')
    a=client.post(f'/v1/payments/{pid}/refresh',headers=h)
    b=client.post(f'/v1/payments/{pid}/refresh',headers=h)
    assert a.status_code==200 and a.json()['credited'] is True
    assert b.status_code==200 and b.json()['credited'] is False
    assert client.get('/v1/me',headers=h).json()['balance']==30
