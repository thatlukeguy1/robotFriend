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
import threading
import time

from .audio import FileMicrophone, FileSpeaker, Microphone, Speaker, beep, record_until_quiet
from .brain_link import BrainLink


NEAR_MISS_FRAMES = 6      # quiet frames (about half a second) that end a near miss
BEEP_ECHO_SECONDS = 0.15  # how long the beep can still be ringing after it "finishes"


# What the face shows for each thing Bolt does (waiting for the wake word looks "idle":
# awake and glancing about; the face dozes off by itself after a while).
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
        self.button_pressed = threading.Event()
        if button_pin:
            from gpiozero import Button  # only on a real Pi
            self.button = Button(int(button_pin))
            self.button.when_pressed = self.button_pressed.set

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
        self.mood("listening", "(go ahead, I'm listening)")
        self.speaker.play(beep(880))
        # LESSON: the mic kept listening while the beep played, so its queue is
        # full of BEEP (and the end of the wake word). If we recorded that, Bolt
        # would think you'd started talking, then stop at the first pause.
        # So: wait a moment for the beep's echo to die away, then throw it all out.
        time.sleep(BEEP_ECHO_SECONDS)
        self.mic.flush()
        recording = record_until_quiet(self.mic)
        if recording is None:
            self.mood("sleeping", "(didn't hear anything)")
            return

        self.mood("thinking")
        # Talk while thinking: each sentence is played as soon as it arrives.
        spoke = False
        for event in self.brain.voice_stream(recording):
            if event[0] == "heard":
                print(f"   you said: {event[1]}")
            elif event[0] == "say":
                print(f"   Bolt:     {event[1]}")
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
            self.speaker.play(beep(220, 300))  # low beep = something went wrong
        self.after_speaking()

    def announce(self, text):
        self.mood("speaking", f"(reminder) {text}")
        self.speaker.play(beep(660))
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
            if self.announcements:
                self.announce(self.announcements.pop(0))
            elif self.wake.heard(frame):
                print(f"   (wake word score {self.wake.last_score:.2f})")
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
    try:
        body.run()
    except (EOFError, KeyboardInterrupt):
        print("Bye!")


if __name__ == "__main__":
    main()
