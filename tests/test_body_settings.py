"""The body's settings: kept by the brain, edited in the Studio, fetched by the Pi."""
import pytest

from robot_friend.body_settings import DEFAULTS, BodySettingsStore, SettingsError, validate


def test_defaults_until_saved(tmp_path):
    store = BodySettingsStore(tmp_path / "body.json")
    assert store.current() == DEFAULTS and not store.is_custom()


def test_save_and_reset(tmp_path):
    store = BodySettingsStore(tmp_path / "body.json")
    store.save({**DEFAULTS, "volume": 60, "replies": ["  Yes?  ", "", "Hiya!"]})
    assert store.current()["volume"] == 60 and store.current()["replies"] == ["Yes?", "Hiya!"] and store.is_custom()
    store.reset()
    assert store.current() == DEFAULTS


@pytest.mark.parametrize("bad", [{"volume": 500}, {"volume": "loud"}, {"listen_seconds": 0},
                                 {"replies": "Yes?"}, {"replies": ["x" * 80]}, {"volume": True},
                                 {"christmas_hat": "yes"}, {"christmas_hat": 1}, {"christmas_hat": None}])
def test_limits_are_enforced(bad):
    with pytest.raises(SettingsError):
        validate({**DEFAULTS, **bad})


def test_routes(tmp_path):
    from robot_friend.brain import Brain
    from robot_friend.reminders import ReminderStore
    from robot_friend.security import Security
    from server import Notifications, create_app
    from test_server import EchoClaude
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=EchoClaude())
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True),
                     body_settings=BodySettingsStore(tmp_path / "body.json")).test_client()
    got = web.get("/body-settings").get_json()
    assert got["current"] == DEFAULTS and got["custom"] is False and got["form"]["numbers"][0]["key"] == "volume"
    assert web.put("/body-settings", json={**DEFAULTS, "volume": 900}).status_code == 400
    assert web.put("/body-settings", json={**DEFAULTS, "volume": 40}).get_json()["current"]["volume"] == 40
    assert web.get("/body-settings").get_json()["custom"] is True
    assert web.post("/body-settings/reset").get_json()["current"]["volume"] == 100


def test_christmas_hat_choice(tmp_path):
    import json
    from datetime import date
    from robot_friend.body_settings import hat_wanted
    store = BodySettingsStore(tmp_path / "body.json")
    assert store.current()["christmas_hat"] == "auto"
    store.save({**DEFAULTS, "christmas_hat": True})                 # the old tick box still works...
    assert store.current()["christmas_hat"] == "on"                 # ...and becomes "on"
    (tmp_path / "old.json").write_text(json.dumps({**DEFAULTS, "christmas_hat": False}))
    assert BodySettingsStore(tmp_path / "old.json").current()["christmas_hat"] == "off"
    season = [date(2026, 11, 25), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 6)]
    not_season = [date(2026, 11, 24), date(2027, 1, 7), date(2027, 7, 4)]
    assert all(hat_wanted("auto", d) for d in season) and not any(hat_wanted("auto", d) for d in not_season)
    assert hat_wanted("on", date(2027, 7, 4)) and not hat_wanted("off", date(2026, 12, 25))
