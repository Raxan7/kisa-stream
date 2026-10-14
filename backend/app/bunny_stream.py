"""Bunny Stream management and signed embed playback, server-side only.

Docs: https://docs.bunny.net/reference/video_getvideo and
https://docs.bunny.net/docs/stream-embed-token-authentication
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from urllib.parse import urlencode

import httpx

GUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

class BunnyError(RuntimeError):
    pass


def library_id() -> str:
    value = os.getenv('BUNNY_STREAM_LIBRARY_ID', '').strip()
    if not value.isdigit():
        raise BunnyError('BUNNY_STREAM_LIBRARY_ID must be configured')
    return value


def api_key() -> str:
    value = os.getenv('BUNNY_STREAM_API_KEY', '')
    if not value:
        raise BunnyError('BUNNY_STREAM_API_KEY is missing')
    return value


def api_url(path: str = '') -> str:
    return f'https://video.bunnycdn.com/library/{library_id()}/videos{path}'


def request(method: str, url: str, *, json=None, content=None, timeout=20) -> dict:
    try:
        response = httpx.request(method, url,
            headers={'AccessKey': api_key(), 'Accept': 'application/json'},
            json=json, content=content, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            message = f'Bunny returned HTTP {code}. Check the Stream library ID, library API key, and account permissions on the server.'
        elif code == 402:
            message = 'Bunny returned HTTP 402. Check trial credits or account billing.'
        elif code == 429:
            message = 'Bunny rate-limited the request (HTTP 429). Please retry shortly.'
        else:
            message = f'Bunny returned HTTP {code}. Check Bunny Stream and retry.'
        # Only the HTTP status is exposed; never include response bodies or secret headers.
        raise BunnyError(message) from exc
    except httpx.RequestError as exc:
        raise BunnyError('Bunny Stream could not be reached. Check provider connectivity.') from exc
    except ValueError as exc:
        raise BunnyError('Bunny returned an invalid response.') from exc


def valid_id(video_id: str) -> bool:
    return bool(GUID.fullmatch(video_id))


def create(title: str) -> dict:
    data = request('POST', api_url(), json={'title': title})
    if not valid_id(data.get('guid', '')):
        raise BunnyError('Bunny returned an invalid video ID')
    return data


def status(video_id: str) -> dict:
    if not valid_id(video_id):
        raise BunnyError('Invalid Bunny video ID')
    return request('GET', api_url('/' + video_id))


def embed_url(video_id: str, ttl: int = 1200) -> str:
    """One-useful-window signed iframe URL. Enable Player Token Authentication in Bunny!"""
    if not valid_id(video_id):
        raise BunnyError('Invalid Bunny video ID')
    key = os.getenv('BUNNY_STREAM_TOKEN_KEY', '')
    if not key:
        raise BunnyError('Bunny embed signing key not configured')
    expires = int(time.time()) + ttl
    token = hashlib.sha256(f'{key}{video_id}{expires}'.encode()).hexdigest()
    query = urlencode({'token': token, 'expires': str(expires), 'autoplay': 'true', 'responsive': 'true'})
    return f'https://player.mediadelivery.net/embed/{library_id()}/{video_id}?{query}'

# Server-only direct-to-Bunny TUS signing. Never reveal the Stream API key.
def tus_upload_ticket(video_id: str, ttl: int = 21600) -> dict:
    if not valid_id(video_id):
        raise BunnyError('Invalid Bunny video ID')
    if not 3600 <= ttl <= 21600:
        raise BunnyError('Invalid Bunny upload-ticket lifetime')
    lib = library_id()
    expires = int(time.time()) + ttl
    signature = hashlib.sha256(f'{lib}{api_key()}{expires}{video_id}'.encode('utf-8')).hexdigest()
    return {
        'tus_endpoint': 'https://video.bunnycdn.com/tusupload',
        'video_id': video_id,
        'library_id': lib,
        'expires': expires,
        'signature': signature,
    }
