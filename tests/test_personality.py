"""Tests for Bolt's personality: the editable character and the protected rules."""

from types import SimpleNamespace as Obj

import pytest

from robot_friend.brain import Brain
from robot_friend.memory import MemoryStore
from robot_friend.personality import (DEFAULT_CHARACTER, PRESETS, RULES, CharacterError, CharacterStore,
                                      build_prompt, validate)
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app


class RecordingClaude:
    def __init__(self):
        self.calls = []
        self.messages = Obj(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return Obj(stop_reason="end_turn", content=[Obj(type="text", text="Arr, hello!")])


PIRATE = {"name": "Captain Bolt", "who": "A salty old pirate robot.", "talk": "Talk like a pirate."}


# ------------------------------------------------------- the character

def test_prompt_always_includes_the_rules():
    prompt = build_prompt(PIRATE)
    assert prompt.startswith("You are Captain Bolt") and "A salty old pirate robot." in prompt
    assert RULES in prompt  # the protected part is always there


def test_presets_and_default_are_valid():
    validate(DEFAULT_CHARACTER)
    for preset in PRESETS.values():
        validate({**preset, "name": "Bolt"})


@pytest.mark.parametrize("change, message", [
    ({"name": ""}, "name"),
    ({"name": "Bolt!!"}, "name can use"),
    ({"name": "x" * 30}, "too long"),
    ({"who": ""}, "who"),
    ({"who": "a" * 3000}, "too long"),
    ({"talk": 42}, "must be text"),
])
def test_bad_characters_are_refused(change, message):
    with pytest.raises(CharacterError, match=message):
        validate({**PIRATE, **change})


def test_save_undo_reset(tmp_path):
    store = CharacterStore(tmp_path / "personality.json")
    assert store.current() == DEFAULT_CHARACTER and not store.is_custom()
    store.save(PIRATE)
    assert store.name() == "Captain Bolt"
    store.save({**PIRATE, "name": "Admiral Bolt"})
    store.undo()
    assert store.name() == "Captain Bolt"
    store.reset()
    assert store.current() == DEFAULT_CHARACTER


# ---------------------------------------------------------- the brain

def test_brain_uses_the_saved_character_and_memories(tmp_path):
    store = CharacterStore(tmp_path / "p.json"); store.save(PIRATE)
    memories = MemoryStore(tmp_path / "m.json"); memories.add("Luke likes tea.")
    claude = RecordingClaude()
    Brain(ReminderStore(tmp_path / "r.json"), client=claude, memories=memories, character=store).chat("hi")
    system = claude.calls[0]["system"]
    assert "Captain Bolt" in system and RULES in system and "Luke likes tea." in system


def test_try_character_has_no_tools_and_leaves_the_real_chat_alone(tmp_path):
    claude = RecordingClaude()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude)
    assert brain.try_character(PIRATE, [{"role": "user", "content": "hello"}]) == "Arr, hello!"
    assert "tools" not in claude.calls[0] and "Captain Bolt" in claude.calls[0]["system"]
    assert brain.messages == []


# ---------------------------------------------------------- the routes

def make(tmp_path):
    claude = RecordingClaude()
    store = CharacterStore(tmp_path / "p.json")
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude)
    web = create_app(brain, Notifications(), characters=store,
                     security=Security(tmp_path, open_for_testing=True)).test_client()
    return brain, store, web


def test_get_and_save(tmp_path):
    brain, store, web = make(tmp_path)
    data = web.get("/personality").get_json()
    assert data["current"]["name"] == "Bolt" and data["rules"] == RULES and "Pirate robot" in data["presets"]

    brain.messages = [{"role": "user", "content": "old chat"}]
    assert web.put("/personality", json=PIRATE).status_code == 200
    assert store.name() == "Captain Bolt"
    assert brain.messages == []  # saving starts a fresh conversation
    assert web.get("/health").get_json()["robot"] == "Captain Bolt"

    assert web.put("/personality", json={**PIRATE, "name": ""}).status_code == 400
    assert web.post("/personality/reset").get_json()["current"]["name"] == "Bolt"
    assert web.post("/personality/undo").get_json()["current"]["name"] == "Captain Bolt"


def test_try_route(tmp_path):
    _, _, web = make(tmp_path)
    ok = web.post("/personality/try", json={"character": PIRATE, "history": [{"role": "user", "content": "hi"}]})
    assert ok.get_json() == {"reply": "Arr, hello!"}
    for bad in ([], [{"role": "assistant", "content": "hi"}], [{"role": "system", "content": "x"}],
                [{"role": "user", "content": "x" * 2000}], [{"role": "user", "content": "hi"}] * 13):
        assert web.post("/personality/try", json={"character": PIRATE, "history": bad}).status_code == 400
    assert web.post("/personality/try", json={"character": {**PIRATE, "name": ""},
                                              "history": [{"role": "user", "content": "hi"}]}).status_code == 400


def test_her_face_follows_her_character():
    from robot_friend.personality import RULES
    assert "Your face shows YOUR CHARACTER" in RULES and "[sarcastic]" in RULES
    assert "never at your owner" in RULES


def test_her_usual_face():
    import pytest
    from robot_friend.personality import (CharacterError, DEFAULT_CHARACTER, PRESETS, build_prompt,
                                          usual_face, validate)
    butler = validate({**DEFAULT_CHARACTER, **PRESETS["Dry-witted butler"]})
    assert butler["face"] == "unimpressed" and usual_face(butler) == "unimpressed"
    assert "Your usual face is [unimpressed]" in build_prompt(butler)
    assert "never [happy] just because the job worked" in build_prompt(DEFAULT_CHARACTER)
    old = {k: v for k, v in DEFAULT_CHARACTER.items() if k != "face"}     # saved before faces existed
    assert validate(old)["face"] == "speaking" and usual_face(old) == "speaking"
    with pytest.raises(CharacterError):
        validate({**DEFAULT_CHARACTER, "face": "furious"})


def test_replies_start_with_her_usual_face(tmp_path):
    from types import SimpleNamespace as Obj
    from robot_friend.brain import Brain
    from robot_friend.personality import CharacterStore, DEFAULT_CHARACTER, PRESETS
    from robot_friend.reminders import ReminderStore
    from robot_friend.security import Security
    from server import Notifications, create_app
    store = CharacterStore(tmp_path / "p.json")
    store.save({**DEFAULT_CHARACTER, **PRESETS["Dry-witted butler"]})
    reply = Obj(stop_reason="end_turn", content=[Obj(type="text", text="The lights are on, sir.")])
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=Obj(messages=Obj(create=lambda **kw: reply)), character=store)
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True), characters=store).test_client()
    assert web.post("/chat", json={"text": "lights on"}).get_json()["cues"][0] == ["mood", "unimpressed"]
    assert "unimpressed" in web.get("/personality").get_json()["faces"]
