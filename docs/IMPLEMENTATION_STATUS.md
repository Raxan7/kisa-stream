# KISA PWA + Bunny implementation status

**Status: code delivered for web PWA tester build. Cloud services require account configuration and live verification.**

Implemented:
- Flutter UI retained and web/mobile PWA assets supplied, HTTPS install manifest, dark brand icons, offline status page, SPA fallback, Cloudflare Pages deployment build script.
- Bunny Stream backend integration for creating slots, linking existing Bunny videos, checking encoding status, signing short-lived iframe playback URLs after free/paid entitlement checks.
- Bunny web embedded player with official Player.js `ended` callback for next-episode progression, manual next and signed playback.
- Persistent relational user/entitlement/wallet business logic preserved; existing PostgreSQL schema migrator adds nullable Bunny GUID without deleting data.
- Verified email OTP identity, basic shared-DB throttling, account recovery login for purchased content, paid checkout guarded behind verified email in production.
- Protected server-rendered admin dashboard at `/admin` with CSRF and HttpOnly session cookies: create draft series and episodes, link Bunny GUIDs, publish/unpublish, view inventory.
- Direct Bunny upload CLI and Cloudflare build+deploy procedure. Google Play Billing implementation retained for a future native Android release.
- 24 backend tests passed locally including existing wallet/payment regression tests and new PWA/Bunny/auth/admin tests.

Not verified or not activated:
- Flutter PWA build/unit/widget tests and device testing (the packaging container has no Flutter SDK; the upgrade includes a build script and GitHub CI workflow).
- Live Bunny upload, token-auth setting, HLS rebuffer performance on physical phones.
- Cloudflare Pages, Neon, Render and SMTP user account configuration; no production URLs or secrets were provided.
- ClickPesa transaction API, final pricing and actual checkout reconciliation; intentionally `PAYMENT_MODE=disabled` for production until documentation is supplied.
- Native Android Bunny player; a placeholder informs Android users while web works. Native Play Billing code remains separate.
- Full-featured resumable-upload dashboard (current dashboard links Bunny dashboard video IDs; upload CLI uses whole-file retries).
- Legal, account deletion, monitoring/analytics dashboards and content-rights signoff before general release.

See `docs/PWA_BUNNY_LAUNCH.md` for deployment and acceptance checklist. Never claim the external services were deployed or live payments certified.
