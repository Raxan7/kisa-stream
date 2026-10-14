#!/usr/bin/env python3
"""Read-only & disposable-guest smoke checks for a public KISA API."""
import json
import os
import sys
import urllib.error
import urllib.request

api=os.getenv('KISA_API','').rstrip('/')
if not api.startswith('https://'):
    print('Set KISA_API=https://your-service.onrender.com',file=sys.stderr)
    sys.exit(2)


def request(method,path,token=None):
    headers={'Accept':'application/json'}
    body=None
    if method=='POST':
        body=b'{}'
        headers['Content-Type']='application/json'
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(api+path, data=body,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=90) as r:
        return r.status,json.load(r)


try:
    health=request('GET','/health')[1]
    assert health.get('ok') is True
    print('[OK] API /health:',health)
    guest=request('POST','/v1/auth/guest')[1]
    token=guest['access_token']
    assert request('GET','/v1/me',token)[1]['balance']==0
    print('[OK] Guest identity, zero starting coins')
    shows=request('GET','/v1/shows')[1]['items']
    print('[OK] Series:',len(shows))
    if shows:
        details=request('GET','/v1/shows/'+shows[0]['id'],token)[1]
        episodes=details['episodes']
        assert all(ep['is_free'] for ep in episodes if ep['number']<=8)
        assert all(ep['cost_coins']==10 for ep in episodes if ep['number']>8)
        print('[OK] First eight free; later episodes cost 10 coins')
        if episodes:
            first=request('POST','/v1/episodes/'+episodes[0]['id']+'/play',token)[1]
            print('[OK] First episode ready:',first.get('ready'))
            if not first.get('ready'):
                print('[ACTION] Upload an MP4 to this episode')
        if len(episodes)>8:
            try:
                request('POST','/v1/episodes/'+episodes[8]['id']+'/play',token)
                raise RuntimeError('Expected episode 9 to be locked')
            except urllib.error.HTTPError as exc:
                assert exc.code==402,f'Expected 402, got {exc.code}'
                print('[OK] Episode 9 paywall enforced')
    else:
        print('[ACTION] Empty catalogue: publish your first movie')
    print('PASS: public API smoke checks (payments not tested)')
except Exception as exc:
    print('FAIL:',str(exc),file=sys.stderr)
    sys.exit(1)
