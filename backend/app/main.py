"""KISA streaming API. Transactional entitlements and server-controlled balance.
Run: cd backend && uvicorn app.main:app --reload
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from . import clickpass, clickpesa, object_storage, bunny_stream, email_login
from sqlalchemy import (Boolean, CheckConstraint, ForeignKey, Integer, String, func,
                        Text, UniqueConstraint, create_engine, select, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = (ROOT / 'data' / 'videos').resolve()
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "data" / "kisa.db"}')
if DB_URL.startswith('postgres://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgres://'):]
elif DB_URL.startswith('postgresql://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgresql://'):]
JWT_SECRET = os.getenv('JWT_SECRET', 'local-dev-key-NOT-FOR-PRODUCTION')
ADMIN_KEY = os.getenv('ADMIN_API_KEY', 'local-admin-key-NOT-FOR-PRODUCTION')
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
DEMO_KEY = os.getenv('DEMO_ADMIN_KEY', 'local-demo-key')
PAYMENT_MODE = os.getenv('PAYMENT_MODE', 'demo')
def enabled_modes():
    return frozenset(m.strip() for m in PAYMENT_MODE.split(',') if m.strip())
BASE_URL = os.getenv('BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
FREE_EPISODES = int(os.getenv('FREE_EPISODES', '8'))
EPISODE_COST = int(os.getenv('EPISODE_COST_COINS', '10'))
PACK_TZS = int(os.getenv('TOKEN_PACK_TZS', '1000'))
PACK_COINS = int(os.getenv('TOKEN_PACK_COINS', '30'))
if not (0 <= FREE_EPISODES <= 100 and 1 <= EPISODE_COST <= 10000 and
        100 <= PACK_TZS <= 10_000_000 and 1 <= PACK_COINS <= 1_000_000):
    raise RuntimeError('Invalid token pricing configuration')

if os.getenv('APP_ENV') == 'production':
    if DB_URL.startswith('sqlite'):
        raise RuntimeError('Production database must be durable PostgreSQL, not local SQLite')
    if (len(JWT_SECRET) < 32 or JWT_SECRET.startswith('local-') or
        len(ADMIN_KEY) < 32 or ADMIN_KEY.startswith('local-')):
        raise RuntimeError('Set long random JWT_SECRET and ADMIN_API_KEY before production deployment')
    if DEMO_MODE or 'demo' in enabled_modes():
        raise RuntimeError('Demo money must never be enabled in production')

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))
    __table_args__ = (CheckConstraint('balance >= 0', name='nonnegative_balance'),)

class AuthRate(Base):
    __tablename__ = 'auth_rates'
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

class EmailIdentity(Base):
    __tablename__ = 'email_identities'
    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False, unique=True)
    verified_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

class EmailCode(Base):
    __tablename__ = 'email_codes'
    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

class Show(Base):
    __tablename__ = 'shows'
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[str] = mapped_column(String(64), default='Drama')
    accent: Mapped[str] = mapped_column(String(8), default='#B31E5D')
    poster_url: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

class Episode(Base):
    __tablename__ = 'episodes'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    show_id: Mapped[str] = mapped_column(String(48), ForeignKey('shows.id'), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=75)
    filename: Mapped[str | None] = mapped_column(String(255))
    # Existing database deployments add this nullable column via migrations/001_bunny_video.sql.
    bunny_video_id: Mapped[str | None] = mapped_column(String(64))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_publish_when_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    __table_args__ = (UniqueConstraint('show_id', 'number'), CheckConstraint('number > 0'),)

class Entitlement(Base):
    __tablename__ = 'entitlements'
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(100), ForeignKey('episodes.id'), primary_key=True)
    purchased_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='pending')
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(255))
    amount_tzs: Mapped[int] = mapped_column(Integer, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

class WalletEntry(Base):
    __tablename__ = 'wallet_entries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))
    __table_args__ = (UniqueConstraint('kind', 'reference', name='wallet_entry_once'),)

class Progress(Base):
    __tablename__ = 'progress'
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), primary_key=True)
    show_id: Mapped[str] = mapped_column(String(48), ForeignKey('shows.id'), primary_key=True)
    episode_number: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

class Favourite(Base):
    __tablename__ = 'favourites'
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), primary_key=True)
    show_id: Mapped[str] = mapped_column(String(48), ForeignKey('shows.id'), primary_key=True)

engine = create_engine(DB_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DB_URL.startswith('sqlite') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base.metadata.create_all(bind=engine)

@contextmanager
def writing():
    """SQLite serializes writers before balance read; Postgres locks wallet rows explicitly."""
    db = SessionLocal()
    try:
        if engine.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db():
    with SessionLocal() as db:
        yield db

def require_user(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required')
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=['HS256'], audience='kisa-app')
        if payload.get('scope') != 'user':
            raise ValueError('wrong scope')
        return str(payload['sub'])
    except Exception:
        raise HTTPException(401, 'Invalid or expired session')

def admin(x_admin_key: Annotated[str | None, Header()] = None):
    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, 'Admin authorization required')

def sign(data: dict, seconds=3600):
    return jwt.encode({**data, 'aud': 'kisa-app', 'exp': int(time.time()) + seconds}, JWT_SECRET, algorithm='HS256')

def get_locked_user(db, uid):
    user = db.scalar(select(User).where(User.id == uid).with_for_update())
    if user is None:
        raise HTTPException(401, 'Session account no longer exists')
    return user

def episode_payload(ep: Episode, uid: str, granted: set[str]):
    return {'id': ep.id, 'number': ep.number, 'title': ep.title,
            'duration_seconds': ep.duration_seconds,
            'is_free': ep.number <= FREE_EPISODES,
            'is_unlocked': ep.number <= FREE_EPISODES or ep.id in granted,
            'cost_coins': 0 if ep.number <= FREE_EPISODES else EPISODE_COST}

def show_payload(s: Show):
    return {'id': s.id, 'title': s.title, 'synopsis': s.synopsis,
            'genre': s.genre, 'accent': s.accent, 'poster_url': s.poster_url}

def seed():
    with writing() as db:
        if db.scalar(select(Show.id).limit(1)):
            return
        stories = [
            ('the-last-promise','The Last Promise','She was supposed to marry a billionaire. Then the stranger at her wedding whispered a name she buried years ago.','Romance','#C84672'),
            ('midnight-heir','The Midnight Heir','A street musician inherits a secret empire, but someone inside the family knows exactly who she really is.','Mystery','#6255CC'),
            ('borrowed-heart','Borrowed Heart','One fake engagement. Two rival families. And a confession that changes everything.','Romance','#C78145'),
        ]
        for sid, title, synopsis, genre, accent in stories:
            db.add(Show(id=sid,title=title,synopsis=synopsis,genre=genre,accent=accent))
            for n in range(1, 13):
                db.add(Episode(id=f'{sid}-{n}',show_id=sid,number=n,
                       title=['The Unexpected Meeting','A Dangerous Secret','The Call','Betrayal','No Turning Back','The Witness','A Second Chance','The Final Letter','Behind the Door','A Name Revealed','One Last Decision','To Be Continued'][n-1],
                       duration_seconds=75,
                       filename='sample.mp4' if n <= 12 else None))

@asynccontextmanager
async def kisa_lifespan(_app):
    """Reconcile queued publish-on-ready uploads even after the admin leaves."""
    import threading
    import logging
    stop = threading.Event()
    worker = None
    if (os.getenv('BUNNY_AUTO_PUBLISH_ENABLED', 'true').lower() == 'true'
            and os.getenv('BUNNY_STREAM_LIBRARY_ID')
            and os.getenv('BUNNY_STREAM_API_KEY')):
        interval = max(30, int(os.getenv('BUNNY_AUTO_PUBLISH_SECONDS', '60')))
        def scan():
            from .admin_bulk import reconcile_auto_publish
            # Render Free may sleep. Scanning resumes after it wakes.
            while not stop.wait(interval):
                try:
                    reconcile_auto_publish()
                except Exception:
                    logging.getLogger(__name__).exception('KISA auto-publish check failed')
        worker = threading.Thread(target=scan, name='kisa-bunny-publisher', daemon=True)
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.join(timeout=2)


app = FastAPI(title='KISA Streaming API', version='0.1.0',
              docs_url=None if os.getenv('APP_ENV') == 'production' else '/docs',
              lifespan=kisa_lifespan)
origins = [x.strip() for x in os.getenv('CORS_ORIGINS', '').split(',') if x.strip()]
# Flutter web's localhost and 127.0.0.1 hosts are distinct browser origins.
# Allow both in local development ONLY; never implicitly in production.
if os.getenv('APP_ENV') != 'production':
    origins = list(dict.fromkeys([
        *origins, 'http://localhost:3000', 'http://127.0.0.1:3000',
    ]))
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=['GET','POST'], allow_headers=['Authorization','Content-Type','X-Admin-Key','X-Demo-Key'])
# Never insert demonstration data on API startup or during deployment.
# `seed()` remains available for explicit LOCAL TEST FIXTURES only.
# In particular, SEED_DEMO=true must not populate a hosted database.

@app.get('/health')
def health():
    with SessionLocal() as db:
        db.execute(text('SELECT 1'))
    return {'ok': True, 'payment_mode': PAYMENT_MODE}

@app.post('/v1/auth/guest')
def guest():
    uid = str(uuid.uuid4())
    with writing() as db:
        db.add(User(id=uid))
    return {'access_token':sign({'sub':uid,'scope':'user'},seconds=60*60*24*90),'user_id':uid}

def limit_auth_requests(ip: str, purpose: str, maximum: int = 12, period: int = 3600):
    """Best-effort shared-DB throttle for OTP delivery and admin sign-in."""
    fingerprint = hmac.new(JWT_SECRET.encode(), f'{purpose}:{ip}'.encode(), hashlib.sha256).hexdigest()
    now = int(time.time())
    with writing() as db:
        item = db.get(AuthRate, fingerprint)
        if item is None:
            db.add(AuthRate(fingerprint=fingerprint, window_start=now, attempts=1))
        elif now-item.window_start >= period:
            item.window_start = now
            item.attempts = 1
        elif item.attempts >= maximum:
            raise HTTPException(429, 'Too many requests. Please try again later.')
        else:
            item.attempts += 1

class EmailAddress(BaseModel):
    email: str = Field(min_length=5, max_length=254)

class EmailVerification(EmailAddress):
    code: str = Field(pattern=r'^\d{6}$')


def normalized_email(raw: str) -> str:
    from email.utils import parseaddr
    email = raw.strip().lower()
    if parseaddr(email)[1] != email or email.count('@') != 1:
        raise HTTPException(422, 'Invalid email address')
    local, domain = email.split('@')
    if not local or '.' not in domain or any(c.isspace() for c in email):
        raise HTTPException(422, 'Invalid email address')
    return email


def otp_digest(email: str, code: str) -> str:
    return hmac.new(JWT_SECRET.encode(), f'{email}:{code}'.encode(), hashlib.sha256).hexdigest()


@app.post('/v1/auth/email/request')
def request_email_code(data: EmailAddress, request: Request):
    email = normalized_email(data.email)
    limit_auth_requests(request.client.host if request.client else 'unknown', 'email_request', 15)
    now = int(time.time())
    code = f'{secrets.randbelow(1_000_000):06d}'
    with writing() as db:
        existing = db.get(EmailCode, email)
        if existing and now - existing.sent_at < 60:
            raise HTTPException(429, 'Wait 60 seconds before requesting another code')
        if existing: db.delete(existing); db.flush()
        db.add(EmailCode(email=email, code_digest=otp_digest(email,code),
                         sent_at=now, expires_at=now+600, attempts=0))
    try:
        email_login.send_code(email, code)
    except email_login.MailError as exc:
        with writing() as db:
            db.query(EmailCode).filter(EmailCode.email == email).delete()
        raise HTTPException(503, 'Email sign-in is temporarily unavailable') from exc
    return {'sent': True, 'expires_in': 600}


@app.post('/v1/auth/email/verify')
def verify_email_code(data: EmailVerification,
                      authorization: Annotated[str | None, Header()] = None):
    email = normalized_email(data.email)
    now = int(time.time())
    guest_uid = None
    if authorization:
        guest_uid = require_user(authorization)
    with writing() as db:
        code = db.scalar(select(EmailCode).where(EmailCode.email == email).with_for_update())
        if not code or code.expires_at < now or code.attempts >= 5:
            raise HTTPException(400, 'Invalid or expired code')
        code.attempts += 1
        good = hmac.compare_digest(code.code_digest, otp_digest(email, data.code))
        if good:
            identity = db.get(EmailIdentity, email)
            if identity is not None:
                uid = identity.user_id
            elif guest_uid and db.get(User, guest_uid) is not None and not db.scalar(
                    select(EmailIdentity).where(EmailIdentity.user_id == guest_uid)):
                uid = guest_uid
                db.add(EmailIdentity(email=email, user_id=uid))
            else:
                uid = str(uuid.uuid4())
                db.add(User(id=uid))
                db.add(EmailIdentity(email=email, user_id=uid))
            db.delete(code)
    if not good:
        raise HTTPException(400, 'Invalid or expired code')
    return {'access_token': sign({'sub':uid,'scope':'user'}, seconds=60*60*24*30),
            'user_id': uid, 'email': email}


def verified_email(db, uid: str) -> bool:
    return db.scalar(select(EmailIdentity.email).where(EmailIdentity.user_id == uid)) is not None

@app.get('/v1/me')
def me(uid: str=Depends(require_user)):
    with SessionLocal() as db:
        u = db.get(User,uid)
        if not u:
            raise HTTPException(401,'User not found')
        return {'user_id':uid,'email_verified':verified_email(db,uid),'balance':u.balance, 'free_episodes':FREE_EPISODES,
                'episode_cost': EPISODE_COST,'pack_coins': PACK_COINS,'pack_tzs':PACK_TZS,
                'payment_mode': PAYMENT_MODE, 'demo_mode':DEMO_MODE}

@app.get('/v1/shows')
def shows(q: str='', genre: str=''):
    with SessionLocal() as db:
        stmt = select(Show).where(Show.is_published.is_(True)).order_by(Show.title)
        if q: stmt = stmt.where(Show.title.ilike(f'%{q[:80]}%'))
        if genre: stmt = stmt.where(Show.genre == genre)
        return {'items':[show_payload(s) for s in db.scalars(stmt)]}

@app.get('/v1/shows/{sid}')
def show_detail(sid: str, uid: str=Depends(require_user)):
    with SessionLocal() as db:
        s = db.get(Show,sid)
        if not s or not s.is_published: raise HTTPException(404,'Show not found')
        eps = db.scalars(select(Episode).where(Episode.show_id==sid, Episode.is_published.is_(True)).order_by(Episode.number)).all()
        ids = {r.episode_id for r in db.scalars(select(Entitlement).where(Entitlement.user_id == uid))}
        p = db.get(Progress,(uid,sid))
        fav = db.get(Favourite,(uid,sid)) is not None
        return {**show_payload(s),'episodes':[episode_payload(e,uid,ids) for e in eps],
                'continue_episode':p.episode_number if p else 1,'favourite':fav}

@app.post('/v1/shows/{sid}/favourite')
def favourite(sid: str, uid: str=Depends(require_user)):
    with writing() as db:
        s=db.get(Show,sid)
        if not s or not s.is_published: raise HTTPException(404,'Show not found')
        f=db.get(Favourite,(uid,sid))
        if f: db.delete(f)
        else: db.add(Favourite(user_id=uid, show_id=sid))
        return {'favourite': not bool(f)}

@app.get('/v1/library')
def library(uid: str=Depends(require_user)):
    with SessionLocal() as db:
        saved = db.scalars(select(Show).join(Favourite, Favourite.show_id==Show.id).where(Favourite.user_id==uid,Show.is_published.is_(True))).all()
        watching = db.execute(select(Show,Progress.episode_number).join(Progress,Progress.show_id==Show.id).where(Progress.user_id==uid,Show.is_published.is_(True)).order_by(Progress.updated_at.desc())).all()
        return {'saved':[show_payload(s) for s in saved],
                'continue_watching':[{**show_payload(s),'episode_number':n} for s,n in watching]}

class ProgressRequest(BaseModel):
    episode_number: int = Field(ge=1,le=10000)

@app.post('/v1/shows/{sid}/progress')
def update_progress(sid: str, req: ProgressRequest,uid:str=Depends(require_user)):
    with writing() as db:
        ep=db.scalar(select(Episode).where(Episode.show_id==sid,Episode.number==req.episode_number,Episode.is_published.is_(True)))
        if not ep: raise HTTPException(404,'Episode not found')
        allowed = ep.number <= FREE_EPISODES or db.get(Entitlement,(uid,ep.id)) is not None
        if not allowed: raise HTTPException(402,'Episode is locked')
        p=db.get(Progress,(uid,sid))
        if not p: db.add(Progress(user_id=uid,show_id=sid,episode_number=ep.number))
        else:
            p.episode_number=ep.number
            p.updated_at=int(time.time())
    return {'ok':True}

@app.post('/v1/episodes/{eid}/unlock')
def unlock(eid:str, uid:str=Depends(require_user)):
    with writing() as db:
        ep=db.get(Episode,eid)
        if not ep or not ep.is_published: raise HTTPException(404,'Episode not found')
        s=db.get(Show,ep.show_id)
        if not s or not s.is_published: raise HTTPException(404,'Show not found')
        u=get_locked_user(db,uid)
        if ep.number <= FREE_EPISODES: return {'unlocked':True,'spent':0,'balance':u.balance}
        if db.get(Entitlement,(uid,eid)):
            return {'unlocked':True,'spent':0,'balance':u.balance}
        if u.balance < EPISODE_COST:
            raise HTTPException(402,{'code':'INSUFFICIENT_COINS','required':EPISODE_COST,'balance':u.balance})
        u.balance -= EPISODE_COST
        db.add(Entitlement(user_id=uid,episode_id=eid))
        db.add(WalletEntry(id=str(uuid.uuid4()),user_id=uid,delta=-EPISODE_COST,kind='episode',reference=f'{uid}:{eid}'))
        return {'unlocked':True,'spent':EPISODE_COST,'balance':u.balance}

@app.post('/v1/episodes/{eid}/play')
def play(eid: str,uid:str=Depends(require_user)):
    with SessionLocal() as db:
        ep=db.get(Episode,eid)
        if not ep or not ep.is_published: raise HTTPException(404,'Episode not found')
        s=db.get(Show,ep.show_id)
        if not s or not s.is_published: raise HTTPException(404,'Show not found')
        if ep.number>FREE_EPISODES and not db.get(Entitlement,(uid,eid)):
            raise HTTPException(402,{'code':'EPISODE_LOCKED','required':EPISODE_COST})
        if ep.bunny_video_id:
            try:
                # Bunny returns status 4 when encoding is finished.
                details = bunny_stream.status(ep.bunny_video_id)
                if details.get('status') != 4:
                    return {'ready': False, 'url': None, 'message': 'Video is still processing'}
                return {'ready': True, 'url': bunny_stream.embed_url(ep.bunny_video_id),
                        'player_type': 'bunny_embed', 'expires_in': 1200}
            except bunny_stream.BunnyError as exc:
                raise HTTPException(503, 'Video service temporarily unavailable') from exc
        if not ep.filename or not object_storage.valid_key(ep.filename):
            return {'ready':False,'message':'Video has not been uploaded yet','url':None}
        if object_storage.enabled():
            try:
                if not object_storage.exists(ep.filename):
                    return {'ready':False,'message':'Video has not been uploaded yet','url':None}
                url=object_storage.presign(ep.filename)
            except Exception as exc:
                raise HTTPException(503, 'Video storage is temporarily unavailable') from exc
            return {'ready':True,'url':url,'expires_in':1200}
        if not (VIDEO_DIR / ep.filename).is_file():
            return {'ready':False,'message':'Video has not been uploaded yet','url':None}
        ticket=sign({'sub':uid,'scope':'media','eid':eid},seconds=60*20)
        return {'ready':True,'url':f'{BASE_URL}/v1/media/{eid}?ticket={ticket}', 'expires_in':1200}

@app.get('/v1/media/{eid}')
def media(eid:str, request: Request, ticket:str=Query(...)):
    try:
        data=jwt.decode(ticket, JWT_SECRET, algorithms=['HS256'], audience='kisa-app')
        if data.get('scope')!='media' or data.get('eid')!=eid: raise ValueError('invalid ticket')
    except Exception: raise HTTPException(401,'Invalid playback ticket')
    with SessionLocal() as db:
        ep=db.get(Episode,eid)
        if not ep or not ep.is_published:raise HTTPException(404,'Not found')
        if ep.number>FREE_EPISODES and db.get(Entitlement,(str(data['sub']),eid)) is None:
            raise HTTPException(403,'Access revoked')
        if not ep.filename or Path(ep.filename).name!=ep.filename:
            raise HTTPException(404,'Video missing')
        path=(VIDEO_DIR / ep.filename).resolve()
        if VIDEO_DIR not in path.parents or not path.is_file():raise HTTPException(404,'Video missing')
    total=path.stat().st_size
    range_header=request.headers.get('range')
    headers={'Accept-Ranges':'bytes','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}
    if not range_header:
        return FileResponse(path,media_type='video/mp4',headers=headers)
    try:
        unit, segment=range_header.split('=',1)
        if unit.strip()!='bytes' or ',' in segment: raise ValueError()
        start_s,end_s=segment.split('-',1)
        if start_s:
            start=int(start_s)
            end=int(end_s) if end_s else total-1
        else:
            suffix=int(end_s)
            if suffix <= 0:raise ValueError()
            start=max(total-suffix,0);end=total-1
        if start<0 or start>=total or end<start:raise ValueError()
        end=min(end,total-1)
    except (ValueError, TypeError):
        return Response(status_code=416,headers={'Content-Range':f'bytes */{total}',**headers})
    def chunks():
        remaining=end-start
        with path.open('rb') as f:
            f.seek(start)
            while remaining>=0:
                chunk=f.read(min(1024*256,remaining+1))
                if not chunk: break
                remaining-=len(chunk)
                yield chunk
    return StreamingResponse(chunks(),status_code=206,media_type='video/mp4',headers={**headers,'Content-Range':f'bytes {start}-{end}/{total}','Content-Length':str(end-start+1)})

@app.get('/v1/wallet')
def wallet(uid:str=Depends(require_user)):
    with SessionLocal() as db:
        user=db.get(User,uid)
        if not user:raise HTTPException(401,'Invalid session')
        rows=db.scalars(select(WalletEntry).where(WalletEntry.user_id==uid).order_by(WalletEntry.created_at.desc()).limit(100)).all()
        return {'balance':user.balance,'entries':[{'delta':r.delta,'kind':r.kind,'reference':r.reference,'created_at':r.created_at} for r in rows],
                'package':{'tzs':PACK_TZS,'coins':PACK_COINS}}

@app.post('/v1/payments')
def make_payment(uid:str=Depends(require_user)):
    # Only the independent APK calls this checkout route. The Play app launches
    # Google Play Billing locally and uses /v1/billing/play/verify after purchase.
    if 'clickpesa' in enabled_modes():
        provider = 'clickpesa'
        gateway = clickpesa
        webhook = 'clickpesa'
    elif 'clickpass' in enabled_modes():
        provider = 'clickpass'
        gateway = clickpass
        webhook = 'clickpass'
    elif 'demo' in enabled_modes() and DEMO_MODE:
        provider = 'demo'
        gateway = None
        webhook = None
    elif 'play' in enabled_modes():
        return {'provider':'play','product_id':os.getenv('GOOGLE_PLAY_PRODUCT_ID','coins_30_tzs_1000'),
                'status':'store_purchase_required'}
    else:
        raise HTTPException(503,'Payment configuration unavailable')
    if os.getenv('APP_ENV') == 'production':
        with SessionLocal() as db:
            if not verified_email(db, uid):
                raise HTTPException(403, 'Sign in with verified email before buying coins')
    payment_id=str(uuid.uuid4())
    with writing() as db:
        get_locked_user(db,uid)
        db.add(Payment(id=payment_id,user_id=uid,status='pending',provider=provider,
                       amount_tzs=PACK_TZS,coins=PACK_COINS))
    if provider == 'demo':
        return {'id':payment_id,'status':'pending','provider':'demo','checkout_url':None}
    try:
        checkout, provider_order = gateway.create_checkout(
            payment_id, PACK_TZS, uid, f'{BASE_URL}/v1/payments/{webhook}/webhook')
        with writing() as db:
            p = db.get(Payment,payment_id)
            p.provider_order_id = provider_order
        return {'id':payment_id,'status':'pending','provider':provider,'checkout_url':checkout}
    except (clickpass.GatewayError, clickpesa.GatewayError) as exc:
        raise HTTPException(503,{'code':'GATEWAY_NOT_READY','payment_id':payment_id,
                                 'detail':str(exc)})

def settle_payment(db, payment_id:str, provider_ref:str):
    p=db.scalar(select(Payment).where(Payment.id==payment_id).with_for_update())
    if p is None:raise HTTPException(404,'Payment not found')
    if p.status=='paid':
        if p.provider_transaction_id!=provider_ref:raise HTTPException(409,'Provider reference mismatch')
        return p, False
    if p.status!='pending':raise HTTPException(409,'Payment cannot be settled')
    prior=db.scalar(select(Payment).where(Payment.provider_transaction_id==provider_ref))
    if prior:raise HTTPException(409,'Provider transaction already used')
    user=get_locked_user(db,p.user_id)
    user.balance+=p.coins
    p.status='paid';p.provider_transaction_id=provider_ref
    db.add(WalletEntry(id=str(uuid.uuid4()),user_id=user.id,delta=p.coins,kind='topup',reference=p.id))
    return p, True

def refresh_external_payment(pid: str, uid: str | None = None):
    with SessionLocal() as db:
        p=db.get(Payment,pid)
        if p is None or (uid is not None and p.user_id != uid):
            raise HTTPException(404,'Payment not found')
        if p.provider not in ('clickpass','clickpesa') or p.provider not in enabled_modes():
            raise HTTPException(404,'Payment not found')
        if p.status=='paid':return {'id':pid,'status':'paid','credited':False}
        if not p.provider_order_id:raise HTTPException(409,'Provider checkout not initialized')
        order_ref=p.provider_order_id
        amount=p.amount_tzs
        gateway = clickpesa if p.provider=='clickpesa' else clickpass
    try:
        verified_txn=gateway.verify_order(pid,order_ref,amount)
    except (clickpass.GatewayError, clickpesa.GatewayError) as exc:
        raise HTTPException(502,'Provider reconciliation unavailable') from exc
    if not verified_txn:return {'id':pid,'status':'pending','credited':False}
    with writing() as db:
        p, credited=settle_payment(db,pid,verified_txn)
        return {'id':p.id,'status':p.status,'credited':credited}

@app.post('/v1/payments/{pid}/refresh')
def payment_refresh(pid:str,uid:str=Depends(require_user)):
    return refresh_external_payment(pid, uid)

@app.post('/v1/payments/{provider}/webhook')
async def external_payment_webhook(provider:str, request:Request):
    # Always query payment status SERVER-SIDE. Webhook body is never proof of payment.
    if provider not in ('clickpass','clickpesa') or provider not in enabled_modes():
        raise HTTPException(404,'Not found')
    required=os.getenv(f'{provider.upper()}_WEBHOOK_SECRET','')
    sent=request.headers.get(f'x-{provider}-webhook-secret','')
    if not required or not hmac.compare_digest(required,sent):
        raise HTTPException(403,'Webhook rejected')
    data=await request.json()
    if not isinstance(data,dict) or not isinstance(data.get('reference'),str):
        raise HTTPException(422,'Missing verified reference field')
    with SessionLocal() as db:
        order=db.get(Payment,data['reference'])
        if order is None or order.provider != provider:
            raise HTTPException(404,'Payment not found')
    return refresh_external_payment(data['reference'])

@app.get('/v1/payments/{pid}')
def payment_status(pid:str,uid:str=Depends(require_user)):
    with SessionLocal() as db:
        p=db.get(Payment,pid)
        if not p or p.user_id!=uid:raise HTTPException(404,'Payment not found')
        return {'id':p.id,'status':p.status,'provider':p.provider,'amount_tzs':p.amount_tzs,'coins':p.coins}

@app.post('/v1/dev/payments/{pid}/settle',dependencies=[Depends(admin)])
def dev_settle(pid:str,x_demo_key:Annotated[str|None,Header()]=None):
    if not DEMO_MODE or PAYMENT_MODE!='demo':raise HTTPException(404,'Not found')
    if not x_demo_key or not hmac.compare_digest(x_demo_key,DEMO_KEY):raise HTTPException(403,'Demo settlement authorization required')
    with writing() as db:
        p,credited=settle_payment(db,pid,f'demo-{pid}')
        return {'status':p.status,'credited':credited}

class DemoTopup(BaseModel):
    # Allows end-to-end testing of the demo on an isolated test server; never available in production.
    pass

@app.post('/v1/dev/me/demo-topup')
def dev_user_topup(uid:str=Depends(require_user)):
    if not DEMO_MODE or PAYMENT_MODE!='demo':raise HTTPException(404,'Not found')
    with writing() as db:
        u=get_locked_user(db,uid)
        pid=str(uuid.uuid4())
        db.add(Payment(id=pid,user_id=uid,status='pending',provider='demo',amount_tzs=PACK_TZS,coins=PACK_COINS))
        db.flush()
        settle_payment(db,pid,f'demo-{pid}')
        return {'id':pid,'status':'paid','balance':u.balance,'demo':True}

def fetch_google_purchase(package_name: str, purchase_token: str) -> dict:
    """Use v2 Play Developer API; credentials stay server-side, never in Flutter."""
    from google.auth import default
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account

    scope = ['https://www.googleapis.com/auth/androidpublisher']
    inline_json = os.getenv('GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', '').strip()
    if inline_json:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(inline_json), scopes=scope)
    else:
        credentials, _ = default(scopes=scope)
    credentials.refresh(GoogleRequest())
    url = (f'https://androidpublisher.googleapis.com/androidpublisher/v3/'
           f'applications/{package_name}/purchases/productsv2/tokens/{purchase_token}')
    response = httpx.get(url, headers={'Authorization': f'Bearer {credentials.token}'}, timeout=15)
    response.raise_for_status()
    return response.json()


class PlayVerification(BaseModel):
    product_id: str = Field(min_length=1,max_length=128)
    purchase_token: str = Field(min_length=8,max_length=4096)

@app.post('/v1/billing/play/verify')
def verify_google_play(req:PlayVerification,uid:str=Depends(require_user)):
    if 'play' not in enabled_modes():raise HTTPException(404,'Not found')
    pkg=os.getenv('GOOGLE_PLAY_PACKAGE','')
    product=os.getenv('GOOGLE_PLAY_PRODUCT_ID','coins_30_tzs_1000')
    if req.product_id!=product or not pkg:raise HTTPException(400,'Wrong product')
    if os.getenv('APP_ENV') == 'production':
        with SessionLocal() as db:
            if not verified_email(db, uid):raise HTTPException(403,'Verified email required')
    try:
        info = fetch_google_purchase(pkg, req.purchase_token)
    except Exception as exc:
        raise HTTPException(503,'Play purchase verification unavailable') from exc
    state = info.get('purchaseStateContext', {}).get('purchaseState')
    if state != 'PURCHASED':
        raise HTTPException(402,'Purchase not eligible for credit')
    items = info.get('productLineItem', [])
    if len(items) != 1 or items[0].get('productId') != product:
        raise HTTPException(400,'Play product does not match this coin package')
    # MVP supports exactly one 30-coin pack per purchase token.
    if int(items[0].get('quantity', 1)) != 1:
        raise HTTPException(409,'Multi-quantity purchases require a separate fulfillment path')
    bound = info.get('obfuscatedExternalAccountId')
    if bound is not None and str(bound) != uid:
        raise HTTPException(409,'Play purchase is bound to another account')
    # Binding order to signed-in user prevents replay to a second account.
    ref='google:'+hashlib.sha256(req.purchase_token.encode()).hexdigest()
    with writing() as db:
        prior=db.scalar(select(Payment).where(Payment.provider_transaction_id==ref))
        if prior:
            if prior.user_id!=uid:raise HTTPException(409,'Purchase already used by another account')
            return {'status':'paid','credited':False,'id':prior.id}
        get_locked_user(db,uid)
        pid=str(uuid.uuid4())
        db.add(Payment(id=pid,user_id=uid,provider='play',status='pending',amount_tzs=PACK_TZS,coins=PACK_COINS))
        db.flush()
        p,credited=settle_payment(db,pid,ref)
        return {'status':p.status,'credited':credited,'id':p.id}

class NewShow(BaseModel):
    id: str=Field(pattern='^[a-z0-9-]{3,48}$')
    title:str=Field(min_length=2,max_length=120)
    synopsis:str=Field(min_length=10,max_length=1000)
    genre:str=Field(max_length=64)
    accent:str=Field(default='#BD396A',pattern='^#[0-9A-Fa-f]{6}$')
    poster_url:str|None=None

@app.post('/v1/admin/shows',dependencies=[Depends(admin)])
def create_show(data:NewShow):
    with writing() as db:
        if db.get(Show,data.id):raise HTTPException(409,'Show already exists')
        s=Show(**data.model_dump());db.add(s)
        return show_payload(s)

class NewEpisode(BaseModel):
    number:int=Field(ge=1,le=10000)
    title:str=Field(min_length=2,max_length=120)
    duration_seconds:int=Field(ge=1,le=900)
    filename:str|None=None

@app.post('/v1/admin/shows/{sid}/episodes',dependencies=[Depends(admin)])
def create_episode(sid:str,data:NewEpisode):
    with writing() as db:
        if not db.get(Show,sid):raise HTTPException(404,'Show missing')
        eid=f'{sid}-{data.number}'
        if db.get(Episode,eid):raise HTTPException(409,'Episode already exists')
        if data.filename:
            if Path(data.filename).name!=data.filename or not data.filename.endswith('.mp4'):
                raise HTTPException(422,'Only simple .mp4 filenames allowed')
            if object_storage.enabled():
                if not object_storage.exists(data.filename):
                    raise HTTPException(422,'Video missing from R2')
            elif not (VIDEO_DIR/data.filename).is_file():
                raise HTTPException(422,'Video file missing on server')
        e=Episode(id=eid,show_id=sid,**data.model_dump());db.add(e)
        return {'id':eid,'number':e.number}


@app.put('/v1/admin/episodes/{eid}/video',dependencies=[Depends(admin)])
async def upload_episode_video(eid:str, video:UploadFile=File(...)):
    """Protected content ingestion for initial deployment. Later move to object storage + CDN."""
    if os.getenv('APP_ENV') == 'production' and not object_storage.enabled():
        raise HTTPException(409,'Upload to Bunny Stream instead; local server video files are not durable')
    if not video.filename or not video.filename.lower().endswith('.mp4'):
        raise HTTPException(422,'An .mp4 video is required')
    with SessionLocal() as db:
        ep=db.get(Episode,eid)
        if ep is None:raise HTTPException(404,'Episode not found')
    max_bytes=150*1024*1024
    temp_path=VIDEO_DIR / f'.{uuid.uuid4()}.upload'
    video_name=f'{uuid.uuid4()}.mp4'
    final_path=VIDEO_DIR / video_name
    total=0
    try:
        with temp_path.open('xb') as out:
            while True:
                chunk=await video.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>max_bytes:raise HTTPException(413,'Video exceeds 150MB')
                out.write(chunk)
        # ISO BMFF/MP4 file-type box near the beginning.
        with temp_path.open('rb') as input_file:
            head=input_file.read(32)
        if total<100 or b'ftyp' not in head[4:16]:
            raise HTTPException(422,'Invalid MP4 file')
        try:
            probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                '-of','default=noprint_wrappers=1:nokey=1',str(temp_path)],
                capture_output=True,text=True,timeout=15,check=True)
            duration=max(1,int(float(probe.stdout.strip())))
        except (subprocess.CalledProcessError,ValueError,OSError,subprocess.TimeoutExpired):
            raise HTTPException(422,'MP4 could not be decoded by ffprobe')
        if duration>900:raise HTTPException(422,'Video is longer than 15 minutes')
        if object_storage.enabled():
            try:
                object_storage.upload(temp_path, video_name)
            except Exception as exc:
                raise HTTPException(503, 'Video upload to R2 failed; episode unchanged') from exc
        else:
            temp_path.replace(final_path)
        with writing() as db:
            ep=db.get(Episode,eid)
            ep.filename=video_name
            ep.duration_seconds=duration
        return {'episode_id':eid,'filename':video_name,'duration_seconds':duration,'bytes':total}
    finally:
        temp_path.unlink(missing_ok=True)
        await video.close()

@app.post('/v1/admin/episodes/{eid}/bunny-init',dependencies=[Depends(admin)])
def bunny_init(eid: str):
    """Create a Bunny video slot without holding DB locks during remote requests."""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if ep is None: raise HTTPException(404, 'Episode missing')
        if ep.bunny_video_id:
            return {'episode_id': eid, 'bunny_video_id': ep.bunny_video_id,
                    'library_id': bunny_stream.library_id(), 'existing': True}
        title = f'{ep.show_id} / Episode {ep.number} / {ep.title}'
    try:
        details = bunny_stream.create(title)
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503, 'Could not create Bunny Stream video') from exc
    with writing() as db:
        ep = db.get(Episode, eid)
        if ep is None: raise HTTPException(404, 'Episode missing')
        if not ep.bunny_video_id:
            ep.bunny_video_id = details['guid']
        assigned = ep.bunny_video_id
    return {'episode_id': eid, 'bunny_video_id': assigned,
            'library_id': bunny_stream.library_id(), 'existing': assigned != details['guid']}


class BunnyLink(BaseModel):
    video_id: str = Field(min_length=36, max_length=36)


@app.post('/v1/admin/episodes/{eid}/bunny-link',dependencies=[Depends(admin)])
def bunny_link_existing(eid: str, data: BunnyLink):
    """Link a video uploaded via Bunny dashboard, after verifying its video ID/library."""
    if not bunny_stream.valid_id(data.video_id):
        raise HTTPException(422, 'Invalid Bunny video GUID')
    try:
        remote = bunny_stream.status(data.video_id)
        if remote.get('guid', '').lower() != data.video_id.lower() or str(
                remote.get('videoLibraryId')) != bunny_stream.library_id():
            raise HTTPException(422, 'Video not in the configured Bunny library')
    except bunny_stream.BunnyError as exc:
        raise HTTPException(503, 'Cannot verify Bunny video') from exc
    with writing() as db:
        ep = db.get(Episode, eid)
        if not ep: raise HTTPException(404, 'Episode missing')
        other = db.scalar(select(Episode).where(Episode.bunny_video_id == data.video_id,
                                                Episode.id != eid))
        if other: raise HTTPException(409, 'Video already linked to another episode')
        ep.bunny_video_id = data.video_id
    return {'episode_id': eid, 'bunny_video_id': data.video_id,
            'ready': remote.get('status') == 4}


@app.get('/v1/admin/episodes/{eid}/bunny-status',dependencies=[Depends(admin)])
def bunny_encoding_status(eid: str):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep: raise HTTPException(404, 'Episode missing')
        if not ep.bunny_video_id: raise HTTPException(409, 'No Bunny video assigned')
        try:
            result = bunny_stream.status(ep.bunny_video_id)
        except bunny_stream.BunnyError as exc:
            raise HTTPException(503, 'Unable to retrieve Bunny status') from exc
        return {'id': eid, 'status': result.get('status'), 'ready': result.get('status') == 4,
                'length': result.get('length'), 'encode_progress': result.get('encodeProgress')}


@app.get('/v1/admin/stats',dependencies=[Depends(admin)])
def admin_stats():
    with SessionLocal() as db:
        return {'users':db.scalar(select(func.count(User.id))),
            'shows':db.scalar(select(func.count(Show.id))),
            'episodes':db.scalar(select(func.count(Episode.id))),
            'unlocks':db.scalar(select(func.count(Entitlement.episode_id))),
            'paid_orders':db.scalar(select(func.count(Payment.id)).where(Payment.status=='paid')),
            'gross_tzs':db.scalar(select(func.coalesce(func.sum(Payment.amount_tzs),0)).where(Payment.status=='paid'))}

# Server-rendered admin is mounted after public API routes to keep secrets out of Flutter.
from .admin_web import router as admin_router
app.include_router(admin_router)
