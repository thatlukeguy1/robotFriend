"""
LESSON: Playing the news
========================
The BBC publishes its short news bulletins as a PODCAST. A podcast is just a
web page in a format called RSS: a list of episodes, newest first, each with a
link (the "enclosure") to an MP3 file. So "play the latest news" means:

  1. download the RSS list (NEWS_FEED in .env)
  2. take the newest episode's MP3 link
  3. download the MP3
  4. turn it into a WAV, the only sound the Pi's speaker code plays.
     `ffmpeg` (installed in the Dockerfile) does that, and makes it mono at
     22,050 samples a second: plenty for a voice, and a smaller file to send.

Safety limits, because this downloads things from the internet:
  * only https links;
  * the list may be at most 2 MB and the MP3 at most 80 MB;
  * at most NEWS_MINUTES of sound is kept (default 5, up to 30). A longer podcast
    FADES OUT over the last 3 seconds, like a radio presenter turning it down,
    instead of stopping mid-word.

The same bulletin is kept in memory, so asking twice doesn't download it twice.
"""

import io
import os
import subprocess
import threading
import urllib.request
import wave
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

DEFAULT_FEED = "https://podcasts.files.bbci.co.uk/p02nq0gn.rss"   # BBC World Service: Global News Podcast
MAX_FEED_BYTES = 2_000_000
MAX_AUDIO_BYTES = 80_000_000   # a 30-minute podcast at 128 kbit/s is about 29 MB
MAX_MINUTES = 10
DEFAULT_MINUTES = 5   # the Global News Podcast is ~30 minutes: play the start, then fade out
RATE = 22050


class NewsError(Exception):
    """The news couldn't be fetched. The message says why, in plain words."""


def _download(url, limit, timeout=20, allow_http=False):
    if not (url.startswith("https://") or (allow_http and url.startswith("http://"))):
        raise NewsError(f"only https links are allowed, not {url[:60]}")
    request = urllib.request.Request(url, headers={"User-Agent": "robot-friend/1.0 (personal desk robot)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            data = r.read(limit + 1)
    except OSError as e:
        raise NewsError(f"couldn't download it ({e})") from e
    if len(data) > limit:
        raise NewsError("the file was far bigger than a news bulletin should be")
    return data


def newest_episode(rss_bytes):
    """The newest episode in a podcast's RSS: {"title", "published", "url"}."""
    try:
        channel = ET.fromstring(rss_bytes).find("channel")
    except ET.ParseError as e:
        raise NewsError("the news feed wasn't a podcast feed") from e
    episodes = []
    for item in (channel.findall("item") if channel is not None else []):
        enclosure = item.find("enclosure")
        if enclosure is None or not enclosure.get("url"):
            continue
        try:
            when = parsedate_to_datetime(item.findtext("pubDate", ""))
        except (TypeError, ValueError):
            when = None
        episodes.append({"title": (item.findtext("title") or "").strip(), "when": when, "url": enclosure.get("url")})
    if not episodes:
        raise NewsError("the news feed has no episodes in it")
    dated = [e for e in episodes if e["when"]]
    newest = max(dated, key=lambda e: e["when"]) if dated else episodes[0]
    when = newest.pop("when")
    newest["published"] = when.isoformat(timespec="minutes") if when else "unknown"
    return newest


def to_wav(audio_bytes, max_minutes=MAX_MINUTES):
    """Any sound file (MP3...) -> a mono 22 kHz WAV, using ffmpeg. Fades out at max_minutes
    (a recording shorter than that never reaches the fade, so it plays untouched)."""
    seconds = max(5, int(max_minutes * 60))
    try:
        done = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-t", str(seconds),
             "-af", f"afade=t=out:st={seconds - 3}:d=3",
             "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"],
            input=audio_bytes, capture_output=True, timeout=120)
    except FileNotFoundError as e:
        raise NewsError("ffmpeg isn't installed in the brain (rebuild it: docker compose up -d --build)") from e
    except subprocess.TimeoutExpired as e:
        raise NewsError("turning the news into sound took too long") from e
    if done.returncode != 0 or len(done.stdout) < 1000:
        raise NewsError("the news download wasn't a sound file ffmpeg could read")
    # ffmpeg gives us the raw samples. We wrap them in the WAV "label" ourselves, because
    # ffmpeg writing into a pipe can't go back and fill in how long the sound is.
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(done.stdout)
    return out.getvalue()


class News:
    def __init__(self, feed=None, download=_download, convert=None, minutes=None):
        self.feed = (feed if feed is not None else os.environ.get("NEWS_FEED", DEFAULT_FEED)).strip()
        try:
            minutes = float(minutes if minutes is not None else os.environ.get("NEWS_MINUTES", DEFAULT_MINUTES))
        except ValueError:
            minutes = DEFAULT_MINUTES
        self.minutes = min(30.0, max(1.0, minutes))
        self.download = download
        self.convert = convert or (lambda audio: to_wav(audio, self.minutes))
        self._cache = (None, None)     # (episode link, its WAV)
        self._lock = threading.Lock()

    @property
    def enabled(self):
        return bool(self.feed) and self.feed.lower() not in ("off", "none", "0")

    def sound_file(self, url):
        """LESSON: the BBC's feeds list their MP3s as plain http:// links (no padlock).
        We try the same link with https:// first. Only if that fails do we use http, and
        only for the SOUND: the feed (which decides what gets downloaded) must be https."""
        if url.startswith("http://"):
            try:
                return self.download("https://" + url[len("http://"):], MAX_AUDIO_BYTES, timeout=60)
            except NewsError as e:
                print(f"   (news: https didn't work ({e}), using the plain http link)", flush=True)
                return self.download(url, MAX_AUDIO_BYTES, timeout=60, allow_http=True)
        return self.download(url, MAX_AUDIO_BYTES, timeout=60)

    def latest(self):
        """The newest bulletin: (episode info, WAV bytes). Raises NewsError if it can't."""
        if not self.enabled:
            raise NewsError("the news isn't switched on (NEWS_FEED in .env)")
        episode = newest_episode(self.download(self.feed, MAX_FEED_BYTES))
        with self._lock:
            if self._cache[0] != episode["url"]:
                self._cache = (episode["url"], self.convert(self.sound_file(episode["url"])))
            return episode, self._cache[1]
