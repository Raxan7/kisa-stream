"""Protected no-JavaScript admin workspace for initial PWA launch.

Admin root credentials are *never* sent to Flutter clients. Cookie is HttpOnly/Secure
in production and all mutations require a per-session CSRF token.
"""
from __future__ import annotations

import html
import hmac
import os
import re
import secrets
from pathlib import Path
import time
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse

router = APIRouter()


def _ctx(request: Request):
    from . import main
    value=request.cookies.get('kisa_admin_session', '')
    if not value:return None
    try:
        data=jwt.decode(value, main.JWT_SECRET, algorithms=['HS256'], audience='kisa-app')
    except jwt.PyJWTError:
        return None
    return data if data.get('scope')=='admin' else None


def _csrf(request: Request, supplied: str):
    ctx=_ctx(request)
    if not ctx:raise HTTPException(401,'Please sign in as admin')
    if not hmac.compare_digest(ctx.get('csrf',''), supplied):
        raise HTTPException(403,'Invalid CSRF token')
    return ctx


def _escape(text):
    return html.escape(str(text or ''),quote=True)


def _page(body: str, title: str = 'Admin'):
    return HTMLResponse('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>KISA Admin</title>
<link rel="icon" href="/favicon.ico" sizes="any"><script defer src="/admin/assets/bunny-upload.js"></script>
<style>
:root{color-scheme:dark}body{margin:0;font:15px system-ui;color:#efedf3;background:#100f19}
main{max-width:1040px;margin:auto;padding:20px}h1{letter-spacing:3px}h2{font-size:20px;margin-top:30px}
form,.panel{background:#201f2d;padding:20px;border-radius:17px;margin:15px 0;border:1px solid #353044}
label{display:block;font-size:12px;color:#c6becd;margin:12px 0 5px}
input,select,textarea{width:100%;box-sizing:border-box;border:1px solid #45384e;background:#13111f;color:#fff;border-radius:10px;padding:13px;font:inherit}
button,.button{display:inline-block;padding:12px 18px;margin-top:12px;background:#ff527b;border:0;border-radius:12px;font-weight:bold;color:white;cursor:pointer;text-decoration:none}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}table{width:100%;border-collapse:collapse}th,td{padding:12px 8px;text-align:left;border-bottom:1px solid #393344}small{color:#ada8be}
a{color:#ff799a}.pill{font-size:11px;color:#93e5b8}
</style></head><body><main><h1>KISA <span style="color:#ff527b">/ Admin</span></h1>'''+body+'</main></body></html>',
    headers={'Cache-Control':'no-store', 'X-Frame-Options':'DENY',
             'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self' https://video.bunnycdn.com; form-action 'self'; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'"})


def _hidden(csrf):return f'<input type="hidden" name="csrf" value="{_escape(csrf)}">'


def _safe_slug(value: str):
    if not re.fullmatch('[a-z0-9-]{3,48}',value):
        raise HTTPException(422, 'IDs use lowercase letters, numbers and hyphens')
    return value

@router.get('/favicon.ico')
def admin_favicon():
    return FileResponse(Path(__file__).with_name('admin-favicon.ico'),
                        media_type='image/x-icon', headers={'Cache-Control': 'public, max-age=86400'})


@router.get('/manifest.json')
def admin_manifest():
    # Admin stays a regular browser page. The viewer PWA manifest is hosted on Pages.
    return JSONResponse({'name':'KISA Studio', 'short_name':'KISA Admin',
                         'start_url':'/admin', 'display':'browser',
                         'theme_color':'#100f19', 'background_color':'#100f19'},
                        headers={'Cache-Control':'public, max-age=3600'})


@router.get('/admin', response_class=HTMLResponse)
def homepage(request:Request):
    if not _ctx(request):
        return _page('''<h2>Administrator sign in</h2>
<form method="post" action="/admin/login"><label>Admin password</label>
<input name="password" type="password" required autocomplete="current-password">
<button type="submit">Sign in</button></form><small>Use HTTPS. Do not share the admin password.</small>''')
    from .admin_bulk import dashboard_html
    return dashboard_html(request)

@router.post('/admin/login')
def login(request:Request,password:str=Form(...)):
    from . import main
    main.limit_auth_requests(request.client.host if request.client else 'unknown','admin_login',10,900)
    configured=os.getenv('ADMIN_DASHBOARD_PASSWORD','')
    if len(configured)<20 or not hmac.compare_digest(password,configured):
        raise HTTPException(403, 'Invalid administrator credentials')
    token=main.sign({'sub':'admin','scope':'admin','csrf':secrets.token_urlsafe(32)},14400)
    r=RedirectResponse('/admin',status_code=303)
    r.set_cookie('kisa_admin_session',token,secure=os.getenv('APP_ENV')=='production',
                 httponly=True,samesite='strict',max_age=14400,path='/admin')
    return r

@router.post('/admin/logout')
def logout(request:Request,csrf:str=Form(...)):
    _csrf(request,csrf)
    r=RedirectResponse('/admin',status_code=303)
    r.delete_cookie('kisa_admin_session',path='/admin')
    return r

@router.post('/admin/shows')
def create_series(request:Request,csrf:str=Form(...),slug:str=Form(...),
                  title:str=Form(...),synopsis:str=Form(...),genre:str=Form('Drama'),poster:str=Form('')):
    _csrf(request,csrf)
    from . import main
    from sqlalchemy.exc import IntegrityError
    slug=_safe_slug(slug.strip())
    if not (2<=len(title)<=120 and 10<=len(synopsis)<=1000 and len(genre)<=64):
        raise HTTPException(422,'Invalid series details')
    if poster and not poster.startswith('https://'):
        raise HTTPException(422,'Poster must use HTTPS')
    try:
        with main.writing() as db:
            db.add(main.Show(id=slug,title=title.strip(),synopsis=synopsis.strip(),
                             genre=genre.strip(),poster_url=poster.strip() or None,
                             is_published=False))
    except IntegrityError as exc:raise HTTPException(409,'Series exists') from exc
    return RedirectResponse('/admin',status_code=303)

@router.post('/admin/episodes')
def create_part(request:Request,csrf:str=Form(...),slug:str=Form(...),number:int=Form(...),
                title:str=Form(...),duration:int=Form(75)):
    _csrf(request,csrf)
    from . import main
    slug=_safe_slug(slug.strip())
    if not (1<=number<=10000 and 1<=duration<=900 and 2<=len(title)<=120):
        raise HTTPException(422,'Invalid episode details')
    with main.writing() as db:
        if not db.get(main.Show,slug):raise HTTPException(404,'Series does not exist')
        if db.get(main.Episode,f'{slug}-{number}'):
            raise HTTPException(409,'Episode exists')
        db.add(main.Episode(id=f'{slug}-{number}',show_id=slug,number=number,
                            title=title,duration_seconds=duration,is_published=False))
    return RedirectResponse('/admin',status_code=303)

@router.post('/admin/bunny/link')
def link_video(request:Request,csrf:str=Form(...),episode:str=Form(...),video_id:str=Form(...)):
    _csrf(request,csrf)
    from . import main, bunny_stream
    if not bunny_stream.valid_id(video_id):raise HTTPException(422,'Invalid Bunny video ID')
    try:
        data=bunny_stream.status(video_id)
        if str(data.get('videoLibraryId'))!=bunny_stream.library_id() or data.get('guid','').lower()!=video_id.lower():
            raise HTTPException(422,'Bunny video does not belong to your library')
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503,'Bunny API temporarily unavailable') from exc
    with main.writing() as db:
        ep=db.get(main.Episode,episode)
        if not ep:raise HTTPException(404,'Unknown episode')
        duplicate=db.scalar(main.select(main.Episode).where(
            main.Episode.bunny_video_id==video_id, main.Episode.id!=episode))
        if duplicate:raise HTTPException(409,'Bunny video already linked')
        ep.bunny_video_id=video_id
    return RedirectResponse('/admin',status_code=303)


# Browser -> Bunny upload. FastAPI issues only a narrowly scoped, expiring
# signature, so the MP4 never passes through FastAPI or its hosting bandwidth.
@router.get('/admin/assets/bunny-upload.js')
def bunny_upload_script():
    from pathlib import Path
    from fastapi.responses import FileResponse
    script = Path(__file__).with_name('bunny-upload.js')
    return FileResponse(script, media_type='text/javascript', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'
    })


@router.post('/admin/videos/bunny/start')
async def start_bunny_upload(request: Request):
    from . import main, bunny_stream
    from sqlalchemy import select
    _csrf(request, request.headers.get('X-CSRF-Token', ''))
    if getattr(main, 'VIDEO_DELIVERY_MODE', 'bunny_stream') == 'r2':
        raise HTTPException(409, 'Switch VIDEO_DELIVERY_MODE=bunny_stream to use Bunny playback')
    main.limit_auth_requests(request.client.host if request.client else 'unknown',
                             'admin_bunny_upload', 180, 900)
    if not request.headers.get('content-type', '').startswith('application/json'):
        raise HTTPException(415, 'JSON content type required')
    try:
        data = await request.json()
    except ValueError as exc:
        raise HTTPException(400, 'Invalid JSON') from exc
    if not isinstance(data, dict):
        raise HTTPException(422, 'Invalid upload request')
    episode = data.get('episode_id', '')
    filename = data.get('filename', '')
    size = data.get('size_bytes', 0)
    if not (isinstance(episode, str) and re.fullmatch(r'[a-z0-9-]{3,80}', episode)
            and isinstance(filename, str) and 1 <= len(filename) <= 180
            and filename.lower().endswith('.mp4')
            and '/' not in filename and '\\' not in filename
            and isinstance(size, int) and not isinstance(size, bool)
            and 1 <= size <= 1024 * 1024 * 1024):
        raise HTTPException(422, 'Choose a valid MP4 up to 1 GiB')

    with main.SessionLocal() as db:
        ep = db.get(main.Episode, episode)
        if ep is None: raise HTTPException(404, 'Episode missing')
        if ep.is_published: raise HTTPException(409, 'Unpublish episode before modifying video')
        video_id = ep.bunny_video_id
        title = f'{ep.show_id} / Episode {ep.number} / {ep.title}'

    if video_id:
        # Reissue a ticket for a resumed browser upload, but never overwrite
        # a finished or currently transcoding Bunny asset.
        try:
            remote = bunny_stream.status(video_id)
        except bunny_stream.BunnyError as exc:
            raise HTTPException(503, f'Cannot check Bunny video: {exc}') from exc
        if remote.get('status') in (1, 2, 3, 4):
            # A completed upload is not a failed upload. Keep the same Bunny
            # GUID and let the dashboard poll until encoding is finished.
            return {'state': 'processing', 'episode_id': episode, 'video_id': video_id,
                    'message': 'Video was received by Bunny. It will go live when processing finishes.'}
        if remote.get('status') in (5, 8):
            raise HTTPException(409, 'Bunny reported a failed video. Please inspect it in Bunny and retry.')
    else:
        try:
            created = bunny_stream.create(title)
        except bunny_stream.BunnyError as exc:
            raise HTTPException(503, f'Bunny could not create this video: {exc}') from exc
        video_id = created['guid']
        with main.writing() as db:
            ep = db.get(main.Episode, episode)
            if ep is None: raise HTTPException(404, 'Episode missing')
            if ep.is_published or ep.bunny_video_id:
                # Another admin started uploading simultaneously. Preserve the
                # first attached video, never silently swap its GUID.
                raise HTTPException(409, 'Episode changed; refresh the dashboard')
            ep.bunny_video_id = video_id
    try:
        return bunny_stream.tus_upload_ticket(video_id)
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503, f'Cannot prepare upload: {exc}') from exc


@router.get('/admin/videos/bunny/status/{episode_id}')
def admin_bunny_status(request: Request, episode_id: str):
    from . import main, bunny_stream
    if not _ctx(request): raise HTTPException(401, 'Please sign in as admin')
    with main.SessionLocal() as db:
        ep = db.get(main.Episode, episode_id)
        if not ep: raise HTTPException(404, 'Episode missing')
        if not ep.bunny_video_id:
            return {'episode_id': episode_id, 'ready': False, 'state': 'awaiting_upload',
                    'status': None, 'encode_progress': 0,
                    'message': 'Episode created. Select an MP4 to begin uploading.'}
        video_id = ep.bunny_video_id
    try:
        result = bunny_stream.status(video_id)
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503, f'Bunny status temporarily unavailable: {exc}') from exc
    status = result.get('status')
    ready = status == 4
    published = False
    if ready:
        # An admin can close the tab after files finish transferring; the
        # server's reconciliation worker also checks these durable flags.
        from .admin_bulk import publish_if_ready
        published = publish_if_ready(episode_id, video_id)
    state = ('ready' if ready else 'failed' if status in (5, 8)
             else 'processing')
    message = ('Video is live.' if published else
               'Bunny finished processing. Ready to publish.' if ready else
               'Bunny could not process this video. Check the file and retry.' if state == 'failed' else
               'Video is safely with Bunny. Processing continues; it will go live when ready.')
    return {
        'episode_id': episode_id,
        'ready': ready, 'published': published, 'state': state,
        'status': status,
        'encode_progress': result.get('encodeProgress'),
        'length_seconds': result.get('length'),
        'message': message,
    }


@router.get('/admin/videos/bunny/preview/{episode_id}')
def admin_bunny_preview(request: Request, episode_id: str):
    from . import main, bunny_stream
    if not _ctx(request): raise HTTPException(401, 'Please sign in as admin')
    with main.SessionLocal() as db:
        ep = db.get(main.Episode, episode_id)
        if not ep: raise HTTPException(404, 'Episode missing')
        if not ep.bunny_video_id: raise HTTPException(409, 'No Bunny video linked')
        video_id = ep.bunny_video_id
    try:
        if bunny_stream.status(video_id).get('status') != 4:
            return HTMLResponse(
                '<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>KISA · Preparing video</title></head>'
                '<body style="background:#100f19;color:#fff;text-align:center;'
                'font:16px system-ui;padding:15vh 20px">'
                '<h1>Video is being processed</h1>'
                '<p>Your upload is safe. Bunny is preparing the video. '
                'It will go live once processing completes.</p>'
                '<a style="color:#ff527b" href="/admin#library">Return to KISA Studio</a>'
                '</body></html>', status_code=200, headers={'Cache-Control':'no-store',
                'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'"})
        url = bunny_stream.embed_url(video_id, ttl=900)
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503, 'Bunny video preview unavailable') from exc
    return RedirectResponse(url, status_code=302, headers={
        'Cache-Control':'no-store', 'Referrer-Policy':'strict-origin-when-cross-origin'
    })

@router.post('/admin/episodes/publish')
def publish_episode(request:Request,csrf:str=Form(...),episode:str=Form(...),publish:str=Form(...)):
    _csrf(request,csrf)
    from . import main, bunny_stream
    if publish not in ('0','1'):raise HTTPException(422,'Invalid publishing action')
    with main.writing() as db:
        ep=db.get(main.Episode,episode)
        if not ep:raise HTTPException(404,'Unknown episode')
        if publish=='1':
            if not ep.bunny_video_id:raise HTTPException(409,'Upload and link video first')
            try:
                if bunny_stream.status(ep.bunny_video_id).get('status')!=4:
                    raise HTTPException(409,'Bunny video is not finished processing')
            except bunny_stream.BunnyError as exc:
                raise HTTPException(503,'Bunny API temporarily unavailable') from exc
        ep.is_published=publish=='1'
        # The series is visible as soon as at least one episode is published.
        if publish=='1':db.get(main.Show,ep.show_id).is_published=True
    return RedirectResponse('/admin',status_code=303)


# KISA Studio: authenticated bulk publishing
from .admin_bulk import router as batch_router
router.include_router(batch_router)
