"""
LESSON: Riley's Pi as a Home Assistant device (over MQTT)
=========================================================
MQTT is a "noticeboard" protocol that lots of smart-home things use. One program,
the BROKER (in Home Assistant: the Mosquitto add-on), holds the noticeboard.
Others PUBLISH messages to "topics" (like riley/pi/state) and SUBSCRIBE to the
topics they care about. Home Assistant subscribes, so whatever Riley pins up, it sees.

Two kinds of message are used here:

  * DISCOVERY: once, Riley pins up a description of each sensor under
    homeassistant/... ("there's a sensor called CPU temperature, in °C, read it
    from riley/pi/state"). Home Assistant reads those and creates a "Riley" device
    by itself: no YAML. They're RETAINED (the broker keeps them for anyone who
    arrives later), and sent again whenever Home Assistant restarts.
  * STATE: every 30 seconds, one message with all the readings, as JSON.

And one clever bit, the LAST WILL: when Riley connects, she tells the broker "if
I vanish without saying goodbye, pin up 'offline' for me". So if her program
crashes or the Pi loses power, Home Assistant shows her sensors as unavailable.

The readings come straight from Linux's own files (/proc and /sys): nothing to install
except the MQTT library. Only numbers about the Pi go out, and her state (asleep,
awake, talking): nothing she hears or sees.

Turn it on in pi/bolt.env (see LEARN.md, "Riley's Pi in Home Assistant"):

    MQTT_HOST=192.168.4.x        (Home Assistant's address)
    MQTT_USER=riley
    MQTT_PASSWORD=...            (never paste it anywhere else)
"""

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

PREFIX = "homeassistant"            # where Home Assistant looks for discovery messages
BASE = "riley/pi"
STATE, AVAILABLE = f"{BASE}/state", f"{BASE}/status"
NODE = "riley_pi"

# key: (name, unit, device_class, icon, diagnostic?)
SENSORS = {
    "cpu": ("CPU use", "%", None, "mdi:cpu-64-bit", True),
    "temperature": ("CPU temperature", "°C", "temperature", None, True),
    "memory": ("Memory use", "%", None, "mdi:memory", True),
    "disk": ("SD card use", "%", None, "mdi:micro-sd", True),
    "wifi": ("Wi-Fi signal", "dBm", "signal_strength", None, True),
    "booted": ("Started", None, "timestamp", None, True),
    "power": ("Power", None, None, "mdi:power-plug", True),
    "riley": ("Riley", None, None, "mdi:robot-happy", False),
}
POWER_PROBLEM = "power_problem"     # a binary sensor: on = under-voltage or slowed down right now


# ---------------------------------------------------------------- reading the Pi

def cpu_times(text):
    """(busy, total) from the first line of /proc/stat. LESSON: Linux counts how long the CPU
    has spent doing each kind of thing since it started. Read it twice: the share of the
    time in between that wasn't "idle" is how busy it was."""
    numbers = [int(n) for n in text.split("\n", 1)[0].split()[1:]]
    idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)       # idle + waiting for the SD card
    return sum(numbers) - idle, sum(numbers)


def cpu_percent(before, after):
    """None if the two readings are too close together to say (under about half a second)."""
    busy, total = after[0] - before[0], after[1] - before[1]
    return round(100 * busy / total, 1) if total >= 50 else None


def memory_percent(meminfo):
    values = {line.split(":")[0]: int(line.split()[1]) for line in meminfo.splitlines() if ":" in line}
    total, free = values.get("MemTotal", 0), values.get("MemAvailable", 0)
    return round(100 * (total - free) / total, 1) if total else None


def wifi_dbm(wireless):
    """The signal level from /proc/net/wireless (e.g. -52), or None if there's no Wi-Fi."""
    for line in wireless.splitlines()[2:]:
        parts = line.split()
        if len(parts) > 3:
            try:
                return int(float(parts[3].rstrip(".")))
            except ValueError:
                pass
    return None


def power_status(throttled):
    """LESSON: `vcgencmd get_throttled` answers with a number whose BITS each mean something.
    Bit 0: the power is too low right now. Bit 2: it's slowed itself down right now (too hot,
    or too little power). Bits 16 and 18: the same, at some point since it started."""
    if throttled is None:
        return "unknown", False
    if throttled & 0b1:
        return "under-voltage now", True
    if throttled & 0b100:
        return "slowed down now", True
    if throttled & (1 << 16):
        return "OK (was under-voltage earlier)", False
    if throttled & (1 << 18):
        return "OK (was slowed down earlier)", False
    return "OK", False


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def read_throttled(run=subprocess.run):
    try:
        out = run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5).stdout
        return int(out.strip().split("=")[1], 16)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Readings:
    """Everything worth knowing about the Pi, read from Linux's own files."""

    def __init__(self, riley_state=lambda: None):
        self.riley_state = riley_state
        self.last_cpu = cpu_times(_read("/proc/stat") or "cpu 0 0 0 0")

    def now(self):
        cpu = cpu_times(_read("/proc/stat") or "cpu 0 0 0 0")
        cpu_use = cpu_percent(self.last_cpu, cpu)
        if cpu_use is not None:
            self.last_cpu = cpu
        temp = _read("/sys/class/thermal/thermal_zone0/temp").strip()
        disk = shutil.disk_usage("/")
        uptime = float((_read("/proc/uptime") or "0").split()[0])
        power, problem = power_status(read_throttled())
        return {
            "cpu": cpu_use,
            "temperature": round(int(temp) / 1000, 1) if temp.isdigit() else None,
            "memory": memory_percent(_read("/proc/meminfo")),
            "disk": round(100 * disk.used / disk.total, 1),
            "wifi": wifi_dbm(_read("/proc/net/wireless")),
            "booted": datetime.fromtimestamp(time.time() - uptime, timezone.utc).replace(microsecond=0).isoformat(),
            "power": power,
            POWER_PROBLEM: "ON" if problem else "OFF",
            "riley": self.riley_state() or "unknown",
        }


# ---------------------------------------------------------------- telling Home Assistant

def device_info():
    model = _read("/proc/device-tree/model").strip("\x00\n ") or "Raspberry Pi"
    return {"identifiers": [NODE], "name": "Riley", "manufacturer": "Raspberry Pi", "model": model}


def discovery_messages(device=None):
    """[(topic, payload)]: one description per sensor, for Home Assistant to create them from."""
    device = device or device_info()
    common = {"state_topic": STATE, "availability_topic": AVAILABLE, "device": device}
    messages = []
    for key, (name, unit, device_class, icon, diagnostic) in SENSORS.items():
        config = {**common, "name": name, "unique_id": f"{NODE}_{key}",
                  "value_template": f"{{{{ value_json.{key} }}}}"}
        if unit:
            config["unit_of_measurement"] = unit
            config["state_class"] = "measurement"         # so Home Assistant keeps long-term graphs
        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
        if diagnostic:
            config["entity_category"] = "diagnostic"
        messages.append((f"{PREFIX}/sensor/{NODE}/{key}/config", config))
    messages.append((f"{PREFIX}/binary_sensor/{NODE}/{POWER_PROBLEM}/config", {
        **common, "name": "Power problem", "unique_id": f"{NODE}_{POWER_PROBLEM}", "device_class": "problem",
        "entity_category": "diagnostic", "value_template": f"{{{{ value_json.{POWER_PROBLEM} }}}}"}))
    return messages


class HomeAssistantSensors:
    def __init__(self, host, port=1883, user="", password="", every=30, riley_state=lambda: None):
        import paho.mqtt.client as mqtt
        self.every = every
        self.readings = Readings(riley_state)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="riley-pi")
        if user:
            self.client.username_pw_set(user, password)
        self.client.will_set(AVAILABLE, "offline", retain=True)    # the last will (see above)
        self.client.on_connect = self._connected
        self.client.on_message = self._message
        self.client.reconnect_delay_set(5, 120)                    # broker down? keep trying, gently
        self.client.connect_async(host, int(port))
        self.client.loop_start()                                   # its own background thread

    def _connected(self, client, userdata, flags, reason, properties=None):
        if getattr(reason, "is_failure", False):
            hint = " (check MQTT_USER and MQTT_PASSWORD in bolt.env)" if "authori" in str(reason).lower() else ""
            print(f"   ! Home Assistant sensors: couldn't connect: {reason}{hint}", flush=True)
            return
        print("   (Home Assistant sensors: connected to MQTT)", flush=True)
        client.subscribe(f"{PREFIX}/status")                       # tells us when HA restarts
        self._announce()

    def _message(self, client, userdata, message):
        if message.topic == f"{PREFIX}/status" and message.payload == b"online":
            self._announce()                                       # HA restarted: describe ourselves again

    def _announce(self):
        for topic, config in discovery_messages():
            self.client.publish(topic, json.dumps(config), retain=True)
        self.client.publish(AVAILABLE, "online", retain=True)
        self.publish()

    def publish(self):
        self.client.publish(STATE, json.dumps(self.readings.now()))

    def run(self):
        while True:
            time.sleep(self.every)
            try:
                if self.client.is_connected():
                    self.publish()
            except Exception as e:                                 # never let this stop Riley
                print(f"   ! Home Assistant sensors: {e}", flush=True)


def start(riley_state=lambda: None):
    """Start reporting if MQTT_HOST is set in bolt.env. Returns the reporter, or None."""
    host = os.environ.get("MQTT_HOST", "").strip()
    if not host:
        return None
    try:
        sensors = HomeAssistantSensors(host, os.environ.get("MQTT_PORT", "1883"), os.environ.get("MQTT_USER", ""),
                                       os.environ.get("MQTT_PASSWORD", ""), riley_state=riley_state,
                                       every=max(10, int(os.environ.get("MQTT_EVERY", "30"))))
    except Exception as e:
        print(f"   ! Home Assistant sensors: {e}", flush=True)
        return None
    threading.Thread(target=sensors.run, daemon=True).start()
    return sensors
