"""Localhost web launcher for Aldervale.

A small stdlib HTTP server serves a branded start page, opens the native ASCII
game in a new terminal window and hosts the pixel-graphics browser build at
/play. It also serves the inspection Studio from `.inspect/` so the launcher,
Studio and both game builds share one local web surface. No external dependency
is used.
"""

import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PROJECT = Path(__file__).resolve().parent.parent
STUDIO_DIR = PROJECT / ".inspect"
TOKEN = secrets.token_urlsafe(24)
LAUNCHER_VERSION = "1.2"


def game_command(mode):
    """The fixed command line for a launch mode; never user supplied."""
    cmd = [sys.executable, "-m", "aldervale"]
    if mode == "demo":
        cmd.extend(["--demo", "9"])
    return cmd


def spawn_game(mode):
    """Open the real game in a new console window (Windows)."""
    if mode not in ("play", "demo"):
        return False, "unknown launch mode"
    if os.name != "nt":
        return False, ("Automatic launch is supported on Windows; run "
                       "'python -m aldervale%s' manually." %
                       (" --demo 9" if mode == "demo" else ""))
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    try:
        # hygiene: allow detached game process; waiting would block the launcher
        subprocess.Popen(game_command(mode), cwd=str(PROJECT),
                         creationflags=flags, close_fds=True)
    except OSError as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    return True, "Game launched in a new console window."


def render_page(token):
    return PAGE.replace("__TOKEN__", token)


def ensure_web_session(server):
    """Start building the browser-play session once, in the background."""
    with server.web_lock:
        if (server.web_session is not None or server.web_building or
                server.web_error):
            return
        server.web_building = True

    def build():
        session = None
        error = None
        try:
            from .webgame import WebGame
            session = WebGame(seed=7, width=132, height=60)
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
        with server.web_lock:
            server.web_session = session
            server.web_building = False
            server.web_error = error

    threading.Thread(target=build, daemon=True).start()


def ensure_web_session3d(server, weather=None, day_t=None):
    """Start building the WebGL session once, in the background."""
    with server.web_lock3d:
        if (server.web_session3d is not None or server.web_building3d or
                server.web_error3d):
            return
        server.web_building3d = True

    def build():
        session = None
        error = None
        try:
            from .webgame import WebGame
            session = WebGame(seed=7, width=132, height=60,
                              render_mode="webgl")
            if weather:
                session.game.world.set_weather(weather)
            if day_t is not None:
                world = session.game.world
                world.time = ((float(day_t) - 0.20) % 1.0) * world.day_length
                world.day_t = float(day_t)
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
        with server.web_lock3d:
            server.web_session3d = session
            server.web_building3d = False
            server.web_error3d = error

    threading.Thread(target=build, daemon=True).start()


def play3d_url(port):
    return launcher_url(port) + "play3d"


def launcher_url(port, autostart=False):
    """The local URL, optionally asking the page to start the game on load."""
    url = "http://127.0.0.1:%d/" % int(port)
    return url + "?autostart=1" if autostart else url


def play_url(port):
    return launcher_url(port) + "play"


def check_health(port):
    """True when an Aldervale launcher already owns the port."""
    if not port:
        return False
    try:
        with urllib.request.urlopen(launcher_url(port) + "health",
                                    timeout=0.5) as response:
            return response.status == 200 and response.read(2) == b"ok"
    except (OSError, urllib.error.URLError):
        return False


def _studio_file(name):
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    candidate = STUDIO_DIR / name
    return candidate if candidate.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "AldervaleLauncher/" + LAUNCHER_VERSION

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, render_page(TOKEN))
            return
        if path == "/health":
            self._send(200, "ok", "text/plain; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path == "/play":
            from .webgame import PLAY_HTML
            ensure_web_session(self.server)
            self._send(200, PLAY_HTML.replace("__TOKEN__", TOKEN))
            return
        if path == "/play3d":
            from .webglclient import PLAY3D_HTML
            query = parse_qs(urlparse(self.path).query)
            weather = (query.get("weather") or [None])[0]
            day = (query.get("day") or [None])[0]
            try:
                day_t = float(day) if day is not None else None
            except ValueError:
                day_t = None
            ensure_web_session3d(self.server, weather, day_t)
            self._send(200, PLAY3D_HTML.replace("__TOKEN__", TOKEN))
            return
        if path in ("/api/scene3d", "/api/state3d"):
            server = self.server
            session = server.web_session3d
            if session is not None:
                payload = (session.scene() if path == "/api/scene3d"
                           else session.state())
            elif server.web_error3d:
                payload = {"status": "error", "message": server.web_error3d}
            else:
                payload = {"status": "loading"}
            self._send(200, json.dumps(payload), "application/json")
            return
        if path in ("/api/world3d", "/api/models3d"):
            server = self.server
            session = server.web_session3d
            if session is not None:
                payload = (session.world_bundle() if path == "/api/world3d"
                           else session.model_bundle())
                payload = dict(payload)
                payload["status"] = "ready"
            elif server.web_error3d:
                payload = {"status": "error", "message": server.web_error3d}
            else:
                payload = {"status": "loading"}
            self._send(200, json.dumps(payload), "application/json")
            return
        if path in ("/api/frame", "/api/state"):
            server = self.server
            session = server.web_session
            if session is not None:
                payload = (session.snapshot() if path == "/api/frame"
                           else session.state())
            elif server.web_error:
                payload = {"status": "error", "message": server.web_error}
            else:
                payload = {"status": "loading"}
            self._send(200, json.dumps(payload), "application/json")
            return
        if path == "/studio" or path == "/studio/":
            path = "/studio/index.html"
        if path.startswith("/studio/"):
            name = unquote(path[len("/studio/"):])
            target = _studio_file(name)
            if target is None:
                self._send(404, "Studio file not found. Run "
                                "`python -m aldervale --inspect .inspect`.")
                return
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)
            return
        self._send(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/start", "/api/input", "/api/input3d"):
            self._send(404, "Not found")
            return
        if self.headers.get("X-Aldervale-Token") != TOKEN:
            self._send(403, json.dumps({"ok": False,
                                        "message": "bad token"}),
                       "application/json")
            return
        try:
            length = min(8192, int(self.headers.get("Content-Length", "0")))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, json.dumps({"ok": False,
                                        "message": "bad request"}),
                       "application/json")
            return
        if path in ("/api/input", "/api/input3d"):
            session = (self.server.web_session if path == "/api/input"
                       else self.server.web_session3d)
            if session is None:
                self._send(409, json.dumps({"ok": False,
                                            "message": "game is loading"}),
                           "application/json")
                return
            session.set_input(payload.get("pressed"), payload.get("held"),
                              payload.get("mouse"))
            self._send(200, json.dumps({"ok": True}), "application/json")
            return
        mode = payload.get("mode", "play")
        if mode not in ("play", "demo"):
            self._send(400, json.dumps({"ok": False,
                                        "message": "unknown mode"}),
                       "application/json")
            return
        server = self.server
        with server.launch_lock:
            now = time.monotonic()
            if (server.last_mode == mode and
                    now - server.last_spawn < 2.0):
                self._send(200, json.dumps(
                    {"ok": True, "message": "Game is already launching."}),
                    "application/json")
                return
            server.last_spawn = now
            server.last_mode = mode
        spawn = getattr(server, "spawn", spawn_game)
        ok, message = spawn(mode)
        self._send(200 if ok else 500,
                   json.dumps({"ok": ok, "message": message}),
                   "application/json")

    def log_message(self, *args):
        return


def serve(port=8765, open_browser=False, autostart=False, open_play=False):
    """Blocking launcher server; returns the exit code."""
    target = play_url(port) if open_play else launcher_url(port, autostart)
    if check_health(port):
        print("launcher: already running at %s" % launcher_url(port))
        if open_browser:
            webbrowser.open_new_tab(target)
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.spawn = spawn_game
    server.last_spawn = 0.0
    server.last_mode = None
    server.launch_lock = threading.Lock()
    server.web_session = None
    server.web_building = False
    server.web_error = None
    server.web_lock = threading.Lock()
    server.web_session3d = None
    server.web_building3d = False
    server.web_error3d = None
    server.web_lock3d = threading.Lock()
    actual = server.server_address[1]
    target = play3d_url(actual) if open_play else launcher_url(actual, autostart)
    print("launcher: %s  (Ctrl+C to stop)" % launcher_url(actual))
    print("launcher: 3D browser game at %s" % play3d_url(actual))
    print("launcher: pixel browser game at %s" % play_url(actual))
    if open_browser:
        webbrowser.open_new_tab(target)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("launcher: stopped")
    finally:
        server.shutdown()
        session = getattr(server, "web_session", None)
        if session is not None:
            session.close()
        session = getattr(server, "web_session3d", None)
        if session is not None:
            session.close()
        server.server_close()
    return 0


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aldervale Launcher</title>
<style>
:root{--bg:#0b0e14;--panel:#121722;--line:#283144;--ink:#dce5f2;
      --dim:#8b97aa;--gold:#e8c45a;--green:#7fd18a;--red:#e07a7a}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:radial-gradient(circle at 50% 0,
  #182238 0, #0b0e14 58%);color:var(--ink)}
body{font-family:"Cascadia Mono",Consolas,"Courier New",monospace;
     display:flex;align-items:center;justify-content:center;padding:32px}
main{width:min(760px,100%);background:rgba(14,19,29,.92);
     border:1px solid var(--line);border-radius:10px;padding:34px 38px;
     box-shadow:0 24px 80px rgba(0,0,0,.55)}
h1{margin:0;font-size:clamp(28px,6vw,54px);letter-spacing:.24em;
   color:var(--gold);text-align:center}
.sub{text-align:center;color:var(--dim);font-size:13px;margin:8px 0 30px}
.buttons{display:flex;flex-wrap:wrap;gap:12px;justify-content:center}
button,.buttons a{border:1px solid var(--line);border-radius:6px;
       padding:14px 26px;background:#0e1420;color:var(--ink);font:inherit;
       font-size:15px;cursor:pointer;letter-spacing:.08em;display:inline-block;
       text-decoration:none}
button.primary,.buttons a.primary{border-color:var(--gold);color:var(--gold);
               background:#161b26}
.buttons a.web{border-color:var(--green);color:var(--green);
               background:#161b26}
button:hover,.buttons a:hover{filter:brightness(1.2)}
button:disabled{opacity:.55;cursor:wait}
#status{min-height:22px;text-align:center;margin:20px 0 6px;font-size:13px;
        color:var(--dim)}
#status.ok{color:var(--green)}#status.bad{color:var(--red)}
.links{display:flex;gap:18px;justify-content:center;margin-top:16px;
       font-size:13px}
a{color:var(--gold);text-decoration:none}
a:hover{text-decoration:underline}
.help{margin-top:28px;border-top:1px solid var(--line);padding-top:18px;
      color:var(--dim);font-size:12px;line-height:1.7}
kbd{color:var(--ink);border:1px solid var(--line);border-radius:3px;
    padding:1px 5px;font:inherit;font-size:11px}
.note{text-align:center;color:#596477;font-size:11px;margin-top:18px}
</style>
</head>
<body>
<main>
  <h1>ALDERVALE</h1>
  <p class="sub">a tale of steel and starlight . GPU 3D in the browser, ASCII in the terminal</p>
  <div class="buttons">
    <a class="web primary" href="/play3d" target="_blank" rel="noopener">PLAY GRAPHICS 3D</a>
    <a class="web" href="/play" target="_blank" rel="noopener">PLAY PIXEL</a>
    <button data-mode="play">START GAME (TERMINAL)</button>
    <button data-mode="demo">WATCH DEMO</button>
  </div>
  <p id="status">Ready. PLAY GRAPHICS 3D opens the GPU build; PLAY PIXEL is the fallback.</p>
  <div class="links">
    <a href="/studio/" target="_blank" rel="noopener">Open Studio</a>
    <a href="/health" target="_blank" rel="noopener">Health</a>
  </div>
  <div class="help">
    Controls in the game window: <kbd>WASD</kbd> walk,
    <kbd>SPACE</kbd> attack, <kbd>E</kbd> talk, <kbd>I</kbd> bag,
    <kbd>M</kbd> map, <kbd>H</kbd> help, <kbd>ESC</kbd> pause.
    The Studio opens the exact browser-rendered frames and the model
    turnaround viewer.
  </div>
  <p class="note">Launcher v__VERSION__ . localhost only . token-protected</p>
</main>
<script>
const TOKEN = "__TOKEN__";
const status = document.getElementById("status");

async function launch(mode) {
  const buttons = [...document.querySelectorAll("button[data-mode]")];
  buttons.forEach(b => b.disabled = true);
  status.className = "";
  status.textContent = mode === "demo"
    ? "Opening the demo..." : "Opening the game...";
  try {
    const r = await fetch("/start", {
      method: "POST",
      headers: {"Content-Type": "application/json",
                "X-Aldervale-Token": TOKEN},
      body: JSON.stringify({mode})
    });
    const data = await r.json();
    status.className = data.ok ? "ok" : "bad";
    status.textContent = data.message;
  } catch (err) {
    status.className = "bad";
    status.textContent = "Launcher error: " + err;
  } finally {
    buttons.forEach(b => b.disabled = false);
  }
}

document.querySelectorAll("button[data-mode]").forEach(btn => {
  btn.addEventListener("click", () => launch(btn.dataset.mode));
});

const params = new URLSearchParams(location.search);
if (params.get("autostart") === "1") {
  history.replaceState(null, "", location.pathname);
  if (!sessionStorage.getItem("aldervale_autostart")) {
    sessionStorage.setItem("aldervale_autostart", "1");
    setTimeout(() => launch("play"), 350);
  }
}
</script>
</body>
</html>
""".replace("__VERSION__", LAUNCHER_VERSION)
