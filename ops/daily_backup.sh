#!/bin/bash
# Daily File From Link backup (host cron): build the package, send it to
# the owner via the bot (local Bot API), prune old archives.
# Cron appends stdout to /var/log/ffl-backup.log.
set -u
REPO_DIR=/opt/file-from-link
cd "$REPO_DIR" || exit 1
OUT=$(/usr/bin/python3 ops/daily_backup.py) || { echo "$OUT"; echo "backup build FAILED"; exit 1; }
echo "$OUT"
ARCHIVE=$(echo "$OUT" | sed -n 's/^ARCHIVE=//p')
CAPTION=$(echo "$OUT" | sed -n 's/^CAPTION=//p')
[ -n "$ARCHIVE" ] || { echo "no ARCHIVE in builder output"; exit 1; }
# The shared volume is /data inside containers. Refresh the sender script
# in the running bot container first (it is also baked into the image on
# every deploy, so this is only a bootstrap for the current container).
CID=$(/usr/bin/docker compose ps -q bot 2>/dev/null)
[ -n "$CID" ] && /usr/bin/docker cp app/send_backup.py "$CID:/code/app/send_backup.py" 2>/dev/null || true
/usr/bin/docker compose exec -T bot python -m app.send_backup "/data/backups/$(basename "$ARCHIVE")" "$CAPTION"
