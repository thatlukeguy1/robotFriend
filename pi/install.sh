#!/usr/bin/env bash
# Installs Bolt's body on a Raspberry Pi and starts it automatically on boot.
# Run it from the robotFriend folder:   bash pi/install.sh
set -euo pipefail
cd "$(dirname "$0")"
PI_DIR="$(pwd)"

echo "== 1/5 System packages (sound library, Python tools)"
sudo apt-get update
sudo apt-get install -y python3-venv python3-gpiozero python3-spidev libportaudio2
sudo raspi-config nonint do_spi 0  # switch on SPI, for the screen

echo "== 2/5 Python environment"
# --system-site-packages lets us use the Pi's own GPIO library for the button.
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps "openwakeword==0.6.0"

echo "== 3/5 Wake word models"
.venv/bin/python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'])"

echo "== 4/5 Settings"
if [ ! -f bolt.env ]; then
    cp bolt.env.example bolt.env
    echo "   Made bolt.env. Check BRAIN_URL in it!"
fi

echo "== 5/5 Start on boot"
sudo tee /etc/systemd/system/bolt-body.service > /dev/null <<SERVICE
[Unit]
Description=Bolt's body (wake word, microphone, speaker)
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$PI_DIR
EnvironmentFile=$PI_DIR/bolt.env
ExecStart=$PI_DIR/.venv/bin/python -m bolt_body.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE
# Let this user start, stop and restart Bolt's body without typing a password,
# and ONLY those three commands: everything else still needs the password.
echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl start bolt-body, /usr/bin/systemctl stop bolt-body, /usr/bin/systemctl restart bolt-body" \
    | sudo tee /etc/sudoers.d/bolt-body > /dev/null
sudo chmod 440 /etc/sudoers.d/bolt-body
sudo visudo -cq || { echo "sudoers check failed: removing the rule"; sudo rm /etc/sudoers.d/bolt-body; }
sudo systemctl daemon-reload
sudo systemctl enable --now bolt-body

echo
echo "Done! Bolt's body is running. Watch it with:  journalctl -u bolt-body -f"
