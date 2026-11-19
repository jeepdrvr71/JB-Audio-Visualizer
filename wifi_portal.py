import time
import threading
import subprocess
from flask import Flask, request, render_template_string

app = Flask(__name__)

HOTSPOT_SSID = "JB-Audio-Setup"
HOTSPOT_CON_NAME = "Hotspot"
LOG_FILE = "/tmp/wifi_portal.log"

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>JB Audio Wi-Fi Setup</title>
    <style>
        body { font-family: Arial, sans-serif; background: #121212; color: #ffffff; padding: 20px; max-width: 400px; margin: auto; }
        h2 { color: #00bfff; text-align: center; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        select, input, button { width: 100%; padding: 12px; margin-top: 8px; border-radius: 6px; border: none; font-size: 16px; box-sizing: border-box; }
        select, input { background: #222; color: #fff; border: 1px solid #444; }
        button { background: #00bfff; color: #000; font-weight: bold; margin-top: 25px; cursor: pointer; }
        button:hover { background: #0099cc; }
        .msg { margin-top: 20px; padding: 12px; background: #1e3a1e; border: 1px solid #2e6b2e; border-radius: 6px; text-align: center; }
    </style>
</head>
<body>
    <h2>JB Audio Wi-Fi Setup</h2>
    {% if message %}
        <div class="msg">{{ message }}</div>
    {% else %}
        <form method="POST">
            <label for="ssid">Select Wi-Fi Network:</label>
            <select name="ssid" id="ssid" required>
                {% for net in networks %}
                    <option value="{{ net }}">{{ net }}</option>
                {% endfor %}
            </select>
            <label for="manual_ssid">Or Type Hidden Network Name:</label>
            <input type="text" name="manual_ssid" placeholder="Optional">
            <label for="password">Wi-Fi Password:</label>
            <input type="password" name="password" placeholder="Enter password" required>
            <button type="submit">Connect & Save</button>
        </form>
    {% endif %}
</body>
</html>
"""

def is_connected():
    res = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] == "wlan0" and parts[1] == "connected" and parts[2] != HOTSPOT_CON_NAME:
            return True
    return False

def get_available_networks():
    subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True)
    time.sleep(2)
    res = subprocess.run(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"], capture_output=True, text=True)
    ssids = []
    for line in res.stdout.splitlines():
        clean = line.strip()
        if clean and clean != HOTSPOT_SSID and clean not in ssids:
            ssids.append(clean)
    return ssids if ssids else ["No networks found"]

def start_hotspot():
    subprocess.run(["nmcli", "connection", "delete", HOTSPOT_CON_NAME], capture_output=True)
    subprocess.run([
        "nmcli", "device", "wifi", "hotspot",
        "ifname", "wlan0",
        "con-name", HOTSPOT_CON_NAME,
        "ssid", HOTSPOT_SSID
    ], check=True)
    subprocess.run(["nmcli", "connection", "modify", HOTSPOT_CON_NAME, "remove", "wifi-sec"], capture_output=True)
    subprocess.run(["nmcli", "connection", "up", HOTSPOT_CON_NAME], capture_output=True)

def switch_to_wifi(ssid, password):
    time.sleep(2)
    log(f"Starting switch to SSID: '{ssid}'")

    # 1. Tear down and delete the Hotspot profile
    subprocess.run(["nmcli", "connection", "down", HOTSPOT_CON_NAME], capture_output=True)
    subprocess.run(["nmcli", "connection", "delete", HOTSPOT_CON_NAME], capture_output=True)

    # 2. Delete any existing profiles matching this SSID to prevent conflicts
    res_list = subprocess.run(["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"], capture_output=True, text=True)
    for line in res_list.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == ssid:
            log(f"Removing old profile '{ssid}' ({parts[1]})")
            subprocess.run(["nmcli", "connection", "delete", parts[1]], capture_output=True)

    # 3. Cycle Wi-Fi radio cleanly out of AP mode and rescan
    subprocess.run(["nmcli", "radio", "wifi", "off"], capture_output=True)
    time.sleep(2)
    subprocess.run(["nmcli", "radio", "wifi", "on"], capture_output=True)
    time.sleep(4)
    subprocess.run(["nmcli", "device", "wifi", "rescan", "ifname", "wlan0"], capture_output=True)
    time.sleep(4)

    # 4. Build an explicit WPA-PSK connection profile and bring it up
    add_res = subprocess.run([
        "nmcli", "connection", "add",
        "type", "wifi",
        "ifname", "wlan0",
        "con-name", ssid,
        "ssid", ssid,
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.psk", password,
        "connection.autoconnect", "yes"
    ], capture_output=True, text=True)
    log(f"Profile add: {add_res.stdout.strip()} {add_res.stderr.strip()}")

    up_res = subprocess.run(["nmcli", "connection", "up", ssid], capture_output=True, text=True)
    log(f"Connection up stdout: {up_res.stdout.strip()}")
    if up_res.stderr:
        log(f"Connection up stderr: {up_res.stderr.strip()}")

cached_networks = []

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        chosen_ssid = request.form.get("manual_ssid", "").strip() or request.form.get("ssid")
        password = request.form.get("password")
        log(f"Form submitted for '{chosen_ssid}' (password length: {len(password)})")

        t = threading.Thread(target=switch_to_wifi, args=(chosen_ssid, password), daemon=False)
        t.start()

        return render_template_string(
            HTML_PAGE,
            message=f"Connecting to '{chosen_ssid}'... Watch the LED matrix for confirmation."
        )

    return render_template_string(HTML_PAGE, networks=cached_networks)

if __name__ == "__main__":
    with open(LOG_FILE, "w") as f:
        f.write("=== Wi-Fi Portal Boot ===\n")

    log("Waiting 20 seconds for existing Wi-Fi connection...")
    for _ in range(20):
        if is_connected():
            log("Already connected to Wi-Fi. Exiting setup portal.")
            exit(0)
        time.sleep(1)

    log("No Wi-Fi found. Scanning networks and starting setup hotspot...")
    cached_networks = get_available_networks()
    start_hotspot()
    log(f"Hotspot '{HOTSPOT_SSID}' active at http://10.42.0.1")
    app.run(host="0.0.0.0", port=80)
