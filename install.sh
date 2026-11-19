#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing JB Audio Visualizer from $REPO_DIR..."

# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-dev python3-venv python3-pip portaudio19-dev git build-essential network-manager

# 2. Create Python virtual environment and install Python packages
python3 -m venv "$REPO_DIR/env"
"$REPO_DIR/env/bin/pip" install --upgrade pip
"$REPO_DIR/env/bin/pip" install -r "$REPO_DIR/requirements.txt"

# 3. Clone and compile rpi-rgb-led-matrix Python bindings
if [ ! -d "/tmp/rpi-rgb-led-matrix" ]; then
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git /tmp/rpi-rgb-led-matrix
fi
cd /tmp/rpi-rgb-led-matrix
make build-python PYTHON="$REPO_DIR/env/bin/python"
sudo make install-python PYTHON="$REPO_DIR/env/bin/python"
cd "$REPO_DIR"

# 4. Configure /boot/firmware/config.txt for status LED on GPIO 2 (SDA)
CONFIG_FILE="/boot/firmware/config.txt"
if [ -f "$CONFIG_FILE" ]; then
    sudo sed -i 's/^dtoverlay=gpio-shutdown/#dtoverlay=gpio-shutdown/' "$CONFIG_FILE"
    if ! grep -q "dtoverlay=gpio-poweroff,gpiopin=2,active_low" "$CONFIG_FILE"; then
        echo "dtoverlay=gpio-poweroff,gpiopin=2,active_low" | sudo tee -a "$CONFIG_FILE" > /dev/null
    fi
fi

# 5. Install and enable systemd services with dynamic paths
sed "s|/home/pi/jb-audio-visualizer|$REPO_DIR|g" "$REPO_DIR/systemd/visualizer.service" | sudo tee /etc/systemd/system/visualizer.service > /dev/null
sed "s|/home/pi/jb-audio-visualizer|$REPO_DIR|g" "$REPO_DIR/systemd/wifi-portal.service" | sudo tee /etc/systemd/system/wifi-portal.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable visualizer.service wifi-portal.service

echo "Installation complete! Reboot your Raspberry Pi with: sudo reboot"
