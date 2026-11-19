# JB Audio Visualizer (16x32 RGB LED Matrix)

A real-time, 11-band frequency audio visualizer built for Raspberry Pi OS Lite (Bookworm) and the Adafruit RGB Matrix Bonnet. Includes a captive-portal Wi-Fi setup hotspot, a mobile-friendly web dashboard for live sensitivity and response-curve tuning, and a physical/remote safe-shutdown animation sequence.

## Features
- **11-Band Real-Time Spectrum Analyzer:** Edge-to-edge 2-pixel-wide columns with 1-pixel gaps, classic green/yellow/red level bars, and royal-blue `(0, 10, 255)` peak-hold indicators.
- **Hybrid Auto-Gain & Frequency Tilt:** Combines global and per-band rolling peak detection with high-frequency presence compensation so bass, mids, and treble stay active without room-noise jitter.
- **Captive Wi-Fi Setup Portal (`wifi_portal.py`):** If no known Wi-Fi network is found within 20 seconds of boot, broadcasts an open **`JB-Audio-Setup`** hotspot (`http://10.42.0.1`) to configure Wi-Fi from a phone.
- **Startup Splash & Network Readout:** Scrolls `"Audio Visualizer 1.0 by JB Audio"` followed by a single-pass readout of the connected Wi-Fi SSID and IPv4 address.
- **Live Web Control Dashboard (`http://<PI_IP>`):** Adjust **Microphone Gain** (`0.1x–5.0x`) and **Response Curve** (`0.40–2.00`) in real time with persistent JSON storage, plus remote **Reboot Pi** and **Safe Shutdown** buttons.
- **Hardware Safe Shutdown:** Pressing the momentary button on **SCL (GPIO 3)** triggers a slow full-bar drop animation, scrolls `"Safe to shutdown"`, and halts the Pi cleanly.

## Hardware & Wiring

### Parts List
- Raspberry Pi (3B+, 4, or Zero 2 W running Raspberry Pi OS Lite Bookworm)
- Adafruit RGB Matrix Bonnet for Raspberry Pi (PID: 3211)
- 16x32 RGB LED Matrix Panel, HUB75 (PID: 420)
- Mini USB Microphone
- 5V 4A Switching Power Supply (barrel jack for the Bonnet)
- Momentary Push Button & 3mm/5mm LED with 220Ω–330Ω current-limiting resistor

### Bonnet Breakout Wiring
| Component | Bonnet Pad | BCM Pin | Notes |
| :--- | :--- | :--- | :--- |
| **Shutdown Button** | `SCL` & `GND` | GPIO 3 | Normally open momentary switch |
| **Power Status LED** | `SDA` & `GND` | GPIO 2 | Turns off once OS halt completes (`active_low`) |

## Installation

1. Flash **Raspberry Pi OS Lite (64-bit or 32-bit Bookworm)** and connect via SSH.
2. Clone this repository and copy your `5x8.bdf` bitmap font into the project directory:
   ```bash
   git clone [https://github.com/](https://github.com/)<YOUR_USERNAME>/jb-audio-visualizer.git
   cd jb-audio-visualizer
   cp /tmp/rpi-rgb-led-matrix/fonts/5x8.bdf .
