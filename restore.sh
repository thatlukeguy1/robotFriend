#!/usr/bin/env bash
# Put a backup made by backup.sh back. Riley's brain is stopped while it happens.
#   bash ~/robotFriend/restore.sh ~/riley-backups/riley-2026-11-23_0317.tar.gz
# An encrypted one from Google Drive (.gpg) works too: it asks for the passphrase,
# or uses ~/.config/riley/backup-passphrase if it's there.
# Her memories, personality, reminders, designs, settings, password, keys and HTTPS
# authority are replaced by the backup's. .env is only restored if it's missing here
# (so a newer key you've put in since isn't overwritten).
set -euo pipefail
cd "$(dirname "$0")"
backup="${1:?Which backup? e.g. bash restore.sh ~/riley-backups/riley-2026-11-23_0317.tar.gz}"
[ -f "$backup" ] || { echo "No such file: $backup" >&2; exit 1; }

work="$(mktemp -d)"
stopped=""
# LESSON: a "trap" runs when the script ends, however it ends (even on an error). So if a
# copy fails half way, Riley is still started again, instead of being left switched off.
trap 'rm -rf "$work"; if [ -n "$stopped" ]; then docker compose start bolt https || true; fi' EXIT
if [[ "$backup" == *.gpg ]]; then
    passphrase="${RILEY_BACKUP_PASSPHRASE_FILE:-$HOME/.config/riley/backup-passphrase}"
    if [ -s "$passphrase" ]; then
        gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$passphrase" -d -o "$work/backup.tar.gz" "$backup"
    else
        gpg --quiet -d -o "$work/backup.tar.gz" "$backup"     # asks you for the passphrase
    fi
    backup="$work/backup.tar.gz"
fi
tar -xzf "$backup" -C "$work"
# Check EVERYTHING before stopping Riley, so a bad backup changes nothing.
for part in robot-data caddy-data; do
    [ -d "$work/riley/$part" ] || { echo "That doesn't look like a whole Riley backup (no $part). Nothing changed." >&2; exit 1; }
done
echo "Restoring the backup from $(cat "$work/riley/made-at" 2>/dev/null || echo 'an unknown date')."
read -r -p "This replaces Riley's current memories and settings. Carry on? [y/N] " ok
[ "$ok" = "y" ] || [ "$ok" = "Y" ] || { echo "Nothing changed."; exit 0; }

stopped=yes
docker compose stop bolt https
docker compose cp "$work/riley/robot-data/." bolt:/data
docker compose cp "$work/riley/caddy-data/." https:/data
if [ ! -f .env ] && [ -f "$work/riley/env" ]; then
    (umask 077; cp "$work/riley/env" .env)
    echo "Restored .env too."
fi
docker compose start bolt https
stopped=""
echo "Done. Riley is back as she was at $(cat "$work/riley/made-at" 2>/dev/null || echo 'the backup')."
