#!/usr/bin/env bash
# Example: API_URL=https://api.example.com ADMIN_API_KEY=... ./scripts/publish_episode.sh the-last-promise-1 /path/episode1.mp4
set -euo pipefail
: "${API_URL:?Required HTTPS API_URL}" "${ADMIN_API_KEY:?Required ADMIN_API_KEY}"
EP_ID="${1:?episode id missing}"; FILE="${2:?movie .mp4 missing}"
curl --fail-with-body --show-error --request PUT \
  --header "X-Admin-Key: $ADMIN_API_KEY" \
  --form "video=@${FILE};type=video/mp4" \
  "${API_URL%/}/v1/admin/episodes/${EP_ID}/video"
printf '\n'
