import os
import json
import time
import threading
import subprocess
import numpy as np
import pyaudio
from flask import Flask, request, render_template_string
from gpiozero import Button
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# --- Persistent Settings File ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "visualizer_settings.json")

def load_settings():
    defaults = {"mic_gain": 1.5, "curve_exponent": 1.00}
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            defaults["mic_gain"] = float(data.get("mic_gain", defaults["mic_gain"]))
            defaults["curve_exponent"] = float(data.get("curve_exponent", defaults["curve_exponent"]))
    except Exception:
        pass
    return defaults

def save_settings(mic_gain, curve_exponent):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump({
                "mic_gain": round(float(mic_gain), 2),
                "curve_exponent": round(float(curve_exponent), 2)
            }, f)
    except Exception as e:
        print(f"Could not save settings: {e}")

settings = load_settings()
MIC_GAIN = settings["mic_gain"]
CURVE_EXPONENT = settings["curve_exponent"]

# --- Shutdown State ---
shutdown_requested = False

# --- Web Control Interface (Flask) ---
web_app = Flask(__name__)

GAIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>JB Audio Visualizer Control</title>
    <style>
        body { font-family: Arial, sans-serif; background: #121212; color: #ffffff; padding: 20px; max-width: 420px; margin: auto; text-align: center; }
        h2 { color: #00bfff; margin-bottom: 5px; }
        p.sub { color: #aaa; font-size: 14px; margin-top: 0; }
        .card { background: #1e1e1e; border: 1px solid #333; border-radius: 10px; padding: 22px 20px; margin-top: 18px; }
        .val { font-size: 34px; font-weight: bold; color: #00bfff; margin: 8px 0 16px 0; }
        .hint { font-size: 12px; color: #888; margin-bottom: 12px; }
        input[type=range] { width: 100%; accent-color: #00bfff; height: 8px; cursor: pointer; }
        .presets { display: flex; justify-content: space-between; gap: 8px; margin-top: 16px; }
        button { flex: 1; padding: 10px; border: none; border-radius: 6px; background: #2c2c2c; color: #fff; font-weight: bold; cursor: pointer; font-size: 13px; }
        button:hover { background: #00bfff; color: #000; }
        .status { margin-top: 14px; font-size: 13px; color: #4caf50; height: 18px; }
        .power-btns { display: flex; gap: 10px; margin-top: 12px; }
        .btn-restart { background: #d97706; color: #fff; padding: 12px; }
        .btn-restart:hover { background: #f59e0b; color: #000; }
        .btn-shutdown { background: #dc2626; color: #fff; padding: 12px; }
        .btn-shutdown:hover { background: #ef4444; color: #fff; }
    </style>
</head>
<body>
    <h2>JB Audio Visualizer</h2>
    <p class="sub">Live Sensitivity, Curve & Power Control</p>

    <div class="card">
        <div>Microphone Gain</div>
        <div class="val" id="gainDisplay">{{ "%.2f"|format(gain) }}x</div>
        <input type="range" id="gainSlider" min="0.1" max="5.0" step="0.05" value="{{ gain }}" oninput="updateGain(this.value)">
        <div class="presets">
            <button onclick="setGainPreset(0.5)">Low (0.5x)</button>
            <button onclick="setGainPreset(1.5)">Default (1.5x)</button>
            <button onclick="setGainPreset(3.0)">High (3.0x)</button>
        </div>
    </div>

    <div class="card">
        <div>Response Curve</div>
        <div class="hint">Lower (less than 1) = lively &bull; 1.0 = linear &bull; Higher (greater than 1) = punchy beats only</div>
        <div class="val" id="curveDisplay">{{ "%.2f"|format(curve) }}</div>
        <input type="range" id="curveSlider" min="0.40" max="2.00" step="0.05" value="{{ curve }}" oninput="updateCurve(this.value)">
        <div class="presets">
            <button onclick="setCurvePreset(0.65)">Lively (0.65)</button>
            <button onclick="setCurvePreset(1.00)">Linear (1.00)</button>
            <button onclick="setCurvePreset(1.45)">Punchy (1.45)</button>
        </div>
    </div>

    <div class="status" id="statusMsg"></div>

    <div class="card">
        <div style="margin-bottom: 10px; color: #ccc;">Device Power</div>
        <div class="power-btns">
            <button class="btn-restart" onclick="sendPower('reboot')">Reboot Pi</button>
            <button class="btn-shutdown" onclick="sendPower('shutdown')">Safe Shutdown</button>
        </div>
    </div>

    <script>
        let saveTimer = null;

        function showSaved(text, color='#4caf50') {
            const msg = document.getElementById('statusMsg');
            msg.style.color = color;
            msg.innerText = text;
            clearTimeout(msg._hideTimer);
            msg._hideTimer = setTimeout(() => { msg.innerText = ''; }, 1800);
        }

        function pushSettings() {
            const g = parseFloat(document.getElementById('gainSlider').value);
            const c = parseFloat(document.getElementById('curveSlider').value);
            clearTimeout(saveTimer);
            saveTimer = setTimeout(() => {
                fetch('/set_params', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ gain: g, curve: c })
                })
                .then(r => r.json())
                .then(data => {
                    showSaved('Saved: Gain ' + data.gain.toFixed(2) + 'x | Curve ' + data.curve.toFixed(2));
                });
            }, 120);
        }

        function setGainPreset(val) {
            document.getElementById('gainSlider').value = val;
            updateGain(val);
        }

        function updateGain(val) {
            document.getElementById('gainDisplay').innerText = parseFloat(val).toFixed(2) + 'x';
            pushSettings();
        }

        function setCurvePreset(val) {
            document.getElementById('curveSlider').value = val;
            updateCurve(val);
        }

        function updateCurve(val) {
            document.getElementById('curveDisplay').innerText = parseFloat(val).toFixed(2);
            pushSettings();
        }

        function sendPower(action) {
            const label = action === 'reboot' ? 'reboot the Raspberry Pi' : 'safely shut down the Raspberry Pi';
            if (!confirm('Are you sure you want to ' + label + '?')) return;
            fetch('/' + action, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showSaved(data.message, '#f59e0b');
                });
        }
    </script>
</body>
</html>
"""

@web_app.route("/", methods=["GET"])
def control_page():
    return render_template_string(GAIN_HTML, gain=MIC_GAIN, curve=CURVE_EXPONENT)

@web_app.route("/set_params", methods=["POST"])
def set_params():
    global MIC_GAIN, CURVE_EXPONENT
    data = request.get_json(silent=True) or {}
    if "gain" in data:
        MIC_GAIN = max(0.1, min(10.0, float(data["gain"])))
    if "curve" in data:
        CURVE_EXPONENT = max(0.30, min(2.50, float(data["curve"])))
    save_settings(MIC_GAIN, CURVE_EXPONENT)
    return {"status": "ok", "gain": MIC_GAIN, "curve": CURVE_EXPONENT}

@web_app.route("/shutdown", methods=["POST"])
def remote_shutdown():
    global shutdown_requested
    shutdown_requested = True
    return {"status": "ok", "message": "Playing shutdown animation & halting Pi..."}

@web_app.route("/reboot", methods=["POST"])
def remote_reboot():
    def delayed_reboot():
        time.sleep(1.5)
        subprocess.run(["sudo", "reboot"])
    threading.Thread(target=delayed_reboot, daemon=False).start()
    return {"status": "ok", "message": "Rebooting Raspberry Pi..."}

def start_web_server():
    try:
        web_app.run(host="0.0.0.0", port=80, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Web server error: {e}")

# Start web UI in a background thread
threading.Thread(target=start_web_server, daemon=True).start()

# --- Physical Shutdown Button Configuration ---
# Wired between SCL (GPIO 3) and GND
def on_shutdown_press():
    global shutdown_requested
    shutdown_requested = True

shutdown_btn = Button(3, pull_up=True, bounce_time=0.1)
shutdown_btn.when_pressed = on_shutdown_press

# --- Matrix Configuration ---
options = RGBMatrixOptions()
options.rows = 16
options.cols = 32
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'adafruit-hat'
options.drop_privileges = False
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# --- Audio Configuration ---
CHUNK = 2048
RATE = 44100

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)

# --- Helper: Display Scrolling Text ---
def display_message(canvas, matrix, font, text, seconds=9.0, abort_on_shutdown=True):
    pos = canvas.width
    start_time = time.time()
    text_color = graphics.Color(0, 10, 255)
    while time.time() - start_time < seconds:
        if abort_on_shutdown and shutdown_requested:
            break
        canvas.Clear()
        length = graphics.DrawText(canvas, font, pos, 12, text_color, text)
        pos -= 1
        if (pos + length < 0):
            pos = canvas.width
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.045)
    return canvas

# --- Helper: Check Active Wi-Fi Connection & IP Address ---
def get_wifi_info():
    """Returns (ssid, ip_address) when connected to a router, or (None, None) if offline."""
    try:
        res = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"],
            capture_output=True, text=True, timeout=2
        )
        ssid = None
        for line in res.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "wlan0" and parts[1] == "connected":
                conn_name = parts[2].strip()
                if conn_name and conn_name != "Hotspot":
                    ssid = conn_name
                    break
        if not ssid:
            return None, None

        ip_res = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        ip_addr = ""
        for token in ip_res.stdout.split():
            if "." in token and not token.startswith("127.") and token != "10.42.0.1":
                ip_addr = token
                break
        return ssid, ip_addr
    except Exception:
        pass
    return None, None

# --- Helper: Wi-Fi Status Scroll (1 pass if connected, up to 60s if offline) ---
def display_wifi_status(canvas, matrix, font, max_offline_seconds=60.0):
    pos = canvas.width
    start_time = time.time()
    last_check = 0
    wifi_ssid, ip_addr = get_wifi_info()
    text_color = graphics.Color(0, 10, 255)

    while True:
        if shutdown_requested:
            break

        if not wifi_ssid and (time.time() - last_check >= 2.0):
            wifi_ssid, ip_addr = get_wifi_info()
            last_check = time.time()
            if wifi_ssid:
                pos = canvas.width

        if wifi_ssid:
            if ip_addr:
                text = f"Connected to WiFi: {wifi_ssid} ({ip_addr})"
            else:
                text = f"Connected to WiFi: {wifi_ssid}"
        else:
            if time.time() - start_time >= max_offline_seconds:
                break
            text = "No WiFi - Setup: 10.42.0.1"

        canvas.Clear()
        length = graphics.DrawText(canvas, font, pos, 12, text_color, text)
        pos -= 1

        if (pos + length < 0):
            if wifi_ssid:
                break
            pos = canvas.width

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.045)

    return canvas

# --- Color Helper ---
def get_color(y, max_y):
    if y < max_y * 0.5: return (0, 255, 0)
    elif y < max_y * 0.8: return (255, 255, 0)
    else: return (255, 0, 0)

# --- Helper: Shutdown Bar-Drop & Message Sequence ---
def run_shutdown_sequence(canvas, matrix, font):
    print("Shutdown triggered! Playing shutdown animation...")
    bar_heights = [16.0] * 11
    dot_heights = [16.0] * 11
    dot_hold = 15

    while any(h > 0 for h in bar_heights) or any(d > 0 for d in dot_heights):
        canvas.Clear()
        for i in range(11):
            bar_heights[i] = max(0.0, bar_heights[i] - 0.25)
            if dot_hold > 0:
                dot_hold -= 1
            else:
                dot_heights[i] = max(0.0, dot_heights[i] - 0.18)

            actual_height = int(bar_heights[i])
            peak_y_val = int(dot_heights[i])
            col1 = i * 3
            col2 = col1 + 1

            for y in range(16 - actual_height, 16):
                r, g, b = get_color(15 - y, 16)
                canvas.SetPixel(col1, y, r, g, b)
                canvas.SetPixel(col2, y, r, g, b)

            if peak_y_val > actual_height and peak_y_val > 0:
                y_coord = 16 - peak_y_val
                if 0 <= y_coord <= 15:
                    canvas.SetPixel(col1, y_coord, 0, 10, 255)
                    canvas.SetPixel(col2, y_coord, 0, 10, 255)

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.03)

    canvas = display_message(canvas, matrix, font, "Safe to shutdown", seconds=6.0, abort_on_shutdown=False)
    canvas.Clear()
    matrix.SwapOnVSync(canvas)

    stream.stop_stream()
    stream.close()
    p.terminate()
    subprocess.run(["sudo", "shutdown", "-h", "now"])

# Load Font
font = graphics.Font()
font.LoadFont(os.path.join(SCRIPT_DIR, "5x8.bdf"))

# 1. Initial Splash Screen (9 seconds)
if not shutdown_requested:
    print("Loading Splash Screen...")
    canvas = display_message(canvas, matrix, font, "Audio Visualizer 1.0 by JB Audio", seconds=9.0)

# 2. Wi-Fi & IP Status Display (scrolls once when connected; waits up to 60s if offline)
if not shutdown_requested:
    print("Checking Wi-Fi status...")
    canvas = display_wifi_status(canvas, matrix, font, max_offline_seconds=60.0)

# --- Visualizer Variables ---
manual_bins = [2, 4, 6, 9, 14, 21, 32, 48, 74, 115, 180, 320]

HISTORY_LENGTH = 50
band_histories = [[] for _ in range(11)]
band_target_max = [170000.0] * 11
BAND_MIN_FLOORS = [105000, 92000, 80000, 68000, 56000, 46000, 38000, 32000, 26000, 22000, 18000]

RISE_SMOOTHING = 0.34
FALL_SPEED = 0.60
PEAK_HOLD_FRAMES = 12
PEAK_FALL_SPEED = 0.4

# Initial Peak Drop-In Animation
smoothed_heights = [16.0] * 11
peak_dots = [16.0] * 11
peak_wait = [PEAK_HOLD_FRAMES] * 11

print("Listening (Visualizer Active)...")

try:
    while not shutdown_requested:
        # 1. Grab Audio
        raw_data = stream.read(CHUNK, exception_on_overflow=False)
        data = np.frombuffer(raw_data, dtype=np.int16)

        # 2. Math & Frequency Band Calculation
        fft_data = np.abs(np.fft.rfft(data)) * MIC_GAIN

        canvas.Clear()
        raw_energies = []

        for i in range(11):
            start_bin = manual_bins[i]
            end_bin = manual_bins[i+1]

            slice_data = fft_data[start_bin:end_bin]
            # Gentle upward tilt (1.0x on bass up to 1.8x on top treble) to counter mic roll-off
            freq_tilt = 1.0 + (i * 0.08)
            band_energy = ((np.max(slice_data) * 0.65) + (np.mean(slice_data) * 0.35)) * freq_tilt
            raw_energies.append(band_energy)

            if band_energy > BAND_MIN_FLOORS[i]:
                band_histories[i].append(band_energy)
                if len(band_histories[i]) > HISTORY_LENGTH:
                    band_histories[i].pop(0)
                band_target_max[i] = max(BAND_MIN_FLOORS[i], np.percentile(band_histories[i], 90))
            else:
                band_target_max[i] = max(BAND_MIN_FLOORS[i], band_target_max[i] * 0.985)

        # Blend 35% global ceiling + 65% per-band ceiling so all 11 frequencies stay active
        global_ceiling = max(band_target_max)

        # 3. Draw the 11 Bars & Peak Dots
        for i in range(11):
            effective_max = (global_ceiling * 0.35) + (band_target_max[i] * 0.65)
            norm = min(1.0, max(0.0, raw_energies[i] / effective_max))
            curved_level = norm ** CURVE_EXPONENT
            target_height = int(round(curved_level * 16))
            target_height = max(0, min(16, target_height))

            if target_height >= smoothed_heights[i]:
                smoothed_heights[i] += (target_height - smoothed_heights[i]) * RISE_SMOOTHING
            else:
                smoothed_heights[i] = max(0, smoothed_heights[i] - FALL_SPEED)

            if smoothed_heights[i] >= peak_dots[i]:
                peak_dots[i] = smoothed_heights[i]
                peak_wait[i] = PEAK_HOLD_FRAMES
            else:
                if peak_wait[i] > 0:
                    peak_wait[i] -= 1
                else:
                    peak_dots[i] = max(0, peak_dots[i] - PEAK_FALL_SPEED)

            actual_height = int(smoothed_heights[i])
            peak_y_val = int(peak_dots[i])

            col1 = i * 3
            col2 = col1 + 1

            for y in range(16 - actual_height, 16):
                r, g, b = get_color(15 - y, 16)
                canvas.SetPixel(col1, y, r, g, b)
                canvas.SetPixel(col2, y, r, g, b)

            if peak_y_val > actual_height and peak_y_val > 0:
                y_coord = 16 - peak_y_val
                if 0 <= y_coord <= 15:
                    canvas.SetPixel(col1, y_coord, 0, 10, 255)
                    canvas.SetPixel(col2, y_coord, 0, 10, 255)

        canvas = matrix.SwapOnVSync(canvas)

    if shutdown_requested:
        run_shutdown_sequence(canvas, matrix, font)

except KeyboardInterrupt:
    print("Stopping visualizer...")
    stream.stop_stream()
    stream.close()
    p.terminate()
