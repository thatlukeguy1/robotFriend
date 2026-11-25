"""Who's home (Home Assistant), who's at the desk (the camera), and greetings."""
from types import SimpleNamespace as Obj

from robot_friend.body_settings import BodySettingsStore, DEFAULTS
from robot_friend.brain import Brain
from robot_friend.presence import PresenceBook, same_person
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app, presence_watch


class Clock:
    def __init__(self): self.now = 1_000_000.0
    def __call__(self): return self.now


def people(luke="home", sarah="not_home"):
    return [{"entity_id": "person.luke", "name": "Luke", "state": luke},
            {"entity_id": "person.sarah", "name": "Sarah", "state": sarah}]


def test_arrivals_are_spotted_but_not_on_the_first_look():
    book = PresenceBook()
    assert book.update_home(people()) == []                        # already home when Riley started
    assert book.update_home(people(sarah="not_home")) == []
    assert book.update_home(people(sarah="home")) == ["Sarah"]
    assert book.update_home(people(sarah="home")) == []            # still home: not a new arrival
    assert book.summary()["home"] == ["Luke", "Sarah"]


def test_greetings_at_most_every_three_hours_and_home_counts_for_the_desk():
    clock = Clock()
    book = PresenceBook(clock=clock)
    assert book.should_greet("Luke Newman") is True                # welcomed home...
    clock.now += 60
    assert book.should_greet("Luke") is False                      # ...so not again when he sits down
    clock.now += 3 * 3600
    assert book.should_greet("Luke") is True


def test_who_is_at_the_desk_fades_after_ten_minutes():
    clock = Clock()
    book = PresenceBook(clock=clock)
    book.seen_at_desk("Luke")
    assert book.at_desk() == ["Luke"]
    clock.now += 11 * 60
    assert book.at_desk() == []


def test_same_person_matches_first_names():
    assert same_person("Luke Newman", "luke") and not same_person("Luke", "Lucy") and not same_person("", "")


def test_claude_is_told_who_is_at_the_desk(tmp_path):
    book = PresenceBook()
    book.seen_at_desk("Luke")
    sent = []
    claude = Obj(messages=Obj(create=lambda **kw: sent.append(kw["messages"][-1]["content"]) or
                              Obj(stop_reason="end_turn", content=[Obj(type="text", text="ok")])))
    Brain(ReminderStore(tmp_path / "r.json"), client=claude, presence=book).chat("remember I like tea")
    assert "[At your desk, recognised by your camera: Luke] remember I like tea" in sent[0]


def test_the_pi_reports_a_face_and_riley_says_hello(tmp_path):
    book = PresenceBook()
    claude = Obj(messages=Obj(create=lambda **kw: Obj(stop_reason="end_turn", content=[Obj(type="text", text="[happy] Hi Luke!")])))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude, presence=book)
    notes = Notifications()
    web = create_app(brain, notes, security=Security(tmp_path, open_for_testing=True),
                     body_settings=BodySettingsStore(tmp_path / "b.json")).test_client()
    assert web.post("/presence", json={"name": "Luke"}).get_json()["status"] == "greeting"
    import time
    for _ in range(50):
        if notes.after(0): break
        time.sleep(0.02)
    assert [n["text"] for n in notes.after(0)] == ["Hi Luke!"]            # stage directions taken out
    assert web.post("/presence", json={"name": "Luke"}).get_json()["status"] == "noted"   # not twice
    assert book.at_desk() == ["Luke"]


def test_greetings_can_be_switched_off(tmp_path):
    settings = BodySettingsStore(tmp_path / "b.json")
    settings.save({**DEFAULTS, "greetings": "off"})
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, presence=PresenceBook())
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True), body_settings=settings).test_client()
    assert web.post("/presence", json={"name": "Luke"}).get_json()["status"] == "noted"


def test_presence_watch_welcomes_arrivals(tmp_path):
    states = [people(sarah="not_home"), people(sarah="home")]
    home = Obj(can_control=True, people=lambda: states.pop(0))
    claude = Obj(messages=Obj(create=lambda **kw: Obj(stop_reason="end_turn", content=[Obj(type="text", text="Welcome back, Sarah!")])))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude, home=home, presence=PresenceBook())
    class Stop:
        n = 0
        def is_set(self): return self.n >= 2
        def wait(self, s): self.n += 1
    notes = Notifications()
    presence_watch(brain, notes, Stop(), BodySettingsStore(tmp_path / "b.json"))
    assert [n["text"] for n in notes.after(0)] == ["Welcome back, Sarah!"]


def test_who_is_home_tool(tmp_path):
    book = PresenceBook()
    book.update_home(people())
    said = Brain(ReminderStore(tmp_path / "r.json"), client=None, presence=book).run_tool("who_is_home", {})
    assert '"home": ["Luke"]' in said and '"away": ["Sarah"]' in said
