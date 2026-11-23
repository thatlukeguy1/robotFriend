"""Tests for the Pi's face drawing. It must read the shared settings and draw every expression."""

from bolt_body.face import HEIGHT, WIDTH, draw_face, geometry, load_config, params_for, preview


def both(config, name):
    return {side: params_for(config, name, side) for side in ("left", "right")}


def colour_count(img, hex_colour):
    rgb = tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    data = img.convert("RGB").tobytes()
    return sum(1 for px in zip(data[0::3], data[1::3], data[2::3]) if sum(abs(a - b) for a, b in zip(px, rgb)) < 30)


def test_every_expression_draws_at_screen_size():
    config = load_config()
    for name in config["expressions"]:
        assert draw_face(both(config, name), config).size == (WIDTH, HEIGHT)


def test_open_eyes_show_and_closed_ones_dont():
    config = load_config()
    iris = config["colors"]["iris"]
    awake = colour_count(draw_face(both(config, "listening"), config), iris)
    asleep = colour_count(draw_face(both(config, "sleeping"), config), iris)
    assert awake > 3000 and asleep < awake * 0.1


def test_blinking_closes_both_eyes():
    config = load_config()
    shut = draw_face(both(config, "idle"), config, blink={"left": 1.0, "right": 1.0})
    assert colour_count(shut, config["colors"]["iris"]) < 300


def test_mouth_opens_when_talking():
    config = load_config()
    mouth = config["colors"]["mouth"]
    bottom = (0, int(HEIGHT * 0.7), WIDTH, HEIGHT)  # just the mouth area (the brows are the same colour)
    quiet = colour_count(draw_face(both(config, "speaking"), config, level=0).crop(bottom), mouth)
    loud = colour_count(draw_face(both(config, "speaking"), config, level=1).crop(bottom), mouth)
    assert loud > quiet * 1.5


def test_brows_never_leave_the_screen():
    config = load_config()
    for name in config["expressions"]:
        p = both(config, name)
        for side in ("left", "right"):
            p[side].update(browShow=1, browRaise=1, browArch=1, browTilt=30)
        for brow in geometry(WIDTH, HEIGHT, p, config["face"], {"left": 0, "right": 0})["brows"].values():
            assert all(y - w / 2 > 0 for _, y, w in brow["pts"])


def test_one_eye_can_differ():
    config = load_config()
    assert params_for(config, "confused", "left")["open"] != params_for(config, "confused", "right")["open"]


def test_preview_sheet(tmp_path):
    names = preview(tmp_path / "face.png")
    assert (tmp_path / "face.png").exists() and "happy" in names


def test_design_comes_from_the_brain_when_it_can():
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    design = load_config()
    design["colors"]["iris"] = "#ff00aa"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(design).encode()
            self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    assert load_config(brain_url=f"http://127.0.0.1:{server.server_port}")["colors"]["iris"] == "#ff00aa"
    server.shutdown()
    assert load_config(brain_url="http://127.0.0.1:1")["colors"]["iris"] != "#ff00aa"


def test_brows_only_show_in_moods_that_use_them():
    config = load_config()
    brow = config["colors"]["brow"]
    top = (0, 0, WIDTH, int(HEIGHT * 0.2))  # the strip above the eyes
    assert colour_count(draw_face(both(config, "idle"), config).crop(top), brow) < 20
    assert colour_count(draw_face(both(config, "thinking"), config).crop(top), brow) > 150


def test_half_shown_brows_are_fainter():
    config = load_config()
    full, half = both(config, "thinking"), both(config, "thinking")
    for side in ("left", "right"):
        half[side]["browShow"] = 0.5
    brow = config["colors"]["brow"]
    top = (0, 0, WIDTH, int(HEIGHT * 0.2))
    assert colour_count(draw_face(half, config).crop(top), brow) < colour_count(draw_face(full, config).crop(top), brow) * 0.3


def test_sleeping_face_has_floating_zs_and_idle_does_not():
    from bolt_body.face import geometry, load_config, params_for
    config = load_config()
    def shapes(name, time):
        p = {s: params_for(config, name, s) for s in ("left", "right")}
        return geometry(320, 240, p, config["face"], {"left": 0, "right": 0}, time=time)["zzz"]
    assert shapes("idle", 1.0) == []
    early, later = shapes("sleeping", 1.0), shapes("sleeping", 1.5)
    assert len(early) == 3 and early[0]["y"] != later[0]["y"]      # they float
    assert all(0 <= z["x"] - z["size"] / 2 and z["x"] + z["size"] / 2 <= 320 and z["y"] - z["size"] / 2 >= 0 for z in early)


def test_thinking_face_has_a_hand_sticker_that_rises_into_view():
    from bolt_body.face import STICKER_SET, geometry, load_config, params_for
    config = load_config()
    def stickers(name, amount=None, hat=0.0):
        p = {s: dict(params_for(config, name, s)) for s in ("left", "right")}
        if amount is not None:
            for s in p:
                p[s]["hand"] = amount
        return {st["name"]: st for st in geometry(320, 240, p, config["face"], {"left": 0, "right": 0},
                                                  hat=hat, stickers=STICKER_SET)["stickers"]}
    assert stickers("idle") == {}
    full, half = stickers("thinking")["hand"], stickers("thinking", 0.5)["hand"]
    assert half["y"] > full["y"] and half["alpha"] == 0.5 and full["tint"] == "mouth"   # rises and fades in
    hat, half_hat = stickers("idle", hat=1.0)["hat"], stickers("idle", hat=0.5)["hat"]
    assert half_hat["y"] < hat["y"]                                                     # the hat slides DOWN onto her


def test_stickers_are_drawn_and_coloured_in():
    from bolt_body.face import draw_face, load_config, params_for
    config = load_config()
    p = {s: params_for(config, "thinking", s) for s in ("left", "right")}
    plain = draw_face(p, config, stickers={})
    with_hand = draw_face(p, config)
    changed = [(x, y) for x in range(0, 320, 2) for y in range(150, 240, 2)
               if plain.getpixel((x, y)) != with_hand.getpixel((x, y))]
    assert len(changed) > 200                                       # a hand-sized patch appeared under the chin
    r, g, b = max((with_hand.getpixel(xy) for xy in changed), key=sum)
    assert b > r                                                    # in her own blue, not grey


def test_missing_stickers_just_mean_no_stickers(tmp_path):
    from bolt_body.face import load_stickers
    assert load_stickers(tmp_path) == {}


def test_the_face_lifts_to_make_room_for_the_hand():
    from bolt_body.face import geometry, load_config, params_for
    config = load_config()
    p = {s: dict(params_for(config, "thinking", s)) for s in ("left", "right")}
    with_hand = geometry(320, 240, p, config["face"], {"left": 0, "right": 0})
    for s in p:
        p[s]["hand"] = 0
    without = geometry(320, 240, p, config["face"], {"left": 0, "right": 0})
    assert with_hand["mouth"]["upper"][0][1] < without["mouth"]["upper"][0][1]
