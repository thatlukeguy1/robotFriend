#!/usr/bin/env bash
# LESSON: Backing Riley up
# ========================
# Everything that makes Riley HER lives in two Docker volumes, plus .env:
#   robot-data   memories, personality, reminders, face designs, body settings,
#                the login password, the Pi's key
#   caddy-data   the HTTPS certificate authority (lose it, and every device
#                has to learn to trust her again)
#   .env         your Claude API key and Home Assistant token
# This copies them out of the running containers into ONE dated file, keeps
# the newest 14, and (optionally) puts a second copy somewhere else, because a
# backup on the same disk can't survive that disk dying.
#
# The file contains passwords and keys: it's made readable by you only.
# Don't upload it anywhere public.
#
#   bash ~/robotFriend/backup.sh
# Settings (optional, in your environment or the crontab line):
#   RILEY_BACKUP_DIR      where backups go        (default ~/riley-backups)
#   RILEY_BACKUP_COPY_TO  a second place to copy each one (a USB stick, a network drive)
#   RILEY_BACKUP_KEEP     how many to keep        (default 14)
set -euo pipefail
cd "$(dirname "$0")"
DEST="${RILEY_BACKUP_DIR:-$HOME/riley-backups}"
COPY_TO="${RILEY_BACKUP_COPY_TO:-}"
KEEP="${RILEY_BACKUP_KEEP:-14}"
umask 077                                  # everything we make: readable by you only

prune() {   # keep the newest $KEEP backups in a folder
    ls -1t "$1"/riley-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do rm -f -- "$old"; done
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/riley"
docker compose cp bolt:/data "$work/riley/robot-data"
docker compose cp https:/data "$work/riley/caddy-data"
[ -f .env ] && cp .env "$work/riley/env"
date -Iseconds > "$work/riley/made-at"
git rev-parse --short HEAD > "$work/riley/code-version" 2>/dev/null || true

mkdir -p "$DEST"
file="$DEST/riley-$(date +%Y-%m-%d_%H%M).tar.gz"
tar -czf "$file" -C "$work" riley
prune "$DEST"
echo "Backed up to $file ($(du -h "$file" | cut -f1))"

if [ -n "$COPY_TO" ]; then
    if [ -d "$COPY_TO" ] && cp "$file" "$COPY_TO/"; then
        prune "$COPY_TO"
        echo "Second copy in $COPY_TO"
    else
        echo "! Couldn't copy to $COPY_TO (is the USB stick or network drive connected?)" >&2
        exit 1
    fi
fi
