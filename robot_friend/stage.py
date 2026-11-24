"""
LESSON: Stage directions
========================
In a play's script, words in [brackets] aren't said out loud: they tell the actor
what to DO. "[sighs] Fine." Riley's replies work the same way. Claude writes:

    [sad] Oh no, your train's cancelled. [show:🚆 22:15] The next one is at quarter past ten.

and before anything is spoken, this file takes the [brackets] out:
  * [happy] [sad] [surprised] [confused] [neutral] -> her FACE changes (a "mood")
  * [show:🚆 22:15] -> a PROP appears on her screen: one emoji, plus a few
    characters of big text (a time, a temperature)
Only the rest, "Oh no, your train's cancelled. The next one is at quarter past
ten.", goes to the voice.

The brain sends the directions to the Pi (and the chat page) as their own events,
so the face changes just before the sentence it belongs to is spoken.
"""

import re

MOODS = {"happy": "happy", "sad": "sad", "surprised": "surprised", "confused": "confused", "neutral": "speaking"}
CUE = re.compile(r"\[(happy|sad|surprised|confused|neutral)\]|\[show:\s*([^\]\n]{1,40})\]", re.IGNORECASE)
MAX_PROP_TEXT = 8


def split_cues(text):
    """("words to say", [("mood", expression), ("show", emoji, text)...]) from one piece of reply."""
    cues = []
    for m in CUE.finditer(text):
        if m.group(1):
            cues.append(("mood", MOODS[m.group(1).lower()]))
        else:
            emoji, _, label = m.group(2).strip().partition(" ")
            if emoji and not emoji.isascii():          # a picture, not a word
                cues.append(("show", emoji[:16], label.strip()[:MAX_PROP_TEXT]))
    words = re.sub(r"\s{2,}", " ", CUE.sub("", text)).strip()
    return words, cues


def without_cues(text):
    """Just the words (for the typed chat, and anything else that isn't the face)."""
    return split_cues(text)[0]
