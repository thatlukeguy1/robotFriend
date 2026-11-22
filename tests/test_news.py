"""The news: find the newest bulletin in a podcast feed, turn it into WAV, play it after the reply."""
import base64
import io
import json
import shutil
import subprocess
import wave
from types import SimpleNamespace as Obj

import pytest

from robot_friend.brain import Brain
from robot_friend.news import News, NewsError, newest_episode, to_wav, _download
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>News Summary</title>
<item><title>Older</title><pubDate>Sun, 22 Nov 2026 06:00:00 GMT</pubDate>
  <enclosure url="https://example.org/old.mp3" type="audio/mpeg"/></item>
<item><title>Latest bulletin</title><pubDate>Sun, 22 Nov 2026 07:00:00 GMT</pubDate>
  <enclosure url="https://example.org/new.mp3" type="audio/mpeg"/></item>
<item><title>No sound</title><pubDate>Sun, 22 Nov 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_newest_episode_is_found_by_date_not_position():
    ep = newest_episode(FEED)
    assert ep == {"title": "Latest bulletin", "url": "https://example.org/new.mp3", "published": "2026-11-22T07:00+00:00"}


def test_bad_feeds_and_links_are_refused():
    with pytest.raises(NewsError):
        newest_episode(b"<html>not a feed</html")
    with pytest.raises(NewsError):
        newest_episode(b"<rss><channel></channel></rss>")
    with pytest.raises(NewsError, match="https"):
        _download("http://example.org/feed.rss", 100)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_mp3_becomes_a_mono_22k_wav():
    mp3 = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                          "-ac", "2", "-f", "mp3", "pipe:1"], capture_output=True, check=True).stdout
    with wave.open(io.BytesIO(to_wav(mp3)), "rb") as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 22050) and 1.8 < w.getnframes() / 22050 < 2.2
    with pytest.raises(NewsError):
        to_wav(b"this is not a sound file")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_long_podcast_is_cut_short_and_fades_out():
    import array
    mp3 = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
                          "-f", "mp3", "pipe:1"], capture_output=True, check=True).stdout
    with wave.open(io.BytesIO(to_wav(mp3, max_minutes=10 / 60)), "rb") as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    assert 9.5 < len(samples) / 22050 < 10.5                      # 10 seconds kept, not 20
    loud = lambda part: max(abs(s) for s in part)
    assert loud(samples[-500:]) < loud(samples[:22050]) / 10      # and it ends quietly


def test_news_minutes_are_kept_sensible(monkeypatch):
    monkeypatch.setenv("NEWS_MINUTES", "999")
    assert News("https://x.org/f.rss").minutes == 30
    monkeypatch.setenv("NEWS_MINUTES", "lots")
    assert News("https://x.org/f.rss").minutes == 5


def fake_news():
    downloads = []
    def download(url, limit, timeout=20, allow_http=False):
        downloads.append(url)
        return FEED if url.endswith(".rss") else b"MP3"
    return News("https://example.org/feed.rss", download=download, convert=lambda b: b"WAV:" + b), downloads


def test_the_same_bulletin_is_only_downloaded_once():
    news, downloads = fake_news()
    assert news.latest() == news.latest()
    assert downloads.count("https://example.org/new.mp3") == 1


def test_news_can_be_switched_off():
    assert not News("off").enabled
    with pytest.raises(NewsError):
        News("off").latest()


def test_typed_chat_cant_play_sound(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, news=fake_news()[0])
    assert "typed chat" in brain.run_tool("play_news", {})


def test_a_news_problem_is_told_to_claude(tmp_path):
    def broken(url, limit, timeout=20):
        raise NewsError("couldn't download it (no internet)")
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, news=News("https://x.org/f.rss", download=broken))
    brain.media_out = []
    assert "no internet" in brain.run_tool("play_news", {}) and brain.media_out == []


def test_voice_stream_plays_the_news_after_the_words(tmp_path):
    turns = [
        (["Here's the latest", " from the BBC."], Obj(stop_reason="tool_use", content=[
            Obj(type="text", text="Here's the latest from the BBC."),
            Obj(type="tool_use", id="t1", name="play_news", input={})])),
        ([], Obj(stop_reason="end_turn", content=[])),
    ]
    calls = []
    def stream(**kwargs):
        pieces, final = turns[len(calls)]
        calls.append({**kwargs, "messages": list(kwargs["messages"])})   # a snapshot
        class S:
            text_stream = iter(pieces)
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return final
        return S()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=Obj(messages=Obj(stream=stream)), news=fake_news()[0])
    web = create_app(brain, Notifications(), ears=lambda wav: "what's the news", mouth=lambda t: t.encode(),
                     security=Security(tmp_path, open_for_testing=True)).test_client()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setframerate(16000); w.setsampwidth(2); w.setnchannels(1); w.writeframes(b"\0\0" * 1600)
    lines = [json.loads(l) for l in web.post("/voice/stream", data=out.getvalue(), content_type="audio/wav").data.decode().splitlines()]
    assert [l["type"] for l in lines] == ["heard", "say", "play", "done"]
    assert lines[2]["title"] == "Latest bulletin" and "audio" not in lines[2]   # a link, not 17 MB in one line
    got = web.get(lines[2]["url"])
    assert got.status_code == 200 and got.data == b"WAV:MP3" and got.mimetype == "audio/wav"
    assert web.get("/sounds/made-up.wav").status_code == 404
    assert "Lined up" in calls[1]["messages"][-1]["content"][0]["content"]
    assert brain.media_out is None          # nothing left over for a typed chat


def test_http_sound_links_try_https_first_then_fall_back():
    seen = []
    feed = FEED.replace(b"https://example.org/new.mp3", b"http://example.org/new.mp3")
    def download(url, limit, timeout=20, allow_http=False):
        seen.append((url, allow_http))
        if url.endswith(".rss"):
            return feed
        if url.startswith("https://"):
            raise NewsError("no https here")
        return b"MP3"
    news = News("https://example.org/feed.rss", download=download, convert=lambda b: b)
    assert news.latest()[1] == b"MP3"
    assert seen[1:] == [("https://example.org/new.mp3", False), ("http://example.org/new.mp3", True)]


def test_the_feed_itself_must_be_https():
    with pytest.raises(NewsError, match="https"):
        News("http://example.org/feed.rss").latest()
