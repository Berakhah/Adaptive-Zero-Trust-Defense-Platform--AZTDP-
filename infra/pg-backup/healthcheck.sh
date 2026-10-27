#!/bin/sh
# Healthy while the newest successful backup is < 26h old (24h cadence + slack).
# start_period covers the first backup after a fresh deploy.
MARK=${BACKUP_DIR:-/backups}/.last_success
[ -f "$MARK" ] && [ $(( $(date +%s) - $(stat -c %Y "$MARK") )) -lt 93600 ]
