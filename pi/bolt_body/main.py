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
import subprocess
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
INTERRUPT_SURE = 0.9     # while talking, the wake word must be THIS sure to interrupt...
INTERRUPT_IN_A_ROW = 2   # ...and heard this many checks in a row (her own voice reaches the mic too)
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
        self.touched = threading.Event()   # a tap on the screen (see touch.py)
        self.touch = None                  # the touch panel, if there is one
        self.camera = None                 # the camera, if there is one (see camera.py)
        self.camera_wakes = True           # Studio: wake up on movement
        self.faces = None                  # face recognition, if faces have been taught (see faces.py)
        self.face_people = {}              # who it knows
        self.recognise = True              # Studio: recognise faces
        self.last_face_check = -1e9
        self.reported = {}                 # name -> when we last told the brain we saw them
        self.things = None                 # the object finder for the 📷 view (see objects.py), made when first needed
        self.things_broken = False
        self.talking = False               # in a conversation: the 📷 view skips its boxes meanwhile
        from .camera import MotionWatch
        self.motion = MotionWatch()
        self.turning_off = False
        self.interrupt_sure = INTERRUPT_SURE   # Studio: how sure "Hey Riley" must be while she talks
        self.picture_seconds = 20              # Studio: how long a camera picture stays on the screen
        if button_pin:
            from gpiozero import Button  # only on a real Pi
            self.button = Button(int(button_pin))
            self.button.when_pressed = self.button_pressed.set

    # ------------------------------------------------- the touch screen

    def on_touch(self, event):
        """Called by the touch panel (in its own thread) for each gesture."""
        kind = event[0]
        if kind in ("down", "tap", "off"):
            print(f"   (touch: {kind})", flush=True)
        if kind == "down":
            self.face.someone_here()                  # wake the screen straight away
        elif kind == "tap":
            self.touched.set()                       # the main loop (or play) acts on it
        elif kind == "hold":
            self.face.power_hold = event[1]          # the ring fills up
        elif kind == "cancel":
            self.face.power_hold = 0.0
            print("   (turning off cancelled)", flush=True)
        elif kind == "off":
            self.power_off()

    def power_off(self, run=subprocess.run):
        """LESSON: why "turn off" isn't just pulling the plug. The Pi keeps files half-written
        in memory and saves them now and then. Pull the plug at the wrong moment and the SD
        card can be damaged (that's what broke the .pyc files that time!). Shutting down
        properly saves everything first. When the Pi's green light stops flashing, it's safe
        to switch the power off."""
        self.turning_off = True
        print("   (turning off: the screen was held down)", flush=True)
        if hasattr(self.speaker, "stop"):
            self.speaker.stop()
        self.face.power_hold = 1.0
        goodnight = self.brain.speak("Turning off. Goodnight!")
        if goodnight:
            self.speaker.play(goodnight)
        self.face.set_state("sleeping")
        done = run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], capture_output=True, text=True)
        if done.returncode != 0:
            self.turning_off = False
            self.face.power_hold = 0.0
            print(f"   ! couldn't turn off: {(done.stderr or '').strip()} (run pi/install.sh again to allow it)", flush=True)

    # ------------------------------------------------- the camera

    def watch_camera(self, every=0.5, clock=time.monotonic, sleep=time.sleep, rounds=None):
        """Runs in a background thread: hands in photos the brain asks for, and notices
        movement (on the Pi only) to wake her face and screen."""
        n = 0
        while rounds is None or n < rounds:
            n += 1
            try:
                request_id, kind = self.brain.camera_wanted()
                if request_id and kind == "view":
                    self.send_view(request_id)
                elif request_id:
                    before = getattr(self.face, "state", None)
                    self.face.set_state("listening")          # she's looking at you...
                    print("   (taking a photo: the brain asked to look)", flush=True)
                    try:
                        self.brain.send_photo(request_id, self.camera.photo())
                    finally:
                        if before:                            # ...then back to what she was doing
                            self.face.set_state(before)
                if self.camera_wakes:
                    if self.motion.update(self.camera.small(), clock()):
                        print("   (saw someone: screen on)", flush=True)
                        self.face.someone_seen()
                else:
                    self.motion.last = None
                self.look_for_faces(clock())
            except Exception as e:  # the camera must never stop Riley listening
                print(f"   ! camera: {e}", flush=True)
                sleep(5)
            sleep(every)

    def send_view(self, request_id):
        """LESSON: someone's watching on the 📷 page. Take a picture, find the faces (named if she
        knows them) and the everyday things in it, and send the picture with the boxes. Her
        screen shows 📷 for as long as anyone is watching: no secret watching."""
        import cv2
        self.face.show_prop("📷", "", seconds=3)
        picture = self.camera.frame()
        boxes = []
        if self.talking:          # LESSON: finding things is hard work for the Pi. While she's
            ok, jpeg = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 70])   # talking, just
            if ok:                                        # the picture, so listening comes first
                self.brain.send_view(request_id, jpeg.tobytes(), [], paused=True)
            return
        try:
            if self.faces is None:                          # nobody taught yet: still find faces
                self.faces = False                          # (False = tried and failed: don't retry)
                from .faces import Recogniser
                self.faces = Recogniser()
            if self.faces:
                boxes += self.faces.label_all(picture, self.face_people if self.recognise else {})
        except Exception as e:
            print(f"   ! view faces: {e}", flush=True)
        if not self.things_broken:
            try:
                if self.things is None:
                    from .objects import ObjectFinder
                    self.things = ObjectFinder()
                boxes += [dict(t, kind="thing") for t in self.things.find(picture)]
            except Exception as e:                          # say so once, then just show faces
                self.things_broken = True
                print(f"   ! view objects: {e}", flush=True)
        ok, jpeg = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            self.brain.send_view(request_id, jpeg.tobytes(), boxes)

    def look_for_faces(self, now):
        """LESSON: only look when it's worth it. Recognising a face takes the Pi a fraction of
        a second, so it only happens when something moved in the last 30 seconds, and at
        most every 2 seconds. Each person is reported to the brain at most once a minute."""
        if not (self.faces and self.face_people and self.recognise):
            return
        if now - self.motion.moved_at > 30 or now - self.last_face_check < 2:
            return
        self.last_face_check = now
        for name in self.faces.who(self.camera.frame(), self.face_people):
            self.face.someone_seen()
            if now - self.reported.get(name, -1e9) > 60:
                self.reported[name] = now
                print(f"   (recognised {name})", flush=True)
                self.brain.presence(name)

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
        self.interrupt_sure = s.get("interrupt_threshold", INTERRUPT_SURE)
        self.picture_seconds = s.get("picture_seconds", 20)
        if self.touch:                                         # the touch screen's timings
            self.touch.gestures.debounce = s.get("touch_min_ms", 40) / 1000
            self.touch.gestures.hold_off = float(s.get("touch_hold_seconds", 5))
        self.camera_wakes = s.get("camera_wakes", "on") == "on"
        self.recognise = s.get("recognise_faces", "on") == "on"
        self.motion.sensitivity = s.get("motion_sensitivity", 5)
        self.face.hat_mode = s.get("christmas_hat", "off")   # 🎅 on, off or auto (the face checks the date)
        if s["replies"] != self.ack_phrases:
            print(f"   ({self.load_acks(s['replies'])} wake-word replies ready)", flush=True)
        return True

    def check_settings(self, last):
        """One check of the Studio: the Body tab's settings and the Face tab's design.
        Returns the settings seen, for next time."""
        data = self.brain.body_settings()
        if data and data != last:
            if self.apply_settings(data):
                s = data["current"]
                print(f"   (settings: volume {s['volume']}%, sleep after {s['sleep_after_minutes']} min, "
                      f"wake {s['wake_threshold']} x{s.get('wake_frames', 1)}, listen {s['listen_seconds']} s, "
                      f"screen off after {s.get('screen_off_minutes', 0) or 'never'})", flush=True)
            last = data
        # A face design saved in the Studio reaches the screen without a restart (and if the
        # brain wasn't reachable when the Pi started, the saved design arrives now).
        if hasattr(self.face, "config") and hasattr(self.brain, "face_design"):
            design = self.brain.face_design()
            if design and design != self.face.config and "expressions" in design:
                self.face.config = design
                print("   (new face design from the Studio)", flush=True)
        return last

    def watch_settings(self, every=30):
        """Runs in a background thread: checks the Studio every 30 seconds."""
        last = None
        while True:
            try:
                last = self.check_settings(last)
            except Exception as e:  # one bad update must never stop later ones arriving
                print(f"   ! settings: {e}", flush=True)
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
        """Play audio, with the mouth moving along to it. Returns False if someone
        said the wake word to interrupt (the sound stops straight away)."""
        self.face.say(audio)
        if not hasattr(self.speaker, "start"):         # e.g. saving to files when testing
            self.speaker.play(audio)
            return True
        # LESSON: listening while talking. Instead of just waiting for the sound to end,
        # keep feeding the microphone to the wake word, and stop if it hears its name.
        self.speaker.start(audio)
        self.touched.clear()
        best = 0.0                                      # the closest anyone came to "Hey Riley"
        try:
            while self.speaker.busy():
                heard = self.interrupt_heard(self.mic.read())
                best = max(best, getattr(self.wake, "last_score", 0.0))
                if heard or self.touched.is_set():      # "Hey Riley" or a tap
                    self.touched.clear()
                    self.speaker.stop()
                    self.face.say(b"")                  # close the mouth
                    print(f"   (interrupted: {'by a tap' if not heard else f'Hey Riley scored {best:.2f}'})", flush=True)
                    return False
            return True
        finally:
            # LESSON: measure before you tune. If you tried to interrupt and she carried on,
            # this line says how close you got, so you know where to set the Studio slider.
            if best >= 0.3:
                print(f"   (while talking: best 'Hey Riley' score {best:.2f}, needs {self.interrupt_sure:.2f}"
                      f" {INTERRUPT_IN_A_ROW} checks in a row)", flush=True)

    def interrupt_heard(self, frame):
        """The wake word, but stricter: her own voice is coming out of the speaker."""
        wake = self.wake
        normal = (wake.threshold, getattr(wake, "frames_needed", 1))
        wake.threshold = self.interrupt_sure
        wake.frames_needed = max(normal[1], INTERRUPT_IN_A_ROW)
        try:
            return wake.heard(frame)
        finally:
            wake.threshold, wake.frames_needed = normal

    # ---------------------------------------------- one conversation turn

    def converse(self):
        """One chat: listen, think, answer. If the answer ends with a question, keep
        listening for the reply (no need to say the wake word again)."""
        self.talking = True
        try:
            self._converse()
        finally:
            self.talking = False

    def _converse(self):
        self.mood("listening", "(go ahead, I'm listening)")
        self.acknowledge()
        wait = self.listen_seconds
        for _ in range(MAX_FOLLOW_UPS + 1):
            outcome = self.one_turn(wait)
            if outcome == "interrupted":               # "Hey Riley!" while she was talking
                self.wake.reset()
                self.mood("listening", "(go ahead, I'm listening)")
                self.acknowledge()
                wait = self.listen_seconds
                continue
            if outcome != "question" or self.follow_up_seconds <= 0:
                break
            # LESSON: she asked you something, so she listens for the answer. Her face
            # says "listening" and a very soft chime says "your turn".
            self.mood("listening", "(waiting for your answer)")
            self.speaker.play(chime((660,), ms=90, volume=0.06))
            wait = self.follow_up_seconds
        self.after_speaking()

    def one_turn(self, wait_seconds):
        """Record you, send it to the brain, speak the reply.
        Returns "question" (she asked you something), "done", "nothing" or "interrupted"."""
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
            return "nothing"

        self.mood("thinking")
        # Talk while thinking: each sentence is played as soon as it arrives.
        spoke, last = False, ""
        reply_face = "speaking"                         # her face while she answers (see stage.py)
        stream = self.brain.voice_stream(recording)
        for event in stream:
            if event[0] == "heard":
                print(f"   you said: {event[1]}")
            elif event[0] == "mood":
                reply_face = event[1] or "speaking"
                if spoke:                               # a change of mood part-way through
                    self.face.set_state(reply_face)
            elif event[0] == "show":
                print(f"   showing:  {event[1]} {event[2]}")
                self.face.show_prop(event[1], event[2])
            elif event[0] == "say":
                print(f"   Bolt:     {event[1]}")
                last = event[1]
                if event[2]:
                    if not spoke:
                        self.mood("speaking")
                        if reply_face != "speaking":
                            self.face.set_state(reply_face)
                    spoke = True
                    if not self.play(event[2]):
                        stream.close()                  # stop listening to the rest of the reply
                        return "interrupted"
            elif event[0] == "error":
                print(f"   ! {event[1]}")
            elif event[0] == "done" and event[1]:
                print("   took: " + " · ".join(f"{k} {v}s" for k, v in event[1].items()))
        if not spoke:
            self.mood("confused")
            self.speaker.play(chime((440, 330)))  # falling notes = something went wrong
            return "nothing"
        return "question" if last.rstrip().rstrip('"\')').endswith("?") else "done"

    def announce(self, item):
        """Say a reminder or Home Assistant message (item: the text, or {"text", "picture"})."""
        text = item["text"] if isinstance(item, dict) else item
        if isinstance(item, dict) and item.get("picture"):
            data = self.brain.picture(item["picture"])
            if data:
                try:
                    self.face.show_picture(data, self.picture_seconds)
                    print("   (showing a picture from Home Assistant)", flush=True)
                except Exception as e:   # a broken picture must never stop her saying the message
                    print(f"   ! picture: {e}", flush=True)
        self.mood("speaking", f"(saying) {text}")
        self.speaker.play(chime((523, 659, 784)))  # a little rising tune: a reminder
        audio = self.brain.speak(text)
        if audio and not self.play(audio):
            self.converse()                             # interrupted: listen instead
            return
        self.after_speaking()

    def after_speaking(self):
        # The mic heard Bolt's own voice while it talked. Throw that away, or
        # Bolt might wake itself up!
        self.mic.flush()
        self.wake.reset()
        self.touched.clear()      # a tap while she was busy doesn't start another chat
        self.mood("sleeping")

    # ------------------------------------------------- the reminder checker

    def check_reminders(self, place):
        """One check for new reminders and announcements. `place` remembers where we got to:
        {"boot": the brain's boot code, "seen": the newest number we've had}."""
        answer = self.brain.notifications(place.get("seen") or 0)
        if answer is None:
            return                                      # couldn't ask: try again next time
        self.face.set_timers(answer.get("timers", []))   # the line round her screen
        if place.get("boot") is None:
            # The first answer: skip anything from before Riley's body started.
            place["boot"] = answer["boot"]
            place["seen"] = max((n["id"] for n in answer["items"]), default=0)
            return
        if answer["boot"] != place["boot"]:
            # The brain restarted, so its numbers began again at 1. Everything it has now
            # happened since the restart, so it's all new to us.
            place["boot"], place["seen"] = answer["boot"], 0
            answer = self.brain.notifications(0)
            if answer is None:
                return
        for n in answer["items"]:
            if n["id"] > place["seen"]:
                self.announcements.append({"text": n["text"], "picture": n["picture"]} if n.get("picture") else n["text"])
                place["seen"] = n["id"]

    def watch_for_reminders(self, every=3):
        """Runs in a background THREAD: asks the brain for new reminders."""
        place = {}
        while True:
            try:
                self.check_reminders(place)
            except Exception as e:  # a hiccup must never stop reminders for good
                print(f"   ! reminders: {e}", flush=True)
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
            elif self.button_pressed.is_set() or self.touched.is_set():
                self.button_pressed.clear()
                self.touched.clear()
                if not self.turning_off:
                    print("   (woken by a touch or the button)", flush=True)
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
    from .touch import make_touch
    body.touch = make_touch(body.on_touch)                           # the touch screen, if TOUCH_IRQ_PIN is set
    from .camera import make_camera
    body.camera = make_camera()                                       # the camera, if one is connected
    try:
        import cv2
        cv2.setNumThreads(2)       # OpenCV may use 2 of the Pi's 4 cores: the others stay free for listening
    except ImportError:
        pass
    if body.camera:
        from .faces import FaceBook, make_recogniser
        body.face_people = FaceBook().people                           # faces taught with `faces enroll`
        body.faces = make_recogniser()
        if body.faces:
            print(f"   (recognises {len(body.face_people)} face(s): {', '.join(body.face_people)})", flush=True)
        print("   (camera ready: looks when asked, wakes when it sees someone)", flush=True)
        threading.Thread(target=body.watch_camera, daemon=True).start()
    if body.touch:
        print("   (touch screen ready: tap to talk, hold to turn off)", flush=True)
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
