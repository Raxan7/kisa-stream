#!/usr/bin/env bash
# Build the Flutter PWA from canonical source, preserving the existing generated project.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$ROOT/kisa_android_build}"
API="${API_BASE_URL:?Set API_BASE_URL to the public HTTPS FastAPI URL (or local http://localhost:8000)}"
MODE="${BILLING_MODE:-clickpesa}"
if [[ "$API" != https://* && "$API" != http://localhost:* && "$API" != http://127.0.0.1:* ]]; then
  echo 'Refusing insecure API_BASE_URL. Use HTTPS in production.' >&2; exit 1
fi
if ! command -v flutter >/dev/null; then echo 'Flutter SDK not installed' >&2; exit 1; fi
mkdir -p "$TARGET"
if [[ -f "$TARGET/pubspec.yaml" ]]; then
  backup="$ROOT/.kisa-backups/pwa-$(date -u +%Y%m%d-%H%M%S)"
  mkdir -p "$backup"
  cp -a "$TARGET/lib" "$TARGET/web" "$TARGET/pubspec.yaml" "$backup/" 2>/dev/null || true
  echo "Existing app backed up: $backup"
fi
# This preserves Android native files, signing settings and additional platforms.
(cd "$TARGET" && flutter create --platforms=web,android . >/dev/null)
cp -a "$ROOT/flutter_app/lib/." "$TARGET/lib/"
cp -a "$ROOT/flutter_app/test/." "$TARGET/test/"
cp "$ROOT/flutter_app/pubspec.yaml" "$TARGET/pubspec.yaml"
cp "$ROOT/flutter_app/analysis_options.yaml" "$TARGET/analysis_options.yaml"
cp -a "$ROOT/flutter_app/web/." "$TARGET/web/"
(cd "$TARGET" && flutter pub get && dart format lib test && flutter analyze --no-fatal-infos && flutter test && flutter build web --release \
  --dart-define="API_BASE_URL=$API" --dart-define="BILLING_MODE=$MODE")
cp "$ROOT/config/cloudflare/_headers" "$ROOT/config/cloudflare/_redirects" "$TARGET/build/web/"
echo "Build ready: $TARGET/build/web"
echo "Publish: npx wrangler pages deploy '$TARGET/build/web' --project-name kisa-stream"
