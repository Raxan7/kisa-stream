#!/usr/bin/env python3
"""Upload a single existing episode to Bunny Stream without streaming via Render.

Use --link VIDEO_GUID when the video was uploaded using Bunny's dashboard.
Requires KISA_API, KISA_ADMIN_KEY and (for uploading) BUNNY_STREAM_API_KEY.
"""
import argparse
import os
import sys
import time
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser(description='Publish a KISA episode through Bunny Stream')
    parser.add_argument('--episode', required=True, help='Existing KISA episode ID, e.g. secret-wedding-1')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', type=Path, help='MP4 to stream-upload directly to Bunny')
    group.add_argument('--link', help='Existing Bunny video GUID uploaded in Bunny dashboard')
    args = parser.parse_args()
    base = os.environ.get('KISA_API', 'http://localhost:8000').rstrip('/')
    if not (base.startswith('https://') or base.startswith('http://localhost:')):
        sys.exit('KISA_API must use HTTPS, except localhost development')
    key = os.environ.get('KISA_ADMIN_KEY', '')
    if not key:sys.exit('KISA_ADMIN_KEY environment variable required')
    if args.file and (not args.file.is_file() or args.file.suffix.lower() != '.mp4'):
        sys.exit('Upload requires existing .mp4 file')
    with httpx.Client(timeout=30, headers={'X-Admin-Key': key}) as api:
        url = f'{base}/v1/admin/episodes/{args.episode}'
        if args.link:
            response = api.post(url + '/bunny-link', json={'video_id': args.link})
            response.raise_for_status()
            print(response.json())
            return
        video_key = os.environ.get('BUNNY_STREAM_API_KEY', '')
        if not video_key:
            sys.exit('BUNNY_STREAM_API_KEY required for direct upload')
        response = api.post(url + '/bunny-init')
        if response.status_code >= 400:
            sys.exit(f'Cannot create video slot (HTTP {response.status_code}): {response.text[:300]}')
        info = response.json()
        video_id = info['bunny_video_id']
        library_id = info['library_id']
        print(f'Bunny video {video_id}; uploading {args.file.stat().st_size / 1048576:.1f} MB')
        dest = f'https://video.bunnycdn.com/library/{library_id}/videos/{video_id}'
        def chunks():
            with args.file.open('rb') as f:
                while part := f.read(1024 * 1024):
                    yield part
        # Upload is retried from the beginning after transient failures. Large files should
        # be uploaded using Bunny's TUS dashboard/resumable uploader instead.
        for attempt in range(3):
            try:
                with httpx.Client(timeout=httpx.Timeout(60, read=240), follow_redirects=False) as bunny:
                    r = bunny.put(dest, headers={
                        'AccessKey': video_key, 'Content-Type':'video/mp4',
                        'Content-Length':str(args.file.stat().st_size),
                    }, content=chunks())
                r.raise_for_status()
                break
            except (httpx.HTTPError, OSError) as e:
                if attempt == 2:raise SystemExit(f'Bunny upload failed: {e}') from e
                time.sleep(2**attempt)
        print('Uploaded. Processing may take a few minutes.')
        print(f'Check status: curl -H "X-Admin-Key: ***" {url}/bunny-status')

if __name__ == '__main__':main()
