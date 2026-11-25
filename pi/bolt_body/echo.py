"""
LESSON: Echo cancelling (hearing you over her own voice)
========================================================
While Riley talks, the microphone hears two things: YOU (maybe saying "Hey Riley,
stop") and HER OWN VOICE coming back out of the speaker, much louder, because the
speaker is a few centimetres away. Her own voice drowns you out.

But she knows EXACTLY what she's saying: it's the sound she just sent to the
speaker. So if she can work out what that sound becomes by the time it reaches the
microphone, she can subtract it, and what's left is you. That's echo cancelling,
the thing every phone does on speaker mode.

Two problems to solve:

1. WHEN does her voice reach the mic? Starting the sound takes the Pi a moment,
   and it varies a bit each time. We find out by "cross-correlation": slide her
   voice along what the mic heard until they line up best. (The mic and the amp
   share one sound card, so once lined up, they stay lined up.)

2. WHAT does it sound like by then? The speaker, the brass and the room all
   change it: some pitches louder, some quieter, little echoes off the desk. An
   ADAPTIVE FILTER learns that, all the time: it guesses the echo, compares its
   guess with what the mic really heard, and nudges itself to guess better next
   time. After a sentence or two it's good, and it keeps what it learned.

   While you're talking too, the difference between guess and mic is YOU, not a
   bad guess, so it stops learning for a moment rather than learn your voice.

How well it worked is printed after each sentence: "her voice 18 dB quieter".
Every 10 dB is ten times less sound power. 15 to 25 dB is good for a small speaker.

The filter is a "partitioned block frequency-domain adaptive filter": it does its
sums with FFTs (see the faces lesson's maths, but for sound), so a Pi can keep up.
"""

import numpy as np

RATE = 16000
BLOCK = 256              # samples per step (16 ms)
PARTS = 4                # the filter covers PARTS x BLOCK samples of echo: 64 ms
EARLY = 128              # look this many samples BEFORE the measured delay, to be safe
MAX_DELAY = RATE // 2    # her voice can take up to half a second to reach the mic
FIND_DELAY_AFTER = int(RATE * 0.3)    # mic sound needed before trying to line up
STEP = 0.2               # how big each learning nudge is (too big and it overshoots)


def to_16k(samples, rate):
    """Her voice at the mic's 16,000 samples a second. Piper speaks at 22,050, so it's
    "resampled". Done with an FFT: keep only the pitches 16,000 can hold, then rebuild."""
    samples = np.asarray(samples, dtype=np.float64)
    if rate == RATE or len(samples) == 0:
        return samples
    n = int(round(len(samples) * RATE / rate))
    spectrum = np.fft.rfft(samples)
    keep = n // 2 + 1
    spectrum = spectrum[:keep] if len(spectrum) >= keep else np.pad(spectrum, (0, keep - len(spectrum)))
    return np.fft.irfft(spectrum, n) * (n / len(samples))


def find_delay(mic, voice, max_delay=MAX_DELAY):
    """How many samples later her voice turns up in the mic (or None if it can't tell).
    LESSON: "PHAT" cross-correlation. Comparing every possible delay one by one is slow,
    so it's done with FFTs; whitening the spectrum makes the peak sharp, even in a
    room with echoes."""
    n = len(mic)
    if n < BLOCK or np.abs(voice[:n]).max(initial=0) < 50:
        return None
    size = 1 << int(np.ceil(np.log2(2 * n)))
    cross = np.fft.rfft(mic, size) * np.conj(np.fft.rfft(voice[:n], size))
    lags = np.fft.irfft(cross / (np.abs(cross) + 1e-9), size)[:min(max_delay, n)]
    best = int(np.argmax(lags))
    return best if lags[best] > 5 * np.median(np.abs(lags)) else None


class EchoCanceller:
    def __init__(self):
        self.weights = np.zeros((PARTS, BLOCK + 1), dtype=complex)   # what it's learned (kept between sentences)
        self.delay = None                                            # samples; kept as a first guess next time
        self.voice = np.zeros(0)
        self.started_at = None
        self.converged = False
        self._reset_sentence()

    def _reset_sentence(self):
        self.history = np.zeros((PARTS, BLOCK + 1), dtype=complex)   # her recent voice, as spectra
        self.previous = np.zeros(BLOCK)
        self.power = None                   # how loud each pitch of her voice is lately
        self.heard = []                     # the mic since she started (until the delay is found)
        self.pending = np.zeros(0)          # mic samples waiting to fill a block
        self.pending_at = None
        self.cleaned = np.zeros(0)
        self.before = self.after = 0.0      # loudness in and out, for the report
        self.delay_found = False

    def begin(self, samples, rate, mic_position):
        """She's started saying this. mic_position = how many samples the mic had recorded
        when the sound was started (the mic counts them)."""
        self.voice = to_16k(samples, rate)
        self.started_at = mic_position
        self._reset_sentence()

    def clean(self, frame, position):
        """One frame from the mic (int16 bytes) that started at sample `position`. Returns the
        frame with as much of her voice taken out as it can (the same length)."""
        mic = np.frombuffer(frame, dtype=np.int16).astype(np.float64)
        if self.started_at is None:
            return frame
        since = position - self.started_at
        if not self.delay_found:
            if not self.heard:
                self.heard_from = since       # where the first frame started, relative to her voice
            self.heard.append(mic)
            heard = np.concatenate(self.heard)
            if len(heard) >= FIND_DELAY_AFTER:
                lag = find_delay(heard, self.voice)
                if lag is not None:
                    self.delay, self.delay_found, self.heard = lag + self.heard_from, True, []
                elif len(heard) > RATE * 2:   # can't line up (too quiet?): give up for this sentence
                    self.heard, self.started_at = [], None
            if not self.delay_found:
                return frame                  # not lined up yet: as heard (guessing would teach it wrong)
        self.pending = np.concatenate([self.pending, mic])
        if self.pending_at is None:
            self.pending_at = since
        while len(self.pending) >= BLOCK:
            block, self.pending = self.pending[:BLOCK], self.pending[BLOCK:]
            self.cleaned = np.concatenate([self.cleaned, self._step(block, self.pending_at)])
            self.pending_at += BLOCK
        out, self.cleaned = self.cleaned[:len(mic)], self.cleaned[len(mic):]
        if len(out) < len(mic):              # still filling the first block: pass it through
            out = np.concatenate([mic[:len(mic) - len(out)], out])
        return np.clip(out, -32768, 32767).astype(np.int16).tobytes()

    def _step(self, mic, at):
        """One block: guess her voice in the mic, subtract it, learn from the difference."""
        start = at - self.delay + EARLY     # her voice from EARLY samples AHEAD of the echo
        voice = self.voice[max(0, start):max(0, start + BLOCK)]
        if start < 0:
            voice = np.concatenate([np.zeros(min(BLOCK, -start)), voice])
        voice = np.pad(voice, (0, BLOCK - len(voice)))
        spectrum = np.fft.rfft(np.concatenate([self.previous, voice]))
        self.previous = voice
        self.history = np.roll(self.history, 1, axis=0)
        self.history[0] = spectrum
        guess = np.fft.irfft((self.weights * self.history).sum(axis=0))[BLOCK:]
        left = mic - guess

        talking = float(voice @ voice) > BLOCK * 30.0 ** 2
        if talking:
            self.before += float(mic @ mic)
            self.after += float(left @ left)
        # Learn, unless someone else is talking too (then "left" is them, not a bad guess).
        both_talking = self.converged and float(left @ left) > 2.0 * float(guess @ guess) + BLOCK * 100.0
        if talking and not both_talking:
            loud = np.abs(spectrum) ** 2
            self.power = loud if self.power is None else 0.9 * self.power + 0.1 * loud
            error = np.fft.rfft(np.concatenate([np.zeros(BLOCK), left]))
            # LESSON: each pitch learns in proportion to how loud it is, so quiet ones
            # don't get huge nudges (the small extra on the bottom keeps that safe)
            nudge = STEP * np.conj(self.history) * error / (self.power + 0.01 * self.power.mean() + 1e3)
            nudge = np.fft.rfft(np.concatenate([np.fft.irfft(nudge, axis=1)[:, :BLOCK],
                                                np.zeros((PARTS, BLOCK))], axis=1), axis=1)
            self.weights += nudge
        return left

    def report(self):
        """How much quieter her voice got in this sentence, in decibels (or None)."""
        if self.before <= 0 or self.after <= 0:
            return None
        db = 10 * np.log10(self.before / self.after)
        self.converged = db > 10
        return round(float(db), 1)
