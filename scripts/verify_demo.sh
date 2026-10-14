#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
python -m pytest -q
python -m compileall -q app
printf '\nBackend demo verified. Flutter build requires Flutter SDK and Android SDK.\n'
