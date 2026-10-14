#!/usr/bin/env bash
set -euo pipefail

# These values are compiled into the published web app.
# Set API_BASE_URL in Cloudflare Pages -> Settings -> Environment variables.
: "${API_BASE_URL:?Set API_BASE_URL to your PUBLIC HTTPS FastAPI URL in Cloudflare Pages settings}"
if [[ "${API_BASE_URL}" != https://* ]]; then
  echo "ERROR: API_BASE_URL must start with https:// for the public PWA." >&2
  exit 1
fi
BILLING_MODE="${BILLING_MODE:-clickpesa}"

# Install Flutter SDK
git clone --depth 1 --branch stable \
  https://github.com/flutter/flutter.git \
  /tmp/flutter-sdk

# Add Flutter to PATH
export PATH="/tmp/flutter-sdk/bin:$PATH"

# Check Flutter
flutter --version

# Download project dependencies
flutter pub get

# Build Flutter web application
flutter build web --release --no-wasm-dry-run \
  --dart-define="API_BASE_URL=${API_BASE_URL%/}" \
  --dart-define="BILLING_MODE=${BILLING_MODE}"

# Ensure Pages deploys our caching rules.
cp web/_headers build/web/_headers
