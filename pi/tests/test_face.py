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
            p[side]["browRaise"] = 1
            p[side]["browTilt"] = 30
        for brow in geometry(WIDTH, HEIGHT, p, config["face"], {"left": 0, "right": 0})["brows"].values():
            assert brow["y0"] > 0 and brow["y1"] > 0


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
