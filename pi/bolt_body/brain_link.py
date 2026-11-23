"""
LESSON: Phoning the brain
=========================
The Pi is a CLIENT of the brain's server, exactly like the web page on your
phone. It uses the same routes:

  POST /voice           send what you said, get back Bolt's spoken reply
  POST /speak           turn text (like a reminder) into Bolt's voice
  GET  /notifications   anything new to announce?

The brain is locked (see robot_friend/security.py), so every request carries
the Pi's KEY in a header:  Authorization: Bearer <key>

The brain speaks HTTPS (see the Caddyfile). `ca` is the path to Bolt's
certificate-authority stamp (bolt-ca.crt): the Pi checks every reply really
comes from Bolt, and refuses to send its key anywhere else.
"""

import base64
import json

import requests


class BrainLink:
    def __init__(self, url, key="", ca=""):
        self.url = url.rstrip("/")
        # A Session remembers settings (like our key header) for every request.
        self.http = requests.Session()
        # Which certificate authority to trust. We pass it on EVERY request rather than
        # setting it once on the Session: settings in the environment (like
        # REQUESTS_CA_BUNDLE) would otherwise quietly win over the Session's.
        self.verify = ca or True
        self.last_timings = {}
        if key:
            self.http.headers["Authorization"] = f"Bearer {key}"

    def key_works(self):
        """True if the brain accepts our key."""
        try:
            return self.http.get(f"{self.url}/notifications", timeout=5, verify=self.verify).status_code != 401
        except requests.RequestException:
            return False

    def is_awake(self):
        try:
            return self.http.get(f"{self.url}/health", timeout=5, verify=self.verify).ok
        except requests.RequestException:
            return False

    def voice(self, wav_bytes):
        """Returns (what Bolt heard, Bolt's reply text, reply audio or None, error or None)."""
        try:
            r = self.http.post(f"{self.url}/voice", data=wav_bytes,
                               headers={"Content-Type": "audio/wav"}, timeout=90, verify=self.verify)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            return "", "", None, f"Can't reach Bolt's brain ({e})"
        audio = base64.b64decode(data["audio"]) if data.get("audio") else None
        self.last_timings = data.get("timings", {})  # how long each step took on the brain
        return data.get("transcript", ""), data.get("reply", ""), audio, data.get("error")

    def voice_stream(self, wav_bytes):
        """
        Talk while thinking: yields events as the brain sends them, so the Pi can
        play each sentence the moment it arrives (see /voice/stream in server.py):
          ("heard", text)   ("say", text, audio-or-None)   ("error", message)   ("done", timings)
        """
        try:
            r = self.http.post(f"{self.url}/voice/stream", data=wav_bytes, headers={"Content-Type": "audio/wav"},
                               timeout=90, stream=True, verify=self.verify)
            if "ndjson" not in r.headers.get("Content-Type", ""):
                data = r.json()   # not a stream: nothing heard, or a problem before Bolt could answer
                yield ("heard", data.get("transcript", ""))
                if data.get("error"):
                    yield ("error", data["error"])
                return
            for raw in r.iter_lines():
                if not raw:
                    continue
                event = json.loads(raw)
                if event["type"] == "heard":
                    yield ("heard", event["text"])
                elif event["type"] == "say":
                    yield ("say", event["text"], base64.b64decode(event["audio"]) if event.get("audio") else None)
                elif event["type"] == "error":
                    yield ("error", event["error"])
                elif event["type"] == "done":
                    self.last_timings = event.get("timings", {})
                    yield ("done", self.last_timings)
        except (requests.RequestException, ValueError) as e:
            yield ("error", f"Can't reach Bolt's brain ({e})")

    def speak(self, text):
        try:
            r = self.http.post(f"{self.url}/speak", json={"text": text}, timeout=30, verify=self.verify)
            return r.content if r.ok else None
        except requests.RequestException:
            return None

    def body_settings(self):
        """Volume, sleep time and so on, saved in the Studio's Body tab (None if the brain can't say)."""
        try:
            r = self.http.get(f"{self.url}/body-settings", timeout=5, verify=self.verify)
            return r.json() if r.ok else None
        except (requests.RequestException, ValueError):
            return None

    def photo_wanted(self):
        """Has the brain asked for a photo? Returns its request id, or None."""
        try:
            r = self.http.get(f"{self.url}/camera/wanted", timeout=5, verify=self.verify)
            return r.json().get("id") if r.ok else None
        except (requests.RequestException, ValueError):
            return None

    def send_photo(self, request_id, jpeg):
        try:
            r = self.http.post(f"{self.url}/camera/photo/{request_id}", data=jpeg,
                               headers={"Content-Type": "image/jpeg"}, timeout=15, verify=self.verify)
            return r.ok
        except requests.RequestException:
            return False

    def notifications(self, after):
        try:
            return self.http.get(f"{self.url}/notifications", params={"after": after}, timeout=5, verify=self.verify).json()["notifications"]
        except (requests.RequestException, ValueError, KeyError):
            return []
