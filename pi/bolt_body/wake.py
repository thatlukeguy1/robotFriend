"""
LESSON: The wake word
=====================
Bolt can't send everything it hears to the mini PC: that would be slow and
creepy. Instead, a tiny AI model runs ON THE PI and does one job: listen
for "Hey Bolt". Only after it hears that does Bolt start recording.

For every 80 ms frame, the model gives a SCORE from 0 to 1: how sure it is
that it just heard the wake word. Above the THRESHOLD (0.5) counts as a yes.
  * Too many false alarms? Raise the threshold (e.g. 0.7).
  * Has to be shouted? Lower it (e.g. 0.3).

The model file comes from openWakeWord. "hey_jarvis" works out of the box;
"Hey Bolt" needs a custom model trained for it (see LEARN.md).
"""

import numpy as np


class WakeWord:
    def __init__(self, model="hey_jarvis", threshold=0.5):
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        if not model.endswith(".onnx"):
            download_models(model_names=[model])  # built-in models download once
        try:
            self.model = Model(wakeword_models=[model], inference_framework="onnx")
        except ValueError as e:
            raise SystemExit(
                f"! There's no wake word model called '{model}'. Set WAKE_MODEL in pi/bolt.env to "
                "hey_jarvis (it works out of the box), or to the path of a trained .onnx file "
                "(e.g. a 'Hey Bolt' model, once it's trained).") from e
        self.threshold = threshold
        self.frames_needed = 1     # how many checks IN A ROW must pass (Studio: Body tab)
        self.last_score = 0.0
        self.in_a_row = 0

    def heard(self, frame):
        """Feed one 80 ms frame. True if the wake word was just said.

        LESSON: a real "Hey Riley" usually scores high for several checks in a row
        (the word lasts a while), but a stray sound from the TV often spikes for just
        one. Needing 2 in a row filters out many of those spikes, at the cost of
        waking 80 ms later."""
        scores = self.model.predict(np.frombuffer(frame, dtype=np.int16))
        return self.judge(max(scores.values()))

    def judge(self, score):
        self.last_score = score
        self.in_a_row = self.in_a_row + 1 if score >= self.threshold else 0
        return self.in_a_row >= self.frames_needed

    def reset(self):
        """Forget recent sound, so one 'Hey Riley' doesn't trigger twice."""
        self.model.reset()
        self.in_a_row = 0
