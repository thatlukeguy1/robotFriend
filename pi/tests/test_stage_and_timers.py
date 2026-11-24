"""Moods, props and timers on Riley's screen."""
from test_body import LOUD, QUIET, PretendBrain, PretendMic, PretendSpeaker, PretendWake, seconds

from bolt_body.main import Body


class Face:
    def __init__(self): self.states, self.props, self.timers = [], [], None
    def set_state(self, name): self.states.append(name)
    def show_prop(self, emoji, text=""): self.props.append((emoji, text))
    def set_timers(self, timers): self.timers = timers
    def say(self, wav): pass
    def someone_here(self): pass


def test_the_reply_s_mood_and_prop_reach_the_face():
    class Brain(PretendBrain):
        def voice_stream(self, wav):
            yield ("heard", "is it raining?")
            yield ("mood", "sad")
            yield ("show", "🌧️", "8°")
            yield ("say", "I'm afraid so.", b"AUDIO1")
            yield ("mood", "happy")
            yield ("say", "But it clears up later!", b"AUDIO2")
            yield ("done", {})
    b = Body(Brain(), PretendMic([LOUD] * seconds(1) + [QUIET] * seconds(2)), PretendSpeaker(), PretendWake())
    b.face = Face()
    b.converse()
    assert b.face.props == [("🌧️", "8°")]
    talking = b.face.states[b.face.states.index("thinking") + 1:]
    assert talking[:3] == ["speaking", "sad", "happy"]           # sad for the bad news, then happy


def test_timers_from_the_feed_reach_the_face():
    class Brain(PretendBrain):
        def notifications(self, after):
            return {"boot": "b", "items": [], "timers": [{"seconds": 600, "seconds_left": 420}]}
    b = Body(Brain(), PretendMic([]), PretendSpeaker(), PretendWake())
    b.face = Face()
    b.check_reminders({})
    assert b.face.timers == [{"seconds": 600, "seconds_left": 420}]


def test_the_screen_shows_the_prop_and_the_timer_line():
    from bolt_body.animate import FaceAnimator
    from bolt_body.face import load_config
    class Screen:
        width, height = 320, 240
        def show(self, img): pass
    t = [0.0]
    f = FaceAnimator(Screen(), load_config(), clock=lambda: t[0])
    plain = f.frame()
    f.set_timers([{"seconds": 600, "seconds_left": 300}])
    f.show_prop("🌧️", "8°")
    t[0] = 0.1
    img = f.frame()
    ink = (0x7f, 0xdc, 0xff)
    assert img.getpixel((319 - 1, 120)) == ink and plain.getpixel((318, 120)) != ink    # the line down the right edge...
    assert img.getpixel((1, 120)) != ink                                               # ...but half gone: not down the left
    assert img.crop((260, 150, 320, 230)).getbbox() is not None and img.crop((260, 150, 320, 230)) != plain.crop((260, 150, 320, 230))
    f.set_state("listening")
    assert f.prop is None                                                              # "Hey Riley": prop put down
    t[0] = 400
    f.frame()
    assert f.timers == []                                                              # finished timers drop off


def test_brain_link_passes_moods_and_props_on():
    from bolt_body.brain_link import BrainLink
    class Reply:
        headers = {"Content-Type": "application/x-ndjson"}
        def iter_lines(self):
            yield '{"type": "mood", "name": "sad"}'.encode()
            yield '{"type": "show", "emoji": "\\ud83c\\udf27", "text": "8"}'.encode()
        def close(self): pass
    link = BrainLink("http://brain")
    link.http.post = lambda *a, **k: Reply()
    assert list(link.voice_stream(b"RIFF")) == [("mood", "sad"), ("show", "🌧", "8")]
