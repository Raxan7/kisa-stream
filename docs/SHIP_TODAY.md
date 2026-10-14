# KISA: ship to Google Play internal testers today

This deployment kit targets **Render Free API + Neon PostgreSQL + private Cloudflare R2**. It updates the original KISA FastAPI source; it does NOT create live hosting accounts, deploy to your Google account, or upload an AAB automatically.

### Status

- Local API tests: see `python -m pytest -q` in `backend/`.
- Google Play verified backend purchase handling: implemented and unit-tested with mocked API responses, **not a real Play purchase**.
- Direct ClickPesa: isolated adapter scaffolding, **NOT real-transaction verified or ready for live charges**. Needs merchant credentials and response/webhook mappings (see below).
- Video: private R2 uploads and 20-minute presigned playback URLs (unit-tested with mocked storage), **not exercised against your own R2 credentials**.
- Existing UI: maintained. Existing demo API data is not migrated into the new database unless you do it manually.

## Step A — create cloud resources

1. Visit https://neon.tech and create a Free PostgreSQL database named `kisa`. Copy the `DATABASE_URL` with `sslmode=require` from Neon. The API accepts `postgresql://`, `postgres://`, and `postgresql+psycopg://` URLs.
2. Visit https://dash.cloudflare.com, activate R2 (may require a payment method). Create **private** bucket `kisa-videos`. Create R2 API credentials with object read/write permissions scoped to this bucket. Record **Account ID, Access Key ID, Secret Access Key**. Keep bucket **private**, do not turn on Public Bucket or r2.dev.
3. Put this project into a new **private GitHub repository**. Do not commit `.env`, cloud keys, or service-account JSON. Verify with `git status` before pushing.
4. Visit https://dashboard.render.com and choose **New > Blueprint** pointing to your repo; accept `render.yaml` and `free` plan. Enter environment secrets in Render. Alternatively create a `Web Service` with Docker runtime, repo root `backend/`, plan Free, health check `/health`. If using manual Docker deployment, the Dockerfile listens on the `PORT` environment variable.

## Step B — configure Render environment

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `postgresql://...` URL from Neon, including `sslmode=require` |
| `BASE_URL` | `https://<your-service>.onrender.com` exact public address, no trailing slash |
| `JWT_SECRET` | 64+ random characters, never in git |
| `ADMIN_API_KEY` | Separate 64+ random characters, never in git |
| `VIDEO_STORAGE` | `r2` |
| `R2_ACCOUNT_ID` | From Cloudflare dashboard |
| `R2_BUCKET` | `kisa-videos` (or your bucket name) |
| `R2_ACCESS_KEY_ID` | Bucket-scoped R2 access key |
| `R2_SECRET_ACCESS_KEY` | Bucket-scoped R2 secret key |
| `SEED_DEMO` | `false` (real pilot catalogue is empty until movies uploaded) |
| `DEMO_MODE` | `false` |
| `PAYMENT_MODE` | `play` **first** |
| `GOOGLE_PLAY_PACKAGE` | `com.kisastream.kisa_stream` unless changing Android applicationId |
| `GOOGLE_PLAY_PRODUCT_ID` | `coins_30_tzs_1000` |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Full Play Developer API service-account JSON as a Render **secret** environment variable. Don't expose it to app. |
| `CORS_ORIGINS` | Leave empty for Android-only testers; add exact web frontend origins if needed. |

Neon stores users, episodes, credits, purchases, entitlements, favorites, progress. It is **not** video storage. Render free disks are ephemeral; **never** use SQLite as production storage on Render Free.

Generate distinct secrets on Linux:

```bash
python3 -c 'import secrets;print(secrets.token_hex(48))'
python3 -c 'import secrets;print(secrets.token_hex(48))'
```

Render `render.yaml` can auto-generate both keys. If it does, view the generated `ADMIN_API_KEY` securely in your account; use that key for publishing. Do not send the secrets to other people.

## Step C — smoke-test the deployed backend

```bash
cd kisa-stream
export KISA_API=https://YOUR-RENDER-SERVICE.onrender.com
python3 scripts/smoke_public_api.py
```

Expected: health HTTP 200, guest login, 0 initial coins, and empty catalogue until you publish. Free Render may cold-start for ~1 minute after 15 minutes idle.

## Step D — upload episodes

The creator/producer exports `01.mp4`, `02.mp4`, ... as vertical H.264/AAC 1080x1920 movies, 60–90 seconds each. You, **the admin**, upload them from your Linux computer to the FastAPI admin endpoint; it validates MP4 and sends the file directly to the **private R2 bucket**. Files persist even when Render restarts. Only the backend knows the R2 keys.

```bash
cd kisa-stream
export KISA_API=https://YOUR-RENDER-SERVICE.onrender.com
read -rsp 'KISA admin API key: ' KISA_ADMIN_KEY; echo
export KISA_ADMIN_KEY

python3 scripts/publish_movie.py \
  --id secret-wedding \
  --title 'The Secret Wedding' \
  --synopsis 'Her wedding turns into a mystery when the wrong man appears.' \
  --genre Romance \
  --videos /home/saidi/Movies/secret-wedding
```

Episode filenames must begin with `01`, `02` and so forth. Each episode is capped at 150 MB and 15 minutes server-side. The backend's `ffprobe` validates content. The script can be rerun if interrupted; it replaces already uploaded episodes with new private R2 objects. Note: orphaned old R2 files are not automatically garbage-collected yet.

For a **browser upload UI later**: build a creator/admin dashboard that calls the same protected endpoints and keeps keys on a secure server; do not put the admin key in your distributed Flutter APK or public JavaScript.

## Step E — configure Google Play Billing

1. In Play Console, create your app with **package name `com.kisastream.kisa_stream`** (confirm against `android/app/build.gradle.kts`). Configure payments profile and one-time **consumable** product ID `coins_30_tzs_1000` for **30 coins**. Set TZS 1,000 or desired equivalent in Play Console, and activate it. Actual displayed prices come from Google Play.
2. In Google Cloud, enable **Google Play Android Developer API**. Configure a service account and grant it the required purchase/financial order access in **Play Console > Users and permissions / API access**. Store the JSON only in Render's secret env `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`.
3. Ensure the app has a valid unique package, icon, privacy policy URL, content rights, age rating, data safety form, and secure release upload key. Configure **Play App Signing**.
4. Copy this kit's Flutter app change into your generated project if you want future direct ClickPesa support (see install commands). Add flavors **only once**:

```bash
cd kisa-stream
python3 scripts/add_android_flavors.py ./kisa_android_build
cd kisa_android_build
flutter doctor -v
flutter pub get
flutter analyze
flutter test
flutter build appbundle --flavor play --release \
  --dart-define=API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com \
  --dart-define=BILLING_MODE=play \
  --dart-define=PLAY_PRODUCT_ID=coins_30_tzs_1000
```

Find `build/app/outputs/bundle/playRelease/*.aab`. The build **must be upload-key signed**, not a debug-signed release; see https://docs.flutter.dev/deployment/android#signing-the-app. Upload AAB to **Play Console > Testing > Internal testing**, add tester emails, distribute the Play opt-in link. Licensed testers can test purchases without real charges; install **from Play testing**, not sideloading.

**Account readiness:** If this is a *new personal Play developer account* created after Nov 13, 2023, public production access requires a closed test with **at least 12 testers opted in continuously for 14 days**, and then an application for production access. Internal testing does not need that wait. Official Google instructions: https://support.google.com/googleplay/android-developer/answer/14151465

### Required live Play Billing test

Install app from Google Play test link using a license tester. On coins page, verify `30 Coins` displays the Play-provided price, initiate purchase, complete Google test purchase, verify server credits exactly 30. Unlock episode 9: balance becomes 20. Repeat verification/unlock: balance remains 20. Check in Play Console that purchase can be repurchased after consumption. Validate pending/cancelled purchases do not create credits. **This has not been run with your actual Google Play account yet.**

## Step F — independent direct APK / ClickPesa (later)

- This must be a **separately identifiable binary** (`--flavor direct`, package suffix `.direct`) and never surface ClickPesa purchasing links in Play-distributed builds.
- Flutter direct mode: `--dart-define=BILLING_MODE=clickpesa`.
- Server: after you have verified ClickPesa integration, set `PAYMENT_MODE=play,clickpesa` so the same Neon wallet and catalogue can serve both editions. Backend's ClickPesa gateway adapter is fail-closed until `CLICKPESA_*` values are mapped to your merchant's **actual** Hosted Checkout API contract.
- ClickPesa documentation: https://docs.clickpesa.com/llms.txt. Official docs state live small-value testing instead of a sandbox. Use independently reconciled provider queries before minting coins; never credit from webhooks alone.
- Create a direct-release signing key and `flutter build apk --flavor direct --release --dart-define=API_BASE_URL=... --dart-define=BILLING_MODE=clickpesa`. Sign it independently and distribute it off Play. **Do not enable live direct payments until the provider API and signing are verified.**

## Critical before charging real users

Current KISA uses 90-day **guest device sessions** without account recovery. Someone who clears app data or changes devices can lose access to coins/episodes. This is acceptable only for clearly explained, no-real-charge internal testing. **Add recoverable accounts (e.g., verified phone OTP), refunds/revocations, error reporting, backups and operational monitoring before collecting real money.** Backend unit tests are not substitutes for device-side purchases and end-to-end tests.

## What to share for a launch review

- Render public hostname (no credentials).
- Output of `KISA_API=... python3 scripts/smoke_public_api.py`.
- Screenshot of R2 bucket and Neon connection success (hide keys/passwords).
- Flutter `flutter analyze`, `flutter test`, and Android AAB build logs.
- Play Console product status and test release status (hide financial credentials).

