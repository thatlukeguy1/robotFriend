"""Riley's Pi as a Home Assistant device over MQTT (bolt_body/ha_sensors.py)."""
import json

from bolt_body import ha_sensors as hs

STAT_1 = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4\n"
STAT_2 = "cpu  250 0 150 1500 100 0 0 0 0 0\n"


def test_cpu_use_is_the_busy_share_between_two_readings():
    assert hs.cpu_percent(hs.cpu_times(STAT_1), hs.cpu_times(STAT_2)) == 20.0     # 200 busy of 1000
    assert hs.cpu_percent(hs.cpu_times(STAT_1), hs.cpu_times(STAT_1)) is None     # too soon to say


def test_memory_uses_what_is_really_available():
    assert hs.memory_percent("MemTotal: 4000 kB\nMemFree: 100 kB\nMemAvailable: 3000 kB\n") == 25.0
    assert hs.memory_percent("") is None


def test_wifi_signal():
    wireless = ("Inter-| sta-|   Quality        |   Discarded packets\n"
                " face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n"
                " wlan0: 0000   58.  -52.  -256        0      0      0      0     12        0\n")
    assert hs.wifi_dbm(wireless) == -52
    assert hs.wifi_dbm("header\nheader\n") is None


def test_power_bits():
    assert hs.power_status(0) == ("OK", False)
    assert hs.power_status(0x50005) == ("under-voltage now", True)
    assert hs.power_status(0x4) == ("slowed down now", True)
    assert hs.power_status(0x50000) == ("OK (was under-voltage earlier)", False)
    assert hs.power_status(None) == ("unknown", False)
    run = lambda *a, **k: type("R", (), {"stdout": "throttled=0x50000\n"})()
    assert hs.read_throttled(run) == 0x50000


def test_discovery_makes_one_device_with_every_sensor():
    messages = dict(hs.discovery_messages({"identifiers": ["riley_pi"], "name": "Riley"}))
    assert len(messages) == len(hs.SENSORS) + 1
    temp = messages["homeassistant/sensor/riley_pi/temperature/config"]
    assert temp["unit_of_measurement"] == "°C" and temp["device_class"] == "temperature"
    assert temp["availability_topic"] == hs.AVAILABLE and temp["state_topic"] == hs.STATE
    assert "state_class" not in messages["homeassistant/sensor/riley_pi/riley/config"]        # words, not numbers
    assert messages["homeassistant/binary_sensor/riley_pi/power_problem/config"]["device_class"] == "problem"
    assert len({m["unique_id"] for m in messages.values()}) == len(messages)
    json.dumps(messages)                                                                   # all sendable


def test_off_unless_a_broker_is_set(monkeypatch):
    monkeypatch.delenv("MQTT_HOST", raising=False)
    assert hs.start() is None


def test_her_status_in_a_word():
    from test_body import PretendBrain, PretendMic, PretendSpeaker, PretendWake
    from bolt_body.main import Body
    b = Body(PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake())
    assert b.status() == "awake"
    b.talking = True
    assert b.status() == "talking"
    b.talking = False
    class Face:
        state, awake_since, sleep_after, screen_on = "idle", 0.0, 600, True
        clock = staticmethod(lambda: 1000.0)
    b.face = Face()
    assert b.status() == "dozing"
    b.face.screen_on = False
    assert b.status() == "screen off"
