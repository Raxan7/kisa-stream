#!/usr/bin/env bash
# Creates an Android scaffold with the installed Flutter SDK, then injects this app.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$ROOT/kisa_android_build}"
if ! command -v flutter >/dev/null 2>&1; then
  echo 'Flutter SDK not found. Install Flutter stable + Android SDK first: https://docs.flutter.dev/get-started/install' >&2
  exit 1
fi
if [[ -e "$TARGET" ]]; then
  echo "Target exists: $TARGET. Choose an unused target path." >&2
  exit 1
fi
flutter create --platforms android --org com.kisastream --project-name kisa_stream "$TARGET"
cp -a "$ROOT/flutter_app/lib/." "$TARGET/lib/"
cp -a "$ROOT/flutter_app/test/." "$TARGET/test/"
cp "$ROOT/flutter_app/pubspec.yaml" "$TARGET/pubspec.yaml"
cp "$ROOT/flutter_app/analysis_options.yaml" "$TARGET/analysis_options.yaml"
python3 - "$TARGET" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])/'android/app/src/main/AndroidManifest.xml'
s=p.read_text()
s=s.replace('<application', '<uses-permission android:name="android.permission.INTERNET"/>\n    <application',1)
p.write_text(s)
# Allow development HTTP to the Android emulator only. NEVER on release main manifest.
p=Path(sys.argv[1])/'android/app/src/debug/AndroidManifest.xml'
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:usesCleartextTraffic="true" />
</manifest>\n''')
PY
(cd "$TARGET" && flutter pub get && flutter analyze --no-fatal-infos && flutter test)
echo "Flutter project ready: $TARGET"
echo "Android emulator example: cd '$TARGET' && flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=BILLING_MODE=demo"
