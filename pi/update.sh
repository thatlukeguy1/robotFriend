#!/usr/bin/env bash
# Get the latest code and restart Riley's body, then show the log (Ctrl+C to stop watching).
#   bash ~/robotFriend/pi/update.sh
set -e
cd "$(dirname "$0")/.."
git pull
chmod 600 pi/bolt.env 2>/dev/null || true   # it holds passwords: yours to read only
pi/.venv/bin/pip install -q -r pi/requirements.txt
sudo systemctl restart bolt-body
echo "Restarted. Watching the log (Ctrl+C to stop watching; Riley keeps running):"
journalctl -u bolt-body -f -n 20
