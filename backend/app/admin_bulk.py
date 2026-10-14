"""KISA admin batch ingest, accessible only through the existing admin session.

Episode slots are created atomically before uploads. Bunny transfers run directly
from the browser. Never send a Bunny library API key to the browser.
"""
from __future__ import annotations

import html
import json
import re
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

router = APIRouter()
MAX_FILE = 1024 * 1024 * 1024
MAX_BATCH = 100


def _require_admin(request: Request, *, mutate=False):
    from .admin_web import _ctx, _csrf
    if mutate:
        return _csrf(request, request.headers.get('X-CSRF-Token', ''))
    ctx = _ctx(request)
    if not ctx:
        raise HTTPException(401, 'Administrator session expired. Sign in again.')
    return ctx


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ''), quote=True)


def _slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9-]{3,48}', value):
        raise HTTPException(422, 'Series slug must use 3–48 lowercase letters, numbers and hyphens')
    return value


def _validate_files(items, start):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH:
        raise HTTPException(422, 'Choose between 1 and 100 MP4 files')
    if type(start) is not int or start < 1 or start + len(items) > 10001:
        raise HTTPException(422, 'Episode numbers must be between 1 and 10000')
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(422, 'Invalid file description')
        name, size, title = item.get('filename'), item.get('size_bytes'), item.get('title')
        duration = item.get('duration_seconds', 75)
        if (not isinstance(name, str) or not 1 <= len(name) <= 180
                or not name.lower().endswith('.mp4') or '/' in name or '\\' in name
                or type(size) is not int or not 1 <= size <= MAX_FILE
                or not isinstance(title, str) or not 1 <= len(title.strip()) <= 120
                or type(duration) is not int or not 1 <= duration <= 900):
            raise HTTPException(422, 'Invalid MP4, title or duration. Maximum size: 1 GiB per file')


def _prepare_payload(payload):
    if not isinstance(payload, dict):
        raise HTTPException(422, 'Invalid batch')
    slug = _slug(payload.get('slug'))
    try:
        start = payload.get('start_number', 1)
        items = payload.get('files')
        _validate_files(items, start)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, 'Invalid batch') from exc
    for flag in ('create_series', 'replace_unlinked', 'auto_publish'):
        if type(payload.get(flag, False)) is not bool:
            raise HTTPException(422, f'{flag} must be a boolean')
    if payload.get('create_series', False):
        title, synopsis, genre = (payload.get('series_title', ''), payload.get('synopsis', ''), payload.get('genre', 'Drama'))
        if (not isinstance(title,str) or not 2 <= len(title.strip()) <= 120
                or not isinstance(synopsis,str) or not 10 <= len(synopsis.strip()) <= 1000
                or not isinstance(genre,str) or not 1 <= len(genre.strip()) <= 64):
            raise HTTPException(422, 'Add a series title, description (10+ characters) and genre')
    return slug, start, items


@router.post('/admin/bulk/prepare')
async def prepare_batch(request: Request):
    _require_admin(request, mutate=True)
    if not request.headers.get('content-type', '').lower().startswith('application/json'):
        raise HTTPException(415, 'JSON request required')
    from . import main
    main.limit_auth_requests(request.client.host if request.client else 'unknown', 'admin_bulk_prepare', 40, 900)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, 'Invalid JSON') from exc
    slug, start, files = _prepare_payload(payload)
    replace = payload.get('replace_unlinked', False)
    create_series = payload.get('create_series', False)
    auto_publish = payload.get('auto_publish', False)
    try:
        with main.writing() as db:
            show = db.get(main.Show, slug)
            if create_series and show:
                raise HTTPException(409, 'Series already exists. Select it from the existing series list.')
            if not show and not create_series:
                raise HTTPException(404, 'Choose an existing series or create a new one')
            if create_series:
                show = main.Show(id=slug, title=payload['series_title'].strip(),
                                 synopsis=payload['synopsis'].strip(), genre=payload.get('genre','Drama').strip(),
                                 is_published=False)
                db.add(show)
            result = []
            for idx, file in enumerate(files):
                number = start + idx
                episode_id = f'{slug}-{number}'
                ep = db.get(main.Episode, episode_id)
                action = 'created'
                if ep:
                    # Never overwrite completed published content or an already linked asset
                    # unless it is an unfinished draft being resumed.
                    if ep.bunny_video_id and ep.is_published:
                        raise HTTPException(409, f'Episode {number} is live. It will not be overwritten.')
                    if ep.is_published and not ep.bunny_video_id:
                        if not replace:
                            raise HTTPException(409, f'Episode {number} is a published placeholder. Enable “Replace empty-video placeholders” to replace it safely.')
                        ep.is_published = False
                        action = 'placeholder-reused'
                    elif ep.bunny_video_id:
                        action = 'upload-resume'
                    elif replace:
                        action = 'draft-reused'
                    else:
                        raise HTTPException(409, f'Episode {number} already exists. Choose another start number or enable placeholder reuse.')
                    if not ep.bunny_video_id:
                        ep.title = file['title'].strip()
                        ep.duration_seconds = file.get('duration_seconds', 75)
                else:
                    ep = main.Episode(id=episode_id, show_id=slug, number=number,
                                      title=file['title'].strip(), duration_seconds=file.get('duration_seconds', 75),
                                      is_published=False)
                    db.add(ep)
                ep.auto_publish_when_ready = auto_publish
                result.append({'episode_id':episode_id, 'number':number, 'action':action, 'title':ep.title})
            # A fully replaced sample series should not appear in the public
            # catalogue until its first real video is successfully published.
            db.flush()
            has_live = db.scalar(select(main.Episode.id).where(
                main.Episode.show_id == slug, main.Episode.is_published.is_(True)).limit(1))
            if not has_live:
                show.is_published = False
    except IntegrityError as exc:
        raise HTTPException(409, 'Episode was created by another request. Reload and try again.') from exc
    return {'series_id':slug, 'count':len(result), 'items':result}


@router.get('/admin/assets/automation.js')
def automation_script(request: Request):
    _require_admin(request)
    return FileResponse(Path(__file__).with_name('admin-automation.js'), media_type='text/javascript',
                        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.get('/admin/assets/automation.css')
def automation_styles(request: Request):
    _require_admin(request)
    return FileResponse(Path(__file__).with_name('admin-automation.css'), media_type='text/css',
                        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


def dashboard_html(request: Request) -> HTMLResponse:
    from . import main
    ctx = _require_admin(request)
    with main.SessionLocal() as db:
        shows = db.scalars(select(main.Show).order_by(main.Show.title)).all()
        episodes = db.scalars(select(main.Episode).order_by(main.Episode.show_id,main.Episode.number)).all()
        users = db.scalar(select(func.count(main.User.id))) or 0
    epcounts = {}
    for e in episodes:
        epcounts[e.show_id] = epcounts.get(e.show_id, 0) + 1
    ready_count = sum(1 for e in episodes if e.bunny_video_id and e.is_published)
    missing_count = sum(1 for e in episodes if e.is_published and not e.bunny_video_id)
    needs_review = sum(1 for e in episodes if not e.is_published and e.bunny_video_id)
    cards = ''.join(
        f'<option value="{_esc(s.id)}" data-next="{1 + max((e.number for e in episodes if e.show_id == s.id), default=0)}">'
        f'{_esc(s.title)} · {epcounts.get(s.id,0)} episodes</option>' for s in shows)
    rows = []
    for ep in episodes[:1500]:
        if ep.is_published and not ep.bunny_video_id:
            status,klass = 'Missing video','warning'
        elif ep.is_published:
            status,klass = 'Live','good'
        elif ep.bunny_video_id:
            status,klass = 'Processing / review','pending'
        else:
            status,klass = 'Draft · no video','muted'
        actions = ''
        if ep.bunny_video_id:
            actions += (f'<a class="tiny-btn" target="_blank" rel="noopener noreferrer" '
                        f'href="/admin/videos/bunny/preview/{_esc(ep.id)}">Preview</a>')
        if ep.bunny_video_id and not ep.is_published:
            actions += (f'<form method="post" action="/admin/episodes/publish" class="inline-action">'
                        f'<input type="hidden" name="csrf" value="{_esc(ctx["csrf"])}">'
                        f'<input type="hidden" name="episode" value="{_esc(ep.id)}">'
                        f'<input type="hidden" name="publish" value="1">'
                        f'<button class="tiny-btn" type="submit">Publish</button></form>')
        if ep.is_published:
            actions += (f'<form method="post" action="/admin/episodes/publish" class="inline-action">'
                        f'<input type="hidden" name="csrf" value="{_esc(ctx["csrf"])}">'
                        f'<input type="hidden" name="episode" value="{_esc(ep.id)}">'
                        f'<input type="hidden" name="publish" value="0">'
                        f'<button class="tiny-btn subtle" type="submit">Unpublish</button></form>')
        rows.append(f'<tr data-series="{_esc(ep.show_id)}" data-search="{_esc((ep.show_id + " " + ep.title + " " + str(ep.number)).lower())}" data-status="{klass}">'
                    f'<td><span class="ep-num">{ep.number:02d}</span></td><td><b>{_esc(ep.title)}</b><small>{_esc(ep.show_id)}</small></td>'
                    f'<td><span class="tag {klass}">{status}</span></td><td class="row-actions">{actions}</td></tr>')
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#12101b">
<title>KISA Studio · Admin</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="stylesheet" href="/admin/assets/automation.css">
<script defer src="/admin/assets/automation.js"></script></head>
<body data-csrf="{_esc(ctx['csrf'])}"><div class="shell">
<aside class="sidebar"><a class="brand" href="/admin"><span class="brand-mark">K</span><span>KISA<small>STUDIO</small></span></a>
<p class="side-label">WORKSPACE</p><a class="nav active" href="#upload"><span>▣</span> Batch uploads</a>
<a class="nav" href="#library"><span>▤</span> Episode library</a>
<a class="nav" href="#help"><span>◈</span> Help & tips</a><div class="side-bottom"><span class="online"></span> Admin session active
<form method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{_esc(ctx['csrf'])}"><button type="submit" class="signout">Sign out ↗</button></form></div></aside>
<main class="main"><header class="top"><div><span class="eyebrow">CONTENT OPERATIONS</span><h1>Make movies, not paperwork.</h1><p>Upload an entire series in one go. KISA handles the episode setup and Bunny processing.</p></div><span class="environment">● KISA Admin</span></header>
<section class="metrics"><div class="metric"><span>Series</span><strong>{len(shows)}</strong></div><div class="metric"><span>Episodes</span><strong>{len(episodes)}</strong></div><div class="metric"><span>Ready & live</span><strong>{ready_count}</strong></div><div class="metric warning-metric"><span>Live without video</span><strong>{missing_count}</strong></div><div class="metric"><span>Awaiting review</span><strong>{needs_review}</strong></div><div class="metric"><span>Viewers</span><strong>{users}</strong></div></section>
<section class="section-panel" id="upload"><div class="section-heading"><div><span class="eyebrow">01 · FAST PUBLISHING</span><h2>Upload episodes</h2><p>Choose your movie, add the MP4 files, and publish when ready.</p></div><span class="soft-tag">Bunny Stream</span></div>
<div class="grid-setup"><div class="field"><label for="series">Movie / series</label><select id="series"><option value="">Choose a series…</option>{cards}<option value="__new__">＋ Create a new movie</option></select><small id="series-help">Select an existing series or create a new one.</small></div>
<div class="field"><label for="start-number">Start at episode</label><input id="start-number" type="number" min="1" max="10000" value="1"><small>Automatically numbers all selected videos in order.</small></div></div>
<div id="new-series" class="new-series" hidden><h3>New movie details</h3><div class="field-grid"><div class="field"><label for="new-title">Movie title</label><input id="new-title" placeholder="The Secret Wedding" maxlength="120"></div>
<div class="field"><label for="new-slug">Short URL name</label><input id="new-slug" placeholder="the-secret-wedding" maxlength="48"></div>
<div class="field"><label for="new-genre">Genre</label><input id="new-genre" value="Drama" maxlength="64"></div></div>
<div class="field"><label for="new-description">Story description</label><textarea id="new-description" rows="2" placeholder="What is this movie about?"></textarea></div></div>
<div class="dropzone" id="dropzone" role="button" tabindex="0"><span class="upload-symbol">⇧</span><h3>Drop your MP4 episodes here</h3><p>Or select multiple files. We'll arrange them by episode number automatically.</p>
<div class="drop-actions"><label for="file-input" class="primary faux-button">Choose videos</label><label for="folder-input" class="secondary faux-button">Choose folder</label></div>
<input id="file-input" type="file" multiple accept=".mp4,video/mp4" hidden><input id="folder-input" type="file" webkitdirectory directory multiple hidden><small>Up to 100 videos per batch · 1 GiB per file · Chrome and desktop</small></div>
<div id="batch-review" hidden><div class="review-head"><div><h3 id="batch-count">Episodes ready</h3><p>Review the order and edit titles if needed. Drag-free move buttons included.</p></div><button id="clear-files" type="button" class="link-btn">Clear selection</button></div><div id="batch-list" class="batch-list"></div>
<div class="options"><label class="check"><input id="replace-existing" type="checkbox"><span>Use existing empty-video episode slots (for your 36 sample episodes). Never replace a video already live.</span></label>
<label class="check"><input id="auto-publish" type="checkbox" checked><span>Automatically publish each episode when Bunny finishes processing</span></label></div>
<div class="action-row"><button class="primary action-main" id="start-batch" type="button">Start all uploads <span>→</span></button><button class="secondary" id="retry-failed" type="button" hidden>Retry failed files ↻</button><span id="overall-progress">Nothing uploading yet.</span></div></div>
<div id="batch-status" class="batch-status" role="status" aria-live="polite" hidden></div>
<p class="hint"><b>How it works:</b> Upload to Bunny happens directly from your browser—not through FastAPI. Keep this tab open while files are transferring. Bunny continues encoding afterward. Bunny continues processing after you leave. Automatic publishing is handled by the backend if enabled; you can also review drafts here.</p></section>
<section class="section-panel" id="library"><div class="section-heading"><div><span class="eyebrow">02 · CONTENT LIBRARY</span><h2>All episodes</h2><p>Find what's ready, what's missing video, and what still needs publishing.</p></div><div class="library-actions"><button type="button" class="secondary" id="publish-ready">Publish ready drafts ✓</button><button type="button" class="secondary" id="refresh-library">Refresh library ↻</button></div></div>
<div class="filters"><input id="search-episodes" placeholder="Search episodes…" aria-label="Search episodes"><select id="filter-series" aria-label="Filter series"><option value="">All series</option>{cards.replace('<option value="__new__">＋ Create a new movie</option>','')}</select><select id="filter-status" aria-label="Filter status"><option value="">All statuses</option><option value="warning">Missing video</option><option value="pending">Processing / review</option><option value="good">Live</option><option value="muted">Draft</option></select></div>
<div class="table-wrap"><table><thead><tr><th>EP</th><th>Episode</th><th>Status</th><th>Actions</th></tr></thead><tbody id="episodes-table">{''.join(rows)}</tbody></table></div><p id="no-rows" hidden>No episodes match your filters.</p></section>
<section class="section-panel help" id="help"><h2>Just three steps</h2><div class="help-grid"><div><b>01 · Select</b><p>Pick a movie and select a complete folder of numbered MP4s.</p></div><div><b>02 · Upload</b><p>Check the automatically suggested titles and click Start all uploads.</p></div><div><b>03 · Done</b><p>KISA watches Bunny processing and publishes ready episodes when you choose automatic publishing.</p></div></div><details><summary>Advanced: manually link an existing Bunny video</summary>
<form method="post" action="/admin/bunny/link" class="advanced-form"><input type="hidden" name="csrf" value="{_esc(ctx['csrf'])}"><label>Episode ID <input name="episode" required placeholder="secret-wedding-1"></label><label>Bunny video GUID <input name="video_id" required placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"></label><button type="submit" class="secondary">Verify and link</button></form></details></section>
<footer>KISA Studio · Content operations, simplified</footer></main></div></body></html>''', headers={
        'Cache-Control':'no-store', 'X-Frame-Options':'DENY', 'X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self' https://video.bunnycdn.com; form-action 'self'; media-src 'self' blob:; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
    })

@router.post('/admin/bulk/publish-ready')
async def publish_ready(request: Request):
    """Safe, idempotent bulk action: publish only finished Bunny-backed drafts.

    Designed for admins returning after a long Bunny transcode. Skip API failures
    and leave unfinished drafts unpublished, rather than losing the whole batch.
    """
    _require_admin(request, mutate=True)
    from . import main, bunny_stream
    if not request.headers.get('content-type','').lower().startswith('application/json'):
        raise HTTPException(415, 'JSON request required')
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(400, 'Invalid JSON') from exc
    if not isinstance(body, dict):
        raise HTTPException(422, 'Invalid request')
    slug = body.get('slug','')
    if slug:
        _slug(slug)
    with main.SessionLocal() as db:
        stmt = select(main.Episode).where(main.Episode.is_published.is_(False),main.Episode.bunny_video_id.is_not(None)).order_by(main.Episode.show_id,main.Episode.number)
        if slug:
            stmt = stmt.where(main.Episode.show_id == slug)
        targets = [(ep.id, ep.bunny_video_id) for ep in db.scalars(stmt.limit(101))]
    if len(targets)>100:
        raise HTTPException(422, 'Too many drafts: publish per series')
    published, waiting, errors = [], [], []
    for episode_id, video_id in targets:
        try:
            state = bunny_stream.status(video_id)
            if state.get('status') != 4:
                waiting.append(episode_id)
                continue
        except bunny_stream.BunnyError:
            errors.append(episode_id)
            continue
        with main.writing() as db:
            ep = db.get(main.Episode,episode_id)
            if ep and not ep.is_published and ep.bunny_video_id == video_id:
                ep.is_published = True
                show = db.get(main.Show,ep.show_id)
                if show:
                    show.is_published = True
                published.append(episode_id)
    return {'published':published,'waiting':waiting,'errors':errors}


def publish_if_ready(episode_id: str, video_id: str) -> bool:
    """Publish only an opted-in, unchanged, finished Bunny video.

    Caller must have verified the exact video's Bunny status is FINISHED (4).
    Rechecks identifiers in a DB transaction to prevent stale upload races.
    """
    from . import main
    with main.writing() as db:
        ep = db.get(main.Episode, episode_id)
        if not (ep and ep.auto_publish_when_ready and not ep.is_published
                and ep.bunny_video_id == video_id):
            return bool(ep and ep.is_published and ep.bunny_video_id == video_id)
        ep.is_published = True
        show = db.get(main.Show, ep.show_id)
        if show:
            show.is_published = True
        return True


def reconcile_auto_publish(limit: int = 30) -> int:
    """Idempotent server-side scan; no open browser tab required.

    A sleeping free-tier host only runs this after it wakes. A permanent,
    independently scheduled worker or signed Bunny webhook is recommended
    for prompt publication regardless of API activity.
    """
    from . import main, bunny_stream
    with main.SessionLocal() as db:
        stmt = select(main.Episode.id, main.Episode.bunny_video_id).where(
            main.Episode.is_published.is_(False),
            main.Episode.auto_publish_when_ready.is_(True),
            main.Episode.bunny_video_id.is_not(None)).limit(limit)
        targets = list(db.execute(stmt))
    count = 0
    for episode_id, video_id in targets:
        try:
            if bunny_stream.status(video_id).get('status') == 4:
                count += int(publish_if_ready(episode_id, video_id))
        except bunny_stream.BunnyError as exc:
            logging.getLogger(__name__).warning(
                'Cannot reconcile Bunny processing for episode %s: %s', episode_id, exc)
    return count
