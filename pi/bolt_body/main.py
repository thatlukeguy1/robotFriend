"""
Bolt's body: the program that runs on the Raspberry Pi.

LESSON: A STATE MACHINE
=======================
At any moment Bolt is in exactly one STATE:

   SLEEPING ──"Hey Bolt" (or button)──► LISTENING ──you stop talking──► THINKING
      ▲                                                                    │
      └──────────────────────────── SPEAKING ◄──── reply arrives ─────────┘

Each state knows what to do and which state comes next. This is how most
robots, games and gadgets are organised. Later, Bolt's eyes will show the
state: sleepy, wide open, thinking, talking.

Settings come from environment variables (see pi/bolt.env.example):
  BRAIN_URL        e.g. http://192.168.4.58:8770
  BOLT_KEY         the brain's key for the Pi (see LEARN.md)
  BOLT_CA          path to bolt-ca.crt, so the Pi can check it's really Bolt (HTTPS)
  WAKE_MODEL       hey_jarvis, or a path to hey_bolt.onnx
  WAKE_THRESHOLD   0.5
  BUTTON_PIN       optional GPIO pin number for a push-to-talk button
  MIC_DEVICE / SPEAKER_DEVICE   optional sound card names

Run on the Pi:            python -m bolt_body.main
Test on any computer:     python -m bolt_body.main --mic-file test.wav --speaker-folder out/
"""

import argparse
import os
import random
import threading
import time

from .audio import FileMicrophone, FileSpeaker, Microphone, Speaker, chime, loudness, record_until_quiet
from .brain_link import BrainLink


NEAR_MISS_FRAMES = 6      # quiet frames (about half a second) that end a near miss
BEEP_ECHO_SECONDS = 0.15  # how long the beep can still be ringing after it "finishes"


# What the face shows for each thing Bolt does (waiting for the wake word looks "idle":
# awake and glancing about; the face dozes off by itself after a while).
# What Bolt says when it hears its name (recorded once at start-up, in Bolt's own voice).
# Change them with ACK_PHRASES in bolt.env, separated by | . Empty = a soft chime instead.
ACK_PHRASES = "Yes?|Mm-hm?|I'm listening.|What's up?|Hi!"

# LESSON: how loud counts as "you've started talking"? It depends on the mic and
# the room, so Bolt keeps measuring the BACKGROUND while it waits for the wake word,
# and speech has to be clearly louder than that: SPEECH_OVER_BACKGROUND times louder,
# but never quieter than QUIETEST_SPEECH (or it would react to every rustle).
SPEECH_OVER_BACKGROUND = 3.0
MAX_FOLLOW_UPS = 5        # questions in a row she'll wait for answers to, before needing her name again
QUIETEST_SPEECH = 120

FACE_FOR = {"sleeping": "idle", "listening": "listening", "thinking": "thinking", "speaking": "speaking"}


def show(state, detail=""):
    """Print what Bolt is doing (the face is moved by Body.mood, below)."""
    faces = {"sleeping": "(-_-) zzz", "listening": "(O_O) !", "thinking": "(o_o) ...", "speaking": "(^_^) ♪"}
    print(f"{faces.get(state, state):12} {state.upper():10} {detail}", flush=True)


class Body:
    def __init__(self, brain, mic, speaker, wake, button_pin=None, face=None):
        from .animate import NoFace
        self.brain, self.mic, self.speaker, self.wake = brain, mic, speaker, wake
        self.face = face or NoFace()
        self.announcements = []          # reminders waiting to be said out loud
        self.acks = []                   # "Yes?" and friends, as ready-made audio (see load_acks)
        self.background = 100.0          # how loud the room is when nobody's talking (kept up to date)
        self.listen_seconds = 4.0        # how long to wait for you to start talking (Studio: Body tab)
        self.follow_up_seconds = 5.0     # how long to wait for your answer when she asks a question
        self.ack_phrases = None          # the replies the acks were recorded from
        self.last_ack = None
        self.button_pressed = threading.Event()
        if button_pin:
            from gpiozero import Button  # only on a real Pi
            self.button = Button(int(button_pin))
            self.button.when_pressed = self.button_pressed.set

    def load_acks(self, phrases):
        """Ask the brain to say each reply once, and keep the audio ready for later."""
        self.ack_phrases = list(phrases)
        acks = [audio for audio in (self.brain.speak(p) for p in phrases if p.strip()) if audio]
        self.acks = acks
        return len(acks)

    def apply_settings(self, data):
        """Use the settings saved in the Studio's Body tab. Until you've saved some there,
        bolt.env's values are kept, so nothing changes by surprise."""
        if not data or not data.get("custom"):
            return False
        s = data["current"]
        if hasattr(self.speaker, "volume"):
            self.speaker.volume = s["volume"] / 100
        self.face.sleep_after = s["sleep_after_minutes"] * 60
        self.face.screen_off_after = s.get("screen_off_minutes", 0) * 60
        self.wake.threshold = s["wake_threshold"]
        self.wake.frames_needed = int(s.get("wake_frames", 1))
        self.listen_seconds = s["listen_seconds"]
        self.follow_up_seconds = s.get("follow_up_seconds", 5)
        if s["replies"] != self.ack_phrases:
            print(f"   ({self.load_acks(s['replies'])} wake-word replies ready)", flush=True)
        return True

    def watch_settings(self, every=30):
        """Runs in a background thread: checks the Studio's Body tab every 30 seconds."""
        last = None
        while True:
            data = self.brain.body_settings()
            if data and data != last:
                if self.apply_settings(data):
                    s = data["current"]
                    print(f"   (settings: volume {s['volume']}%, sleep after {s['sleep_after_minutes']} min, "
                          f"wake {s['wake_threshold']} x{s.get('wake_frames', 1)}, listen {s['listen_seconds']} s, "
                          f"screen off after {s.get('screen_off_minutes', 0) or 'never'})", flush=True)
                last = data
            time.sleep(every)

    def acknowledge(self):
        """Answer the wake word: a spoken reply (never the same one twice running), or a soft chime."""
        choices = [i for i in range(len(self.acks)) if i != self.last_ack] or list(range(len(self.acks)))
        if choices:
            self.last_ack = random.choice(choices)
            self.play(self.acks[self.last_ack])
        else:
            self.speaker.play(chime())

    def speech_level(self):
        """How loud a frame must be to count as someone talking, in this room."""
        return max(QUIETEST_SPEECH, self.background * SPEECH_OVER_BACKGROUND)

    def hear_background(self, frame):
        """While waiting: slowly learn how loud the room is. Loud moments (talking, a
        door banging) are ignored, so they don't make Bolt think the room is noisy."""
        level = loudness(frame)
        if level < self.background * 2:
            self.background += (level - self.background) * 0.02

    def mood(self, state, detail=""):
        """Print what Bolt is doing, and show it on the face."""
        show(state, detail)
        self.face.set_state(FACE_FOR.get(state, state))

    def play(self, audio):
        """Play audio, with the mouth moving along to it."""
        self.face.say(audio)
        self.speaker.play(audio)

    # ---------------------------------------------- one conversation turn

    def converse(self):
        """One chat: listen, think, answer. If the answer ends with a question, keep
        listening for the reply (no need to say the wake word again)."""
        self.mood("listening", "(go ahead, I'm listening)")
        self.acknowledge()
        wait = self.listen_seconds
        for _ in range(MAX_FOLLOW_UPS + 1):
            asked = self.one_turn(wait)
            if not asked or self.follow_up_seconds <= 0:
                break
            # LESSON: she asked you something, so she listens for the answer. Her face
            # says "listening" and a very soft chime says "your turn".
            self.mood("listening", "(waiting for your answer)")
            self.speaker.play(chime((660,), ms=90, volume=0.06))
            wait = self.follow_up_seconds
        self.after_speaking()

    def one_turn(self, wait_seconds):
        """Record you, send it to the brain, speak the reply. True if the reply was a question."""
        # LESSON: the mic kept listening while Bolt said "Yes?" (or asked its question), so
        # its queue is full of Bolt's OWN VOICE. If we recorded that, Bolt would think you'd
        # started talking. So: wait a moment for the echo to die away, then throw it all out.
        time.sleep(BEEP_ECHO_SECONDS)
        self.mic.flush()
        needs = self.speech_level()
        stats = {}
        recording = record_until_quiet(self.mic, min_level=needs, stats=stats, wait_seconds=wait_seconds)
        if recording is None:
            self.mood("sleeping", f"(didn't hear anything: loudest sound {stats.get('loudest', 0):.0f}, "
                                  f"talking needs {needs:.0f}, background {self.background:.0f})")
            return False

        self.mood("thinking")
        # Talk while thinking: each sentence is played as soon as it arrives.
        spoke, last = False, ""
        for event in self.brain.voice_stream(recording):
            if event[0] == "heard":
                print(f"   you said: {event[1]}")
            elif event[0] == "say":
                print(f"   Bolt:     {event[1]}")
                last = event[1]
                if event[2]:
                    if not spoke:
                        self.mood("speaking")
                    self.play(event[2])
                    spoke = True
            elif event[0] == "error":
                print(f"   ! {event[1]}")
            elif event[0] == "done" and event[1]:
                print("   took: " + " · ".join(f"{k} {v}s" for k, v in event[1].items()))
        if not spoke:
            self.mood("confused")
            self.speaker.play(chime((440, 330)))  # falling notes = something went wrong
            return False
        return last.rstrip().rstrip('"\')').endswith("?")

    def announce(self, text):
        self.mood("speaking", f"(reminder) {text}")
        self.speaker.play(chime((523, 659, 784)))  # a little rising tune: a reminder
        audio = self.brain.speak(text)
        if audio:
            self.play(audio)
        self.after_speaking()

    def after_speaking(self):
        # The mic heard Bolt's own voice while it talked. Throw that away, or
        # Bolt might wake itself up!
        self.mic.flush()
        self.wake.reset()
        self.mood("sleeping")

    # ------------------------------------------------- the reminder checker

    def watch_for_reminders(self, every=10):
        """Runs in a background THREAD: asks the brain for new reminders."""
        seen = max((n["id"] for n in self.brain.notifications(0)), default=0)  # skip old ones
        while True:
            for n in self.brain.notifications(seen):
                self.announcements.append(n["text"])
                seen = max(seen, n["id"])
            time.sleep(every)

    # ------------------------------------------------------- the main loop

    def run(self):
        self.mood("sleeping", "(say the wake word, or press the button)")
        best, best_until = 0.0, 0
        while True:
            frame = self.mic.read()
            self.hear_background(frame)
            if self.announcements:
                self.announce(self.announcements.pop(0))
            elif self.wake.heard(frame):
                print(f"   (wake word score {self.wake.last_score:.2f}, {getattr(self.wake, 'in_a_row', 1)} in a row)", flush=True)
                self.wake.reset()
                best = 0.0
                self.converse()
            elif self.button_pressed.is_set():
                self.button_pressed.clear()
                self.converse()
            else:
                # LESSON: tuning the threshold. A "near miss" is a score at least
                # half the threshold that didn't make it. Seeing them tells you
                # whether to LOWER the threshold (your real tries score 0.3-0.4) or
                # leave it (only random noises get near). We print the best score
                # of each near miss once it's over, so one word gives one line.
                threshold = getattr(self.wake, "threshold", 1.0)
                score = self.wake.last_score
                if score >= threshold / 2:
                    best, best_until = max(best, score), NEAR_MISS_FRAMES
                elif best:
                    best_until -= 1
                    if best_until <= 0:
                        print(f"   (nearly woke: score {best:.2f}, needs {threshold:.2f})", flush=True)
                        best = 0.0


def main():
    parser = argparse.ArgumentParser(description="Bolt's body")
    parser.add_argument("--mic-file", help="test with a WAV file instead of a microphone")
    parser.add_argument("--speaker-folder", help="save Bolt's speech to this folder instead of playing it")
    args = parser.parse_args()

    brain = BrainLink(os.environ.get("BRAIN_URL", "https://localhost:8770"), os.environ.get("BOLT_KEY", ""),
                      os.environ.get("BOLT_CA", ""))
    if not brain.is_awake():
        print(f"! Can't reach Bolt's brain at {brain.url}. Check BRAIN_URL (it should start https://),"
              " BOLT_CA, and that the mini PC is on.")
    elif not brain.key_works():
        print("! The brain refused our key. Put the key from `docker exec bolt python -m robot_friend.security show-key`"
              " into BOLT_KEY in bolt.env.")

    from .wake import WakeWord
    wake = WakeWord(os.environ.get("WAKE_MODEL", "hey_jarvis"), float(os.environ.get("WAKE_THRESHOLD", "0.5")))
    mic = FileMicrophone(args.mic_file) if args.mic_file else Microphone(os.environ.get("MIC_DEVICE") or None)
    speaker = FileSpeaker(args.speaker_folder) if args.speaker_folder else Speaker(os.environ.get("SPEAKER_DEVICE") or None)

    from .animate import make_face
    face = make_face(brain.url, os.environ.get("BOLT_CA") or None)   # the animated face, if a screen is connected
    body = Body(brain, mic, speaker, wake, button_pin=os.environ.get("BUTTON_PIN") or None, face=face)
    threading.Thread(target=body.watch_for_reminders, daemon=True).start()
    # Record the wake-word replies in the background, so Bolt starts listening straight away
    phrases = os.environ.get("ACK_PHRASES", ACK_PHRASES).split("|")
    body.ack_phrases = phrases
    threading.Thread(target=lambda: print(f"   ({body.load_acks(phrases)} wake-word replies ready)", flush=True),
                     daemon=True).start()
    threading.Thread(target=body.watch_settings, daemon=True).start()   # the Studio's Body tab
    try:
        body.run()
    except (EOFError, KeyboardInterrupt):
        print("Bye!")


if __name__ == "__main__":
    main()
