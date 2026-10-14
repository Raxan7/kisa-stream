#!/usr/bin/env python3
"""Publish a series and numbered episodes to KISA admin API.

Usage:
  KISA_API=https://your-api.onrender.com KISA_ADMIN_KEY=... \
    python3 scripts/publish_movie.py --id new-drama --title "New Drama" \
    --synopsis "A secret changes everything." --genre Romance \
    --videos ./episodes

Directory must contain 01.mp4, 02.mp4, ... in numeric order.
The backend verifies MP4 and ffprobe then pushes to R2 (if configured).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def curl_json(api, key, method, route, payload=None):
    cmd=['curl','--connect-timeout','15','--max-time','120','--fail-with-body','-sS',
         '-X',method,api.rstrip('/')+route,'-H','X-Admin-Key: '+key]
    if payload is not None:
        cmd += ['-H','Content-Type: application/json','--data-binary',json.dumps(payload)]
    result=subprocess.run(cmd, capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f'{route}: {result.stderr.strip()} {result.stdout[:300]}')
    return json.loads(result.stdout)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api',default=os.getenv('KISA_API'))
    parser.add_argument('--id',required=True)
    parser.add_argument('--title',required=True)
    parser.add_argument('--synopsis',required=True)
    parser.add_argument('--genre',default='Drama')
    parser.add_argument('--poster-url',default=None)
    parser.add_argument('--videos',type=Path,required=True)
    args=parser.parse_args()
    api=args.api
    key=os.getenv('KISA_ADMIN_KEY')
    if not api or not api.startswith('https://') or not key:
        parser.error('Set KISA_API to your HTTPS Render URL and KISA_ADMIN_KEY to the secret')
    if not re.fullmatch(r'[a-z0-9-]{3,48}',args.id):
        parser.error('--id must be a lowercase slug, e.g. secret-heir')
    clips=list(args.videos.glob('*.mp4'))
    numbers={}
    for path in clips:
        match=re.match(r'^(\d+)(?:[._ -]|$)',path.stem)
        if not match:
            parser.error(f'Video should begin with episode number: {path.name}')
        n=int(match.group(1))
        if n in numbers:
            parser.error(f'Duplicate episode number {n}')
        numbers[n]=path
    if not numbers:
        parser.error('No .mp4 clips found in --videos directory')
    if sorted(numbers)!=list(range(1,len(numbers)+1)):
        parser.error('Episode numbers must be consecutive from 1')
    print(f'Publishing {args.title!r} with {len(numbers)} episodes to {api}')
    try:
        result=curl_json(api,key,'POST','/v1/admin/shows',{
            'id':args.id,'title':args.title,'synopsis':args.synopsis,
            'genre':args.genre,'poster_url':args.poster_url})
        print('Series created:',result['id'])
    except RuntimeError as exc:
        if 'already exists' in str(exc):
            print('Series exists; resuming uploads')
        else:
            raise
    for num,path in sorted(numbers.items()):
        eid=f'{args.id}-{num}'
        try:
            curl_json(api,key,'POST',f'/v1/admin/shows/{args.id}/episodes',{
                'number':num,'title':path.stem.replace('_',' ').replace('-',' ')})
        except RuntimeError as exc:
            if 'already exists' not in str(exc):
                raise
        print(f'[{num}/{len(numbers)}] Uploading {path.name} ({path.stat().st_size//1024} KiB)')
        # Filename is local-only; raw MP4 goes over HTTPS to the admin-only route.
        cmd=['curl','--fail-with-body','-sS','--connect-timeout','20',
             '--max-time','900','-X','PUT',api.rstrip('/')+f'/v1/admin/episodes/{eid}/video',
             '-H','X-Admin-Key: '+key,'-F',f'video=@{path};type=video/mp4']
        r=subprocess.run(cmd,capture_output=True,text=True)
        if r.returncode:
            raise RuntimeError(f'Upload failed on episode {num}: {r.stderr} {r.stdout[:300]}')
        data=json.loads(r.stdout)
        print('   Saved:',data['filename'],'duration:',data['duration_seconds'],'seconds')
    print('DONE — check the catalogue in the app')


if __name__=='__main__':
    try:main()
    except (RuntimeError, ValueError) as exc:
        print('ERROR:',exc,file=sys.stderr)
        sys.exit(1)
