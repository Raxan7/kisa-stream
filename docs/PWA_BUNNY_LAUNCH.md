# KISA Stream — Flutter PWA / Bunny Stream / Cloudflare release

**Release state:** application code and automated Python tests prepared. Flutter build, public-cloud live testing, real video upload and ClickPesa activation must be performed with your accounts. The new billing documentation and final prices have **not** been provided; real purchases stay disabled until verified.

## What the components do

- Flutter remains the **single application UI** for web and future Android. Web is installable through HTTPS as a PWA.
- Cloudflare Pages hosts static `build/web` only; it does **not** host FastAPI, PostgreSQL, or MP4s.
- FastAPI serves the `/v1/` endpoints and `/admin` admin workspace. Keep its instance reachable over public HTTPS.
- Neon PostgreSQL holds users, email identity, verification codes, series, episodes, paid entitlements, wallets and order status. Never deploy production on SQLite or Render's temporary disk.
- Bunny Stream encodes and delivers videos. Videos uploaded via Bunny's dashboard or `scripts/publish_bunny.py` are linked to episode rows using a Bunny GUID. Bunny handles adaptive streaming; the FastAPI server **never proxies Bunny video bytes**.
- The existing Google Play Billing adapter is retained for a later native Play build; web will use ClickPesa only after the correct API specification and real payments are verified. Do **not** enable demo credits in production.

## 1. Apply upgrade to the existing KISA project

From downloaded upgrade archive:

```bash
cd ~/Projects/KISA_Stream_Flutter_Android_Demo_Source/kisa-stream
python3 ~/Downloads/KISA_PWA_Bunny_Upgrade/installer.py .
```

The installer backs up modified source files in `.kisa-backups/`, syncs the generated Flutter `lib/` files if `kisa_android_build/` exists, and leaves Android signing, DB files and secrets unchanged.

## 2. Local backend smoke test

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
# First-time local demo only; NOT production
DEMO_MODE=true PAYMENT_MODE=demo SEED_DEMO=true \
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000 \
EMAIL_DEV_CONSOLE=true uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/health` should return HTTP 200. `http://localhost:8000/docs` has the API docs locally; the public server disables docs.

### Existing Postgres migration

The new `episodes.bunny_video_id` column must be added to existing databases. Docker executes the **additive** `backend/migrate.py` before importing the app, safely and idempotently. Run `python migrate.py` manually before deploying new code if you host FastAPI without Docker. Keep a database backup first. For a new Neon DB, the main app creates the new tables on first startup.

## 3. Neon PostgreSQL database

1. Create project in https://console.neon.tech. Obtain connection string with TLS (`sslmode=require`).
2. Set `DATABASE_URL` **only in backend host environment** (no credentials in Flutter or GitHub).
3. Start FastAPI and check `/health`; create a new guest and restart backend; `/v1/me` using that token should still return the same user.
4. Configure backups and regular exports before real paid transactions. Database plan limits can change; check actual quotas.

## 4. Bunny Stream video library

1. Create a Bunny Stream Video Library (Bunny dashboard > Stream). Copy **Video Library ID** and **Library API Key** (the *library key*, not account API key).
2. Configure backend secrets `BUNNY_STREAM_LIBRARY_ID`, `BUNNY_STREAM_API_KEY`, `BUNNY_STREAM_TOKEN_KEY`. The signing key is the Bunny Stream **Embed View Token Authentication** key, **not** the upload API key.
3. **Enable Embed View Token Authentication** under your Stream library Security settings. Add your real site hostname (without `https://`) to Allowed Domains; include any pages.dev preview hostname you intend to test. Use `strict-origin-when-cross-origin` referrer policy. Keep the embed signing key backend-only.
4. In the admin workspace `https://<API_HOST>/admin`, log in with `ADMIN_DASHBOARD_PASSWORD` (separate from `ADMIN_API_KEY`). Create a **draft** series and episodes. Keep episodes drafts until videos finish processing.
5. Option A (easiest for production team): upload each MP4 in Bunny Stream dashboard, copy each **Video GUID**, paste it in the admin `Link a Bunny video` form, then select Publish after transcoding completes.
6. Option B (technical uploader, no Render bandwidth or max body size): use the command below to create a Bunny slot and upload directly from your Ubuntu machine:

```bash
# Install script dependencies in a Python venv: pip install httpx
export KISA_API=https://YOUR_API_HOST
read -rsp 'KISA admin API key: ' KISA_ADMIN_KEY; echo; export KISA_ADMIN_KEY
read -rsp 'Bunny Stream library API key: ' BUNNY_STREAM_API_KEY; echo; export BUNNY_STREAM_API_KEY
python3 scripts/publish_bunny.py --episode secret-wedding-1 --file ~/Movies/secret-wedding/01.mp4
# Or link video uploaded in dashboard:
python3 scripts/publish_bunny.py --episode secret-wedding-1 --link BUNNY_VIDEO_GUID
```

This CLI retries whole-file direct PUT uploads after temporary failures. For very large videos or unstable connections, upload through Bunny's dashboard/TUS resumable upload instead. Do not upload MP4s to Cloudflare Pages, your API server disk, or PostgreSQL.

Admin workspace functions today: create series/episode, link Bunny GUID, publish/unpublish, view episode status, logout. It intentionally **does not** expose the Bunny library API key in browser scripts. The separate CLI provides direct file upload until the full polished dashboard supports presigned TUS transfers. An administrator password of at least 20 characters is required; protect `/admin` further with Cloudflare Access if available.

### Video production export suggestions

- Vertical 9:16 MP4, H.264 video + AAC sound. Normal short-form episodes are around 60–90 seconds.
- Avoid excessive source bitrate; Bunny will transcode adaptive streaming variants.
- Use a unique episode title and number; maintain a clean folder per series.
- Publish a batch of free episodes first, then test the episode-9 unlock.
- Every published series needs licensed content, rights clearance and cover artwork.

## 5. Public FastAPI API hosting

Easiest route: deploy this project's `render.yaml` from GitHub on Render (free tier for staging). Free Render instances can sleep, causing cold starts; consider an always-on VM for the real launch. Configure every secret in the hosting dashboard, **not** `.env` in git. Set:

```env
APP_ENV=production
DEMO_MODE=false
SEED_DEMO=false
PAYMENT_MODE=disabled
DATABASE_URL=postgresql+psycopg://...NEON.../...?sslmode=require
JWT_SECRET=<long random secret>
ADMIN_API_KEY=<another long random secret>
ADMIN_DASHBOARD_PASSWORD=<a separate long password>
BASE_URL=https://YOUR_API_HOST
CORS_ORIGINS=https://YOUR-PROJECT.pages.dev,https://YOUR_CUSTOM_DOMAIN
BUNNY_STREAM_LIBRARY_ID=<video library id>
BUNNY_STREAM_API_KEY=<library video API key>
BUNNY_STREAM_TOKEN_KEY=<embed token authentication key>
SMTP_HOST=<smtp host>
SMTP_PORT=465
SMTP_FROM=<sender address>
SMTP_USERNAME=<smtp username>
SMTP_PASSWORD=<smtp password>
```

Use `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` three times for independent secret values. **Never paste these values into ChatGPT or place them in Dart defines**.

The production environment refuses local SQLite, demo credits and short development JWT/admin keys. There is a browser-OTP signup path: guests can browse freely; before real purchases users must verify email and then can sign in on another device. Configure SMTP before inviting paid users. OTP requests are rate-limited, verification codes are hashed, expire in 10 min, and have an attempt limit. Additional Cloudflare/WAF rate limits should be enabled for public access.

## 6. Build the Flutter PWA on Ubuntu

Requires an installed Flutter stable SDK (your machine already has one). Run from repository root:

```bash
cd ~/Projects/KISA_Stream_Flutter_Android_Demo_Source/kisa-stream
export API_BASE_URL=https://YOUR_API_HOST
export BILLING_MODE=clickpesa
bash scripts/build_pwa.sh ./kisa_android_build
```

The script preserves Android native files/signing, backs up generated Flutter files, adds web support, syncs the canonical sources, runs `dart format`, `flutter analyze --no-fatal-infos`, `flutter test`, and `flutter build web --release`. The output is `kisa_android_build/build/web/` with PWA manifest, icons, offline fallback, Bunny iframe bridge, `_headers` and `_redirects`.

**Note:** The published app expects HTTPS and won't accept plain HTTP API in production. No real ClickPesa payment will be enabled until your gateway specifications are validated. `PAYMENT_MODE=disabled` makes the wallet purchase button inactive.

### Test the built site locally

```bash
cd kisa_android_build/build/web
python3 -m http.server 3000
```

Open `http://localhost:3000`. Set the backend CORS allowlist accordingly. For a real install prompt and signed Bunny playback use the public **HTTPS** URL.

## 7. Deploy Flutter static files to Cloudflare Pages

Visit https://dash.cloudflare.com > Workers & Pages. Create a **Direct Upload** Pages project named `kisa-stream` (or your preferred available name). Direct Upload can't later be converted to Git-integrated Pages; keep this in mind if you prefer CI deployment instead. Use Wrangler for uploads:

```bash
npm install -g wrangler
wrangler login
# create project if you haven't created it in dashboard:
wrangler pages project create kisa-stream
wrangler pages deploy kisa_android_build/build/web --project-name kisa-stream
```

Your Pages deployment gets an HTTPS `*.pages.dev` URL. Add custom domain via Pages > Custom domains and add **the exact deployed hostname** to the FastAPI `CORS_ORIGINS` and Bunny Allowed Domains. **Do not** configure a Bunny signed URL or upload key in Cloudflare Pages environment variables; it stays on the API server.

## 8. Test on real phones (acceptance checklist)

1. Open the Pages HTTPS URL on Android Chrome and iPhone Safari. Install via Chrome browser menu / Safari Share > Add to Home Screen.
2. Launch from the home-screen icon: standalone layout, correct KISA icon and dark splash.
3. Load catalogue, open a series and stream an actually uploaded/published Bunny video, including on 3G/4G. Confirm quality adapts without extended buffering.
4. Verify the Bunny embed gets HTTP 200; troubleshoot 403 via Library Allowed Domains, token signing key and expiry.
5. Verify `episodes 1–8` are free and episode 9 returns HTTP 402 without previous entitlement.
6. Verify email OTP sign-in (real SMTP) and that reopening on another phone restores identity and previously unlocked content.
7. Resume progress, favorites, share a `/series/<slug>` link, follow it into the installed PWA, and watch automatic next-episode progression at video end.
8. Confirm no purchase button can charge money in staging while `PAYMENT_MODE=disabled`.
9. Review API logs, Bunny Stream metrics, Cloudflare traffic, and database logs after a tester session.

## 9. Payments — staged release policy

The **provisional** values are `FREE_EPISODES=8`, `EPISODE_COST_COINS=10`, `TOKEN_PACK_TZS=1000`, `TOKEN_PACK_COINS=30` on the backend. Override them there only after reviewing your actual pricing. Flutter reads values from `/v1/me`; it doesn't hardcode the wallet price. Existing data/entitlement logic stays intact.

Until the ClickPesa **specific API documentation, merchant webhook format, keys and pricing** are supplied and validated, keep `PAYMENT_MODE=disabled` in production. Existing `clickpesa.py` is an adapter template, **not** proof of successful live integration. Verify initiation, status, complete/failed/pending/duplicate transactions and reconciliation under a provider sandbox before enabling.

Future Play edition remains a **separate compiled distribution** with `BILLING_MODE=play`, Google Play Billing and backend verification. No ClickPesa checkout is exposed in the Play-distributed edition. The native Android Bunny player needs its own integration; this release's Bunny iframe player targets Flutter Web/PWA.

## 10. Remaining production signoffs

- Compile and physically test the Flutter PWA on Ubuntu/Android Chrome/iPhone Safari (Flutter SDK is not installed in the packaging environment).
- Configure Bunny account and ingest *real* encoded MP4s, test playback and transcoding status.
- Configure Neon, SMTP, and public HTTPS FastAPI; verify migrations and database retention.
- Test actual mobile network performance, buffering and swipe/auto-advance. The signed Bunny embed is integrated via official Player.js events; manual next is available as a fallback.
- Receive and integrate your ClickPesa documentation, credentials and final pricing, then perform live sandbox reconciliation before enabling paid sales.
- Publish Terms, Privacy Policy, support contact, rights clearance, account deletion request path, monitoring and operational backup plan before broad release.

**Do not advertise production paid checkout as live until the above signoffs are complete.**
