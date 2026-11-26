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


class WeatherHome:
    can_control = True
    def weather_today(self):
        return {"where": "Letchworth", "now": "cloudy", "temperature": 5.4, "unit": "°C",
                "today": {"condition": "cloudy", "temperature": 7, "templow": 2}}


def test_weather_cues_come_from_the_real_weather():
    from robot_friend.stage import weather_cue
    assert weather_cue({"now": "rainy", "temperature": 7.6}) == "[show:🌧️ 8°]"
    assert weather_cue({"now": "sunny"}) == "[show:☀️]"
    assert weather_cue({"now": "something-new", "temperature": 3}) == "" and weather_cue(None) == ""


def test_asking_about_the_weather_holds_up_the_weather_prop(tmp_path):
    from types import SimpleNamespace as Obj
    from test_voice import make_wav
    turns = [
        (["[neutral] Let me look."], Obj(stop_reason="tool_use", content=[
            Obj(type="text", text="[neutral] Let me look."), Obj(type="tool_use", id="t1", name="weather", input={})])),
        (["[sad] It's cloudy and about five degrees."], Obj(stop_reason="end_turn", content=[
            Obj(type="text", text="[sad] It's cloudy and about five degrees.")])),
    ]
    n = []
    def stream(**kw):
        pieces, final = turns[len(n)]; n.append(1)
        class S:
            text_stream = iter(pieces)
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def get_final_message(s): return final
        return S()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=Obj(messages=Obj(stream=stream)), home=WeatherHome())
    web = create_app(brain, Notifications(), ears=lambda wav: "what's the weather?", mouth=lambda t: t.encode(),
                     security=Security(tmp_path, open_for_testing=True)).test_client()
    lines = [json.loads(l) for l in web.post("/voice/stream", data=make_wav(), content_type="audio/wav").data.decode().splitlines()]
    shows = [l for l in lines if l["type"] == "show"]
    assert shows == [{"type": "show", "emoji": "☁️", "text": "5°"}]               # the brain chose it
    assert [l["text"] for l in lines if l["type"] == "say"] == ["Let me look.", "It's cloudy and about five degrees."]
    assert brain.stage_waiting == ""


def test_the_clock_prop_shows_the_nearest_clock_face():
    from datetime import datetime
    from robot_friend.stage import time_cue
    assert time_cue(datetime(2026, 11, 24, 14, 5)) == "[show:🕑 14:05]"
    assert time_cue(datetime(2026, 11, 24, 14, 28)) == "[show:🕝 14:28]"    # half past two
    assert time_cue(datetime(2026, 11, 24, 23, 50)) == "[show:🕛 23:50]"    # nearly midnight


def test_time_questions_are_spotted():
    from robot_friend.stage import is_time_question
    for q in ["What time is it?", "what's the time", "Have you got the time?", "tell me the time please",
              "Riley what time is it"]:
        assert is_time_question(q), q
    for q in ["Set a timer", "what time is the dentist?", "is it time for tea"]:
        assert not is_time_question(q), q


def test_asking_the_time_holds_up_the_clock_straight_away(tmp_path):
    from datetime import datetime
    from test_voice import StreamingClaude
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=StreamingClaude(["[neutral] It's five past two."]))
    from robot_friend.sentences import sentences
    from robot_friend.stage import split_cues
    first = next(iter(sentences(brain.chat_stream("what time is it?", now=datetime(2026, 11, 24, 14, 5)))))
    assert split_cues(first) == ("It's five past two.", [("show", "🕑", "14:05"), ("mood", "speaking")])


def test_the_new_moods_and_an_eye_roll():
    from robot_friend.stage import split_cues
    words, cues = split_cues("[sarcastic] Oh great, Monday. [eyeroll] Again. [annoyed] And the printer's jammed.")
    assert words == "Oh great, Monday. Again. And the printer's jammed."
    assert cues == [("mood", "sarcastic"), ("mood", "eyeroll"), ("mood", "annoyed")]
