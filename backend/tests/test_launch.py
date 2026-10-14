"""Deployment-specific regression checks, sharing API test settings and database."""
from tests.test_api import account, client  # noqa: E402


def test_r2_presigned_video_only_after_entitlement(monkeypatch):
    from app import main
    h=account()
    monkeypatch.setenv('VIDEO_STORAGE','r2')
    monkeypatch.setattr(main.object_storage,'exists',lambda filename:True)
    monkeypatch.setattr(main.object_storage,'presign',lambda filename: 'https://example.r2.cloudflarestorage.com/signed/'+filename)
    r=client.post('/v1/episodes/the-last-promise-1/play',headers=h)
    assert r.status_code==200
    assert r.json()['url'].startswith('https://example.r2.cloudflarestorage.com/signed/')
    assert client.post('/v1/episodes/the-last-promise-9/play',headers=h).status_code==402


def test_r2_missing_video_returns_not_ready(monkeypatch):
    from app import main
    monkeypatch.setenv('VIDEO_STORAGE','r2')
    monkeypatch.setattr(main.object_storage,'exists',lambda filename:False)
    r=client.post('/v1/episodes/the-last-promise-1/play',headers=account())
    assert r.status_code==200 and r.json()['ready'] is False


def test_google_play_v2_only_purchased_single_pack(monkeypatch):
    from app import main
    monkeypatch.setattr(main,'PAYMENT_MODE','play')
    monkeypatch.setenv('GOOGLE_PLAY_PACKAGE','com.kisastream.kisa_stream')
    monkeypatch.setenv('GOOGLE_PLAY_PRODUCT_ID','coins_30_tzs_1000')
    data={'productLineItem':[{'productId':'coins_30_tzs_1000','quantity':1}],
          'purchaseStateContext':{'purchaseState':'PENDING'}}
    monkeypatch.setattr(main,'fetch_google_purchase',lambda pkg,token:data)
    h=account()
    body={'product_id':'coins_30_tzs_1000','purchase_token':'validtokenpending'}
    assert client.post('/v1/billing/play/verify',json=body,headers=h).status_code==402
    assert client.get('/v1/me',headers=h).json()['balance']==0
    data['purchaseStateContext']['purchaseState']='PURCHASED'
    first=client.post('/v1/billing/play/verify',json=body,headers=h)
    assert first.status_code==200 and first.json()['credited'] is True
    repeated=client.post('/v1/billing/play/verify',json=body,headers=h)
    assert repeated.status_code==200 and repeated.json()['credited'] is False
    assert client.get('/v1/me',headers=h).json()['balance']==30
    assert client.post('/v1/billing/play/verify',json=body,headers=account()).status_code==409


def test_dual_mode_only_credits_verified_clickpesa(monkeypatch):
    from app import main
    monkeypatch.setattr(main,'PAYMENT_MODE','play,clickpesa')
    monkeypatch.setattr(main.clickpesa,'create_checkout',lambda pid,amt,uid,url:('https://secure.clickpesa.com/pay','order-ref'))
    h=account()
    response=client.post('/v1/payments',headers=h)
    assert response.status_code==200,response.text
    p=response.json()
    assert p['provider']=='clickpesa'
    assert client.get('/v1/me',headers=h).json()['balance']==0
    monkeypatch.setattr(main.clickpesa,'verify_order',lambda pid,oid,amt:None)
    assert client.post(f"/v1/payments/{p['id']}/refresh",headers=h).json()['status']=='pending'
    assert client.get('/v1/me',headers=h).json()['balance']==0
    monkeypatch.setattr(main.clickpesa,'verify_order',lambda pid,oid,amt:'clickpesa:test-ref')
    assert client.post(f"/v1/payments/{p['id']}/refresh",headers=h).json()['credited'] is True
    assert client.post(f"/v1/payments/{p['id']}/refresh",headers=h).json()['credited'] is False
    assert client.get('/v1/me',headers=h).json()['balance']==30


def test_video_upload_uses_r2_and_not_ephemeral_disk(monkeypatch):
    from pathlib import Path
    from app import main
    monkeypatch.setenv('VIDEO_STORAGE','r2')
    received=[]
    monkeypatch.setattr(main.object_storage,'upload',lambda path,name: received.append((name,Path(path).stat().st_size)))
    sample=(Path(__file__).resolve().parents[1]/'data/videos/sample.mp4').read_bytes()
    admin_headers={'X-Admin-Key':main.ADMIN_KEY}
    r=client.put('/v1/admin/episodes/borrowed-heart-2/video',headers=admin_headers,
                 files={'video':('episode-02.mp4',sample,'video/mp4')})
    assert r.status_code==200,r.text
    assert received==[(r.json()['filename'],len(sample))]
    assert not (main.VIDEO_DIR/r.json()['filename']).exists()
