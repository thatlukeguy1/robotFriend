"""Body settings as the brain sends them (the Pi can't import the brain's code)."""


def settings(**changes):
    return {"volume": 100, "sleep_after_minutes": 10, "screen_off_minutes": 0, "wake_threshold": 0.5,
            "wake_frames": 1, "listen_seconds": 4, "follow_up_seconds": 5, "christmas_hat": "off",
            "replies": [], **changes}
