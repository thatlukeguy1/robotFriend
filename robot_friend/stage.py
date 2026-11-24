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


# Home Assistant's weather conditions -> the prop for them
WEATHER_EMOJI = {"sunny": "☀️", "clear-night": "🌙", "partlycloudy": "⛅", "cloudy": "☁️", "fog": "🌫️",
                 "rainy": "🌧️", "pouring": "🌧️", "lightning": "🌩️", "lightning-rainy": "⛈️", "hail": "🌨️",
                 "snowy": "❄️", "snowy-rainy": "🌨️", "windy": "💨", "windy-variant": "💨", "exceptional": "⚠️"}


def weather_cue(weather):
    """The prop for a weather report, e.g. "[show:☁️ 5°]" (or "" if there's nothing to show).
    Made by the brain from the REAL weather, rather than relying on Claude to remember."""
    if not isinstance(weather, dict):
        return ""
    emoji = WEATHER_EMOJI.get(str(weather.get("now", "")))
    if not emoji:
        return ""
    temp = weather.get("temperature")
    text = f"{round(temp)}°" if isinstance(temp, (int, float)) and not isinstance(temp, bool) else ""
    return f"[show:{emoji} {text}]".replace(" ]", "]")


CLOCK_ON_THE_HOUR = "🕛🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚"       # 12 o'clock, 1 o'clock, ... 11 o'clock
CLOCK_HALF_PAST = "🕧🕜🕝🕞🕟🕠🕡🕢🕣🕤🕥🕦"         # half past 12, half past 1, ...
TIME_QUESTION = re.compile(r"\bwhat(?:'s| is)? the time\b|\bwhat time (?:is it|it is)\b|\btime is it\b"
                           r"|\b(?:got|have) the time\b|\btell me the time\b", re.IGNORECASE)


def is_time_question(text):
    return bool(TIME_QUESTION.search(text or ""))


def time_cue(now):
    """The clock prop for a time, e.g. "[show:🕝 14:28]". LESSON: there's a clock-face emoji for
    every hour and half hour, so we pick the nearest one: the little picture shows the real time."""
    hour, minute = now.hour % 12, now.minute
    if minute >= 45:
        face = CLOCK_ON_THE_HOUR[(hour + 1) % 12]
    elif minute >= 15:
        face = CLOCK_HALF_PAST[hour]
    else:
        face = CLOCK_ON_THE_HOUR[hour]
    return f"[show:{face} {now:%H:%M}]"


def without_cues(text):
    """Just the words (for the typed chat, and anything else that isn't the face)."""
    return split_cues(text)[0]
