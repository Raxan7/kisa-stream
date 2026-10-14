# KISA Stream — Flutter PWA + Bunny Stream

**Current release: installable mobile website first, Flutter/Android code retained.**

Start with [`docs/PWA_BUNNY_LAUNCH.md`](docs/PWA_BUNNY_LAUNCH.md). Use `scripts/build_pwa.sh` to compile the installable Flutter Web version, Cloudflare Pages for the static site, FastAPI + Neon for application data, and Bunny Stream for videos. `https://<API_HOST>/admin` is the basic protected production-team workspace.

New payment documentation and final prices have not been supplied. Real money checkout **must remain disabled** (`PAYMENT_MODE=disabled`) until sandbox and reconciliation tests pass. Backend automated tests: **24 passing** in this packaging environment; Flutter/web builds require a local Flutter SDK.

---

# KISA Stream — vertical mini-drama Android application

A self-hosted short-series streaming **engineering demo** built with Flutter and FastAPI. Branding is a provisional demo name; replace it before launch. This repository is an original app, not a copy of DramaBox source code or licensed content.

**Status:** Backend integration tested locally; Flutter source authored but **not compiled in this environment** because Flutter/Android SDK tools are unavailable. No Play Store submission or real ClickPass transaction was performed. A generated Play Store-ready release requires installing Flutter, validating on Android devices, live gateway docs, and Play Console access.

## Scope implemented

| Capability | Details |
|---|---|
| Short dramas | Discover carousel, genre filter, search, show details, episode list |
| Playback | Fullscreen vertical MP4 player, swipe between episodes, autoplay-next, timeline seek, pause, signed playback links, HTTP Range |
| Free episodes | First **8 of each show** free, server-enforced |
| Premium access | From episode 9: **10 coins** per episode; unlock is permanent per account, repeat unlock doesn't deduct twice |
| Token packs | **30 coins per TZS 1,000** (one pack; prices can be edited via business logic) |
| Wallet | Atomic balance/ledger, purchase idempotency, transaction history |
| Monetization | Google Play Billing purchase flow + backend receipt verification, configurable ClickPass external checkout/reconciliation adapter, explicit fake demo coin mode |
| Viewer features | Device guest session, favorites, recently watched, continue watching |
| Creator workflow | Admin-only API to add series/episodes, upload/replace MP4 video, view aggregate metrics |
| Ops | Docker Compose (PostgreSQL), HTTPS Nginx example, CI tests and debug APK build workflow |

### 1. Run API locally

Requires Python >=3.12 (or another supported recent version). From the repo:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env
# For LOCAL DEMO ONLY edit .env and set DEMO_MODE=true, PAYMENT_MODE=demo,
# JWT_SECRET and ADMIN_API_KEY to fresh long random values.
set -a; source .env; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://127.0.0.1:8000/docs and GET /health. Three fictional sample shows are seeded in development, each with 12 episodes. The bundled 5-second MP4 is a **placeholder preview**, not a generated drama or 75-second movie.

### 2. Create Flutter Android project

Requires **Flutter stable with Dart 3.12+**, Android Studio SDK/platform tools, Java and Android emulator or device. On a machine with Flutter installed:

```bash
bash scripts/bootstrap_flutter.sh ./kisa_android_build
cd kisa_android_build
flutter devices
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=BILLING_MODE=demo
```

`10.0.2.2` reaches the host from the standard Android emulator. For a physical device, host the API behind **HTTPS**, then run `--dart-define=API_BASE_URL=https://api.example.com`. The debug manifest allows local emulator HTTP; release does not permit cleartext by default.

To build:

```bash
flutter test
flutter analyze
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=BILLING_MODE=demo
```

Production Play release (requires correct keystore/Play App Signing and Play Console product configuration):

```bash
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://api.example.com \
  --dart-define=BILLING_MODE=play \
  --dart-define=PLAY_PRODUCT_ID=coins_30_tzs_1000
```

The generated **AAB** is submitted to the Play Console testing track manually by an authorized publisher. This project does NOT itself upload it.

### 3. Production backend

```bash
cp .env.production.example .env
# Populate .env with secure secrets, HTTPS BASE_URL, and payment config.
docker compose up -d --build
docker compose ps
curl https://api.example.com/health
```

Reverse proxy to `127.0.0.1:8000` using the example in `config/nginx.example.conf`; issue TLS certificates first. PostgreSQL and media are persisted as Docker volumes. Set `APP_ENV=production`; production startup explicitly rejects demo payment mode and insecure default keys. **Do not run production without SSL and backups.** Restrict admin endpoints by IP/VPN in the proxy in addition to `X-Admin-Key`.

### 4. Publish movies

Development sample shows are only demo seed records; production starts with an empty catalogue.

```bash
API_URL=https://api.example.com
ADMIN_API_KEY='YOUR_SECRET'

curl -X POST "$API_URL/v1/admin/shows" \
 -H "X-Admin-Key: $ADMIN_API_KEY" -H 'Content-Type: application/json' \
 -d '{"id":"love-and-ashes","title":"Love and Ashes","synopsis":"A secret threatens two families on the day of their wedding.","genre":"Romance","accent":"#C84672"}'

curl -X POST "$API_URL/v1/admin/shows/love-and-ashes/episodes" \
 -H "X-Admin-Key: $ADMIN_API_KEY" -H 'Content-Type: application/json' \
 -d '{"number":1,"title":"The Wedding","duration_seconds":75}'

API_URL="$API_URL" ADMIN_API_KEY="$ADMIN_API_KEY" \
 ./scripts/publish_episode.sh love-and-ashes-1 /path/to/episode-01.mp4

curl "$API_URL/v1/admin/stats" -H "X-Admin-Key: $ADMIN_API_KEY"
```

Upload format is MP4/H.264/AAC preferred, vertically framed **1080x1920**, target **60–90 seconds** per original episode, max 150 MB, verified using ffprobe. This MVP uses authenticated Range streaming. When traffic increases, move videos to object storage + CDN with signed HLS URLs and adaptive bitrate. Provide subtitles/captions and have content rights for all movies.

### 5. Payment deployment choices

**Google Play build** (`BILLING_MODE=play`, server `PAYMENT_MODE=play`): define the consumable item ID `coins_30_tzs_1000` in Play Console. Configure the price in Play Console; displayed store price comes from Google (may vary by tax/region). Enable Google Play Developer API, grant service account purchase verification permissions, and mount service-account credentials to `/run/secrets/kisa/service-account.json`. Server verifies purchase state via Android Publisher API and credits each purchase token only once. Flutter consumes the purchase only after backend verification. End-to-end purchases must be tested using Play Console internal testing / licensed testers.

**Direct APK / eligible alternative-billing build** (`BILLING_MODE=clickpass`, server `PAYMENT_MODE=clickpass`): details in `docs/CLICKPASS.md`. Backend creates a pending purchase; opens the provider checkout using external browser; the server alone verifies the successful order, TZS amount, order reference and transaction ID before adding coins. Client polls for confirmation; webhook triggers reconciliation. **ClickPass's precise HTTP contract and credentials are not present in the brief**, so the adapter needs configured request/response mappings and real sandbox verification. Do not substitute ClickPesa specs: these are not confirmed to be the same product.

**Demo** (`BILLING_MODE=demo`, server `PAYMENT_MODE=demo`, `DEMO_MODE=true`): UI button credits 30 explicitly fake coins; no actual money is collected. Production refuses this mode.

Current Play payments policy generally requires Google Play Billing for Play-distributed in-app virtual currency and digital entertainment, unless an applicable registered alternative billing program/exception applies. Do not submit the direct-ClickPass build as an ordinary Play app without checking eligibility.

### 6. Tests

```bash
cd backend && python -m pytest -q
# Android SDK machine: run scripts/bootstrap_flutter.sh then inside project:
flutter analyze && flutter test
```

Backend tests cover free/paid access, unlock idempotency, wallet arithmetic, forged/no-login requests, unauthorized settlements, progress restrictions, signed MP4 and Range requests, concurrent unlock race, favorites, admin access and video validation. Tests are automated; external provider acceptance, Dart compilation and real-device behavior still need release QA.

### 7. Known launch requirements

- Replace demo guest identity with **phone/OTP or social sign-in account restoration** before charging real customers, otherwise users can lose purchases when device data is deleted.
- Set up Play listing, privacy policy, app/data-safety disclosures, developer verification, content classification, and release signing. Movies must be licensed, and your actual creators must supply them.
- Add observability (APM/structured logs), backups and tested restore, WAF/rate limits, error reporting, load tests, CDN/DRM for valuable content, refund/chargeback reconciliation, and schema migrations for successive versions.
- Demo placeholder videos intentionally repeat; these are only to exercise playback and paywall integration.

The code is designed as a head start for a production implementation, not a certification that the app is already safe to take real money or ready for store approval.
