"""Tests for the Pi's eye drawing. It must read the shared settings and draw every expression."""

from bolt_body.eyes import SIZE, draw_eye, load_config, params_for, preview


def colour_count(img, hex_colour):
    rgb = tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    data = img.convert("RGB").tobytes()
    pixels = zip(data[0::3], data[1::3], data[2::3])
    return sum(1 for px in pixels if sum(abs(a - b) for a, b in zip(px, rgb)) < 30)


def test_every_expression_draws():
    config = load_config()
    for name in config["expressions"]:
        for side in ("left", "right"):
            img = draw_eye(params_for(config, name, side), config, side)
            assert img.size == (SIZE, SIZE)


def test_open_eye_shows_the_iris_and_a_closed_one_doesnt():
    config = load_config()
    iris = config["colors"]["iris"]
    awake = colour_count(draw_eye(params_for(config, "listening", "left"), config, "left"), iris)
    asleep = colour_count(draw_eye(params_for(config, "sleeping", "left"), config, "left"), iris)
    assert awake > 5000 and asleep < awake * 0.05


def test_blinking_closes_the_eye():
    config = load_config()
    iris = config["colors"]["iris"]
    p = params_for(config, "idle", "left")
    assert colour_count(draw_eye(p, config, "left", blink=1.0), iris) < 300


def test_one_eye_can_differ():
    config = load_config()
    assert params_for(config, "confused", "left")["open"] != params_for(config, "confused", "right")["open"]


def test_preview_sheet(tmp_path):
    names = preview(tmp_path / "eyes.png")
    assert (tmp_path / "eyes.png").exists() and "happy" in names


def test_design_comes_from_the_brain_when_it_can(tmp_path):
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
    # Brain down? Use the original file.
    assert load_config(brain_url="http://127.0.0.1:1")["colors"]["iris"] != "#ff00aa"
