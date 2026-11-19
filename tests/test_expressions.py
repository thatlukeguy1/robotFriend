"""Tests for saving eye designs from the Eye Studio."""

import copy
import json

import pytest

from robot_friend.expressions import ORIGINAL, DesignError, DesignStore, validate
from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app


def original():
    return json.loads(ORIGINAL.read_text())


# --------------------------------------------------------------- checking

def test_original_design_is_valid():
    validate(original())


@pytest.mark.parametrize("break_it, message", [
    (lambda d: d["colors"].update(iris="blu"), "colors.iris"),
    (lambda d: d["face"].update(eyeWidth=5), "face.eyeWidth"),
    (lambda d: d["expressions"]["happy"].update(mouthSmile=3), "happy.mouthSmile"),
    (lambda d: d["expressions"]["happy"].update(open="lots"), "happy.open"),
    (lambda d: d["expressions"]["happy"].update(open=float("nan")), "happy.open"),
    (lambda d: d["expressions"]["happy"].update(sparkle=1), "unknown setting"),
    (lambda d: d["expressions"]["confused"]["left"].update(tilt=99), "confused.left.tilt"),
    (lambda d: d["expressions"].pop("sleeping"), "sleeping"),
    (lambda d: d["expressions"].update({"Bad Name!": {}}), "good expression name"),
    (lambda d: d["defaults"].update(browShow="lots"), "defaults.browShow"),
    (lambda d: d.pop("colors"), "missing 'colors'"),
])
def test_bad_designs_are_refused(break_it, message):
    d = original()
    break_it(d)
    with pytest.raises(DesignError, match=message):
        validate(d)


def test_new_expressions_and_per_eye_settings_are_fine():
    d = original()
    d["expressions"]["surprised"] = {"open": 1, "pupil": 0.5, "left": {"lookX": -0.2}}
    validate(d)


# ------------------------------------------------------- saving and undoing

def test_save_undo_reset(tmp_path):
    store = DesignStore(tmp_path / "expressions.json")
    assert not store.is_custom() and store.current() == original()

    pink = original(); pink["colors"]["iris"] = "#ff00aa"
    store.save(pink)
    assert store.is_custom() and store.current()["colors"]["iris"] == "#ff00aa"

    green = copy.deepcopy(pink); green["colors"]["iris"] = "#00ff66"
    store.save(green)
    store.undo()
    assert store.current()["colors"]["iris"] == "#ff00aa"   # back to the previous save

    store.reset()
    assert not store.is_custom() and store.current() == original()


def test_bad_design_never_replaces_a_good_one(tmp_path):
    store = DesignStore(tmp_path / "expressions.json")
    good = original(); good["colors"]["iris"] = "#ff00aa"
    store.save(good)
    bad = original(); bad["face"]["lookRange"] = -3
    with pytest.raises(DesignError):
        store.save(bad)
    assert store.current()["colors"]["iris"] == "#ff00aa"


def test_undo_with_nothing_to_undo(tmp_path):
    with pytest.raises(DesignError):
        DesignStore(tmp_path / "expressions.json").undo()


# ---------------------------------------------------------------- the routes

def test_routes(tmp_path):
    store = DesignStore(tmp_path / "expressions.json")
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=object())
    web = create_app(brain, Notifications(), designs=store, security=Security(tmp_path, open_for_testing=True)).test_client()

    assert web.get("/static/expressions.json").headers["X-Bolt-Design"] == "original"
    pink = original(); pink["colors"]["iris"] = "#ff00aa"
    assert web.put("/expressions", json=pink).status_code == 200
    response = web.get("/static/expressions.json")
    assert response.get_json()["colors"]["iris"] == "#ff00aa" and response.headers["X-Bolt-Design"] == "custom"

    bad = original(); bad["colors"]["iris"] = "nope"
    response = web.put("/expressions", json=bad)
    assert response.status_code == 400 and "colors.iris" in response.get_json()["error"]

    assert web.post("/expressions/reset").get_json()["design"] == original()
    assert web.post("/expressions/undo").get_json()["design"]["colors"]["iris"] == "#ff00aa"


def test_old_two_round_eyes_designs_are_upgraded(tmp_path):
    old = original()
    old.pop("face")
    old["eye"] = {"irisRadius": 0.7, "pupilRadius": 0.37, "lookRange": 0.41}
    for k in ("brow", "mouth"):
        old["colors"].pop(k)
    old["colors"]["iris"] = "#ff00aa"
    old["expressions"]["happy"] = {"open": 0.5}
    store = DesignStore(tmp_path / "expressions.json")
    (tmp_path / "expressions.json").write_text(json.dumps(old))
    current = store.current()
    assert "face" in current and "eye" not in current
    assert current["colors"]["iris"] == "#ff00aa"           # their colour kept
    assert current["expressions"]["happy"] == {"open": 0.5}   # their expression kept
    validate(current)


def test_designs_saved_before_brow_show_existed_still_work(tmp_path):
    older = original()
    older["defaults"].pop("browShow"); older["defaults"].pop("browArch")
    store = DesignStore(tmp_path / "expressions.json")
    (tmp_path / "expressions.json").write_text(json.dumps(older))
    current = store.current()
    assert current["defaults"]["browShow"] == 0
    validate(current)
