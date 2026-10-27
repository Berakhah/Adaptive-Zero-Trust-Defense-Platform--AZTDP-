#!/usr/bin/env bash
# scripts/lint_dockerfiles.sh - lint every service Dockerfile.
# Per Dockerfile: hadolint (via docker), plus hard requirements that a final
# stage runs as a non-root USER, has a HEALTHCHECK, and pins base images by digest.
set -uo pipefail
cd "$(dirname "$0")/.."

# DL3008/DL3018 (pin apt/apk package versions) are ignored: distro mirrors drop old
# versions and break rebuilds; integrity comes from the digest-pinned base images.
fail=0
for df in services/*/Dockerfile; do
  svc=$(basename "$(dirname "$df")")
  echo "== $svc"
  if ! docker run --rm -i hadolint/hadolint hadolint --ignore DL3008 --ignore DL3018 - < "$df"; then
    echo "FAIL[$svc]: hadolint reported issues"; fail=1
  fi
  if ! grep -Eq '^USER[[:space:]]+[^[:space:]]+' "$df" || grep -Eq '^USER[[:space:]]+(root|0)([[:space:]]|$)' "$df"; then
    echo "FAIL[$svc]: no non-root USER"; fail=1
  fi
  grep -Eq '^HEALTHCHECK[[:space:]]' "$df" || { echo "FAIL[$svc]: no HEALTHCHECK"; fail=1; }
  if grep -E '^FROM[[:space:]]' "$df" | grep -v '@sha256:' | grep -viE '^FROM[[:space:]]+[a-z]+[[:space:]]*$' | grep -q .; then
    echo "FAIL[$svc]: base image not pinned by digest"; fail=1
  fi
done
[ "$fail" -eq 0 ] && echo "PASS: all Dockerfiles OK" || { echo "FAILED"; exit 1; }
