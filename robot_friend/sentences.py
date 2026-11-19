"""
LESSON: Chopping a stream into sentences
========================================
Claude's reply arrives a few words at a time:  "Sure", " thing!", " I'll turn", ...
Piper speaks best with a whole sentence at once (so it gets the tone right),
so we collect the pieces and hand over each sentence the moment it ends.

A sentence ends at . ! ? (or a new line), followed by a space.
"""

import re

END = re.compile(r'(?<=[.!?…])["\')\]]*\s+|\n+')


def sentences(pieces, min_length=6):
    """
    Turn a stream of text pieces into a stream of whole sentences.
    Very short sentences ("Ok.") are joined to the next one so Bolt doesn't speak in tiny bursts.
    """
    buffer = ""
    for piece in pieces:
        buffer += piece
        while True:
            match = END.search(buffer)
            if not match:
                break
            sentence, rest = buffer[:match.end()].strip(), buffer[match.end():]
            if len(sentence) < min_length and rest.strip():
                # too short: wait and join it with the next sentence
                nxt = END.search(rest)
                if not nxt:
                    break
                sentence = (sentence + " " + rest[:nxt.end()].strip()).strip()
                rest = rest[nxt.end():]
            buffer = rest
            if sentence:
                yield sentence
    if buffer.strip():
        yield buffer.strip()
