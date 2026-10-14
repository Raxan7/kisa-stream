#!/usr/bin/env bash
set -euo pipefail

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
flutter build web --release
