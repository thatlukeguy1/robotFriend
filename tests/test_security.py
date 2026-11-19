"""
Tests for the lock. Most of these try to get past it, and must fail.
"""

import json
import stat

import pytest

from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import MAX_TRIES, Security
from server import Notifications, create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def setup(tmp_path):
    security = Security(tmp_path)
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=object())
    app = create_app(brain, Notifications(), security=security)
    return security, app.test_client()


def log_in(web, password=PASSWORD):
    return web.post("/login", json={"password": password})


# ------------------------------------------------------ the password itself

def test_password_is_never_stored(tmp_path):
    sec = Security(tmp_path)
    sec.set_password(PASSWORD)
    saved = (tmp_path / "password.json").read_text()
    assert PASSWORD not in saved and "battery" not in saved
    assert sec.check_password(PASSWORD) and not sec.check_password("wrong password")


def test_short_passwords_refused(tmp_path):
    with pytest.raises(ValueError):
        Security(tmp_path).set_password("short")


def test_secret_files_are_private(tmp_path):
    sec = Security(tmp_path)
    sec.set_password(PASSWORD); sec.api_key(); sec.session_secret()
    for name in ("password.json", "api.key", "session.secret"):
        assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600


# ------------------------------------------------------- locked by default

def test_no_password_means_nothing_works(setup):
    security, web = setup
    assert web.get("/login/status").get_json() == {"has_password": False, "logged_in": False}
    assert web.post("/chat", json={"text": "turn on the lights"}).status_code == 401
    assert log_in(web, "").status_code == 401


@pytest.mark.parametrize("method, path", [
    ("post", "/chat"), ("post", "/voice"), ("post", "/speak"), ("get", "/memories"),
    ("delete", "/memories/abc"), ("post", "/reset"), ("get", "/notifications"),
    ("put", "/expressions"), ("post", "/expressions/undo"), ("post", "/expressions/reset"),
    ("get", "/static/index.html"), ("get", "/studio"), ("get", "/personality"), ("put", "/personality"),
    ("post", "/personality/try"), ("post", "/personality/undo"), ("post", "/personality/reset"),
])
def test_everything_private_is_locked(setup, method, path):
    security, web = setup
    security.set_password(PASSWORD)
    assert getattr(web, method)(path).status_code == 401


def test_pages_send_people_to_the_login_page(setup):
    security, web = setup
    for page in ("/", "/studio", "/eyes"):
        r = web.get(page, headers={"Accept": "text/html"})
        assert r.status_code == 302 and r.headers["Location"].startswith("/login?next=")


def test_public_things_stay_public(setup):
    _, web = setup
    for path in ("/health", "/login", "/login/status", "/static/face.js", "/static/expressions.json", "/static/auth.js"):
        assert web.get(path).status_code == 200, path


# ------------------------------------------------------------ logging in

def test_log_in_and_out(setup):
    security, web = setup
    security.set_password(PASSWORD)
    assert log_in(web, "wrong password").status_code == 401
    assert web.get("/memories").status_code == 401
    assert log_in(web).status_code == 200
    assert web.get("/memories").status_code == 200
    assert web.get("/", headers={"Accept": "text/html"}).status_code == 200
    web.post("/logout")
    assert web.get("/memories").status_code == 401


def test_cookie_is_locked_down(setup):
    security, web = setup
    security.set_password(PASSWORD)
    cookie = log_in(web).headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and PASSWORD not in cookie


def test_changing_the_password_logs_everyone_out(setup):
    security, web = setup
    security.set_password(PASSWORD)
    log_in(web)
    security.set_password("a brand new password")
    assert web.get("/memories").status_code == 401


def test_guessing_is_slowed_down(setup):
    security, web = setup
    security.set_password(PASSWORD)
    for _ in range(MAX_TRIES):
        assert log_in(web, "guess").status_code == 401
    r = log_in(web)  # even the right password has to wait now
    assert r.status_code == 429 and "Try again" in r.get_json()["error"]


def test_a_cookie_from_somewhere_else_is_useless(tmp_path):
    a, b = Security(tmp_path / "a"), Security(tmp_path / "b")
    a.set_password(PASSWORD); b.set_password(PASSWORD)
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=object())
    web_a = create_app(brain, Notifications(), security=a).test_client()
    web_b = create_app(brain, Notifications(), security=b).test_client()
    cookie = log_in(web_a).headers["Set-Cookie"].split(";")[0]
    assert web_b.get("/memories", headers={"Cookie": cookie}).status_code == 401


# --------------------------------------------------------------- the Pi's key

def test_api_key(setup):
    security, web = setup
    security.set_password(PASSWORD)
    good = {"Authorization": "Bearer " + security.api_key()}
    assert web.get("/notifications", headers=good).status_code == 200
    assert web.get("/notifications", headers={"Authorization": "Bearer nope"}).status_code == 401
    old = good
    security.new_api_key()
    assert web.get("/notifications", headers=old).status_code == 401


# ---------------------------------------------------------- other websites

def test_other_websites_cant_make_changes(setup):
    security, web = setup
    security.set_password(PASSWORD)
    log_in(web)
    assert web.post("/reset", headers={"Origin": "http://evil.example"}).status_code == 403
    assert web.post("/reset", headers={"Origin": "http://localhost"}).status_code == 200
