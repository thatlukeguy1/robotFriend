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
        self.model = Model(wakeword_models=[model], inference_framework="onnx")
        self.threshold = threshold
        self.last_score = 0.0

    def heard(self, frame):
        """Feed one 80 ms frame. True if the wake word was just said."""
        scores = self.model.predict(np.frombuffer(frame, dtype=np.int16))
        self.last_score = max(scores.values())
        return self.last_score >= self.threshold

    def reset(self):
        """Forget recent sound, so one 'Hey Bolt' doesn't trigger twice."""
        self.model.reset()
