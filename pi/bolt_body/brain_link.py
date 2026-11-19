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
"""

import base64

import requests


class BrainLink:
    def __init__(self, url, key=""):
        self.url = url.rstrip("/")
        # A Session remembers settings (like our key header) for every request.
        self.http = requests.Session()
        if key:
            self.http.headers["Authorization"] = f"Bearer {key}"

    def key_works(self):
        """True if the brain accepts our key."""
        try:
            return self.http.get(f"{self.url}/notifications", timeout=5).status_code != 401
        except requests.RequestException:
            return False

    def is_awake(self):
        try:
            return self.http.get(f"{self.url}/health", timeout=5).ok
        except requests.RequestException:
            return False

    def voice(self, wav_bytes):
        """Returns (what Bolt heard, Bolt's reply text, reply audio or None, error or None)."""
        try:
            r = self.http.post(f"{self.url}/voice", data=wav_bytes,
                              headers={"Content-Type": "audio/wav"}, timeout=90)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            return "", "", None, f"Can't reach Bolt's brain ({e})"
        audio = base64.b64decode(data["audio"]) if data.get("audio") else None
        return data.get("transcript", ""), data.get("reply", ""), audio, data.get("error")

    def speak(self, text):
        try:
            r = self.http.post(f"{self.url}/speak", json={"text": text}, timeout=30)
            return r.content if r.ok else None
        except requests.RequestException:
            return None

    def notifications(self, after):
        try:
            return self.http.get(f"{self.url}/notifications", params={"after": after}, timeout=5).json()["notifications"]
        except (requests.RequestException, ValueError, KeyError):
            return []
