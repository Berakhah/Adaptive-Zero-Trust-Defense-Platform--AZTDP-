#!/bin/sh
# Scheduler: take a backup whenever the newest successful one is older than
# BACKUP_INTERVAL_SECONDS (default 24h). Checking an on-disk marker, not a fixed
# wall-clock slot, means a restart never skips or doubles a backup. A failed run
# is logged and retried after BACKUP_RETRY_SECONDS; the healthcheck turns
# unhealthy once the last success is older than 26h.
set -u
INTERVAL=${BACKUP_INTERVAL_SECONDS:-86400}
RETRY=${BACKUP_RETRY_SECONDS:-900}
MARK=${BACKUP_DIR:-/backups}/.last_success
while :; do
  now=$(date +%s)
  last=$(stat -c %Y "$MARK" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge "$INTERVAL" ]; then
    if ! /backup.sh; then echo "backup: FAILED, retry in ${RETRY}s" >&2; sleep "$RETRY"; continue; fi
  fi
  sleep 300
done
