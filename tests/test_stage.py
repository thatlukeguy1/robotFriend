"""Stage directions: moods and props come out of the reply before it's spoken."""
import json

from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from robot_friend.stage import split_cues, without_cues
from server import Notifications, create_app


def test_moods_and_props_are_taken_out():
    words, cues = split_cues("[sad] Oh no, your train's cancelled. [show:🚆 22:15] The next one's later.")
    assert words == "Oh no, your train's cancelled. The next one's later."
    assert cues == [("mood", "sad"), ("show", "🚆", "22:15")]


def test_neutral_means_her_normal_talking_face_and_case_doesnt_matter():
    assert split_cues("[Neutral] Right.")[1] == [("mood", "speaking")]


def test_props_must_be_pictures_and_text_is_kept_short():
    assert split_cues("[show:sun] Hi")[1] == []                       # a word isn't a prop
    assert split_cues("[show:☀️ twelve degrees] Hi")[1] == [("show", "☀️", "twelve d")]
    assert without_cues("[show:☀️]") == ""


def test_ordinary_brackets_are_left_alone():
    assert without_cues("The answer [roughly] is 4.") == "The answer [roughly] is 4."


def test_the_voice_stream_sends_directions_before_their_sentence(tmp_path):
    from test_voice import StreamingClaude, make_wav
    brain = Brain(ReminderStore(tmp_path / "r.json"),
                  client=StreamingClaude(["[happy] Good news! ", "[show:☀️ 21°] It'll be sunny."]))
    web = create_app(brain, Notifications(), ears=lambda wav: "weather?", mouth=lambda t: t.encode(),
                     security=Security(tmp_path, open_for_testing=True)).test_client()
    lines = [json.loads(l) for l in web.post("/voice/stream", data=make_wav(), content_type="audio/wav").data.decode().splitlines()]
    assert [l["type"] for l in lines] == ["heard", "mood", "say", "show", "say", "done"]
    assert lines[1]["name"] == "happy" and lines[3] == {"type": "show", "emoji": "☀️", "text": "21°"}
    assert [l["text"] for l in lines if l["type"] == "say"] == ["Good news!", "It'll be sunny."]
    assert lines[-1]["reply"] == "Good news! It'll be sunny."


def test_typed_chat_gets_clean_words_and_the_cues(tmp_path):
    from types import SimpleNamespace as Obj
    claude = Obj(messages=Obj(create=lambda **kw: Obj(stop_reason="end_turn",
                                                       content=[Obj(type="text", text="[surprised] Really? Wow.")])))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude)
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True)).test_client()
    assert web.post("/chat", json={"text": "guess what"}).get_json() == {"reply": "Really? Wow.", "cues": [["mood", "surprised"]]}
