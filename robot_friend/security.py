"""
LESSON: Locking the front door
==============================
Bolt can switch things on in your home, read its memories about you, and
change its own eyes. So it needs a lock. Three ideas make it work:

1. PASSWORD HASHING
   We never store your password. We store a HASH: the result of scrambling
   it with a slow, one-way recipe (PBKDF2). When you log in, we scramble what
   you typed the same way and compare the results. Even someone who reads
   the file can't turn the hash back into your password. The SALT (random
   extra data mixed in) means two people with the same password still get
   different hashes.

2. SESSION COOKIES
   After you log in, the server gives your browser a COOKIE: a small,
   tamper-proof note saying "this browser logged in". The browser sends it
   back with every request, so you don't type the password each time. It's
   signed with a secret key only Bolt knows, so it can't be faked.

3. API KEYS
   The Pi can't type a password, so it has a long random KEY instead and sends
   it with every request ("Authorization: Bearer <key>").

Commands (run on the mini PC):
    docker exec -it bolt python -m robot_friend.security set-password
    docker exec bolt python -m robot_friend.security show-key
    docker exec bolt python -m robot_friend.security new-key
    docker exec bolt python -m robot_friend.security ca-fingerprint
"""

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

ITERATIONS = 300_000      # how many times to scramble: slow on purpose, so guessing is slow
MIN_LENGTH = 8
MAX_TRIES = 5             # wrong passwords allowed...
TRY_WINDOW = 300          # ...in this many seconds, before a device has to wait


class Security:
    def __init__(self, folder=None, open_for_testing=False):
        self.folder = Path(folder or os.environ.get("BOLT_DATA", "."))
        self.open_for_testing = open_for_testing  # ONLY for automated tests
        self._lock = threading.Lock()
        self._fails = {}  # device address -> times of recent wrong passwords

    # ------------------------------------------------------------ files

    def _file(self, name):
        return self.folder / name

    def _secret(self, name, length=32):
        """Read a random secret from a file, making it the first time."""
        path = self._file(name)
        with self._lock:
            if not path.exists():
                self.folder.mkdir(parents=True, exist_ok=True)
                path.write_text(secrets.token_urlsafe(length))
                path.chmod(0o600)  # only Bolt's own user can read it
            return path.read_text().strip()

    def session_secret(self):
        """Signs login cookies. Kept in a file so logins survive restarts."""
        return self._secret("session.secret")

    def api_key(self):
        """The Pi's key."""
        return self._secret("api.key")

    def new_api_key(self):
        self._file("api.key").unlink(missing_ok=True)
        return self.api_key()

    # --------------------------------------------------------- password

    def has_password(self):
        return self._file("password.json").exists()

    def set_password(self, password):
        if len(password) < MIN_LENGTH:
            raise ValueError(f"Use at least {MIN_LENGTH} characters.")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
        record = {"salt": salt.hex(), "hash": digest.hex(), "iterations": ITERATIONS}
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._file("password.json")
        path.write_text(json.dumps(record))
        path.chmod(0o600)

    def check_password(self, password):
        if not self.has_password():
            return False
        record = json.loads(self._file("password.json").read_text())
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(record["salt"]), record["iterations"])
        # compare_digest takes the same time whether the first letter or the last
        # is wrong, so an attacker can't learn anything from how long it takes.
        return hmac.compare_digest(digest.hex(), record["hash"])

    def fingerprint(self):
        """Changes whenever the password changes, which logs every browser out."""
        if not self.has_password():
            return ""
        return json.loads(self._file("password.json").read_text())["hash"][:16]

    def check_api_key(self, key):
        return bool(key) and hmac.compare_digest(key, self.api_key())

    # ------------------------------------------------- slowing down guessing

    def wait_needed(self, device, now=None):
        """Seconds this device must wait before trying again (0 = go ahead)."""
        now = now or time.time()
        with self._lock:   # several requests can arrive at once (the server has 8 workers)
            for d in [d for d, times in self._fails.items() if all(now - t >= TRY_WINDOW for t in times)]:
                del self._fails[d]                     # forget devices that stopped trying
            recent = [t for t in self._fails.get(device, []) if now - t < TRY_WINDOW]
        if len(recent) < MAX_TRIES:
            return 0
        return int(TRY_WINDOW - (now - recent[0])) + 1

    def record_fail(self, device, now=None):
        with self._lock:
            self._fails.setdefault(device, []).append(now or time.time())

    def record_success(self, device):
        with self._lock:
            self._fails.pop(device, None)


def main(args):
    sec = Security()
    if args == ["set-password"]:
        first = getpass.getpass("New password for Bolt: ")
        if getpass.getpass("Type it again: ") != first:
            print("❌ Those didn't match. Nothing changed.")
            return 1
        try:
            sec.set_password(first)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
        print("✅ Password set. Every browser will need to log in again.")
    elif args == ["show-key"]:
        print(sec.api_key())
    elif args == ["ca-fingerprint"]:
        # The certificate authority's "fingerprint": compare it with what a device downloaded,
        # to be sure nobody swapped the file on the way.
        import ssl
        path = Path(os.environ.get("CA_CERT_PATH", "/caddy/caddy/pki/authorities/local/root.crt"))
        if not path.exists():
            print("❌ No certificate authority yet. Is the HTTPS front door (bolt-https) running?")
            return 1
        der = ssl.PEM_cert_to_DER_cert(path.read_text())
        digest = hashlib.sha256(der).hexdigest().upper()
        print("SHA256 fingerprint:", ":".join(digest[i:i + 2] for i in range(0, len(digest), 2)))
    elif args == ["new-key"]:
        print(sec.new_api_key())
        print("(The old key no longer works. Put this new one in the Pi's bolt.env.)", file=sys.stderr)
    else:
        print("Usage: python -m robot_friend.security set-password | show-key | new-key | ca-fingerprint")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
