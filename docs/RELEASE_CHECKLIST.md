# Android publishing checklist

[ ] Product's final brand name, registered package name and app icon approved
[ ] Real content: audio mix, 9:16 master videos, 60-90 seconds, episode cliffhangers, creative ownership & licenses
[ ] App privacy policy, terms/refund policy, copyright procedure, age rating, Play Data Safety
[ ] Phone/social verified sign-in and customer support account recovery
[ ] Production PostgreSQL database, encrypted backups, tested restore and monitoring
[ ] HTTPS API domain, production secrets and firewall/rate limiting
[ ] Play Console: enable Google Play Developer API, create consumable item, set taxes/local prices, create service account
[ ] Upload release AAB signed with your upload key; verify Play App Signing, store listing, screenshots and testing track
[ ] Run device QA: poor network, lost connection, close/reopen app, rapidly unlock 10 times, cancelled/failed/pending/refunded purchases
[ ] Verify 8 free then paid 9+ across all shows, no duplicate charges after network retry
[ ] Validate purchase after uninstall/login on another device; keep purchase history
[ ] For direct APK ClickPass, verify real sandbox API, signatures, reconciliation, retries and 1000 TZS credited exactly once
[ ] Run load, penetration, DRM/leak review, accessibility and privacy tests
[ ] Validate crash-free startup with install from Play testing track
