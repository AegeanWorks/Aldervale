"""Browser play client: a localhost thin client over the real Python engine.

The browser sends key/mouse state and draws a canvas from truecolor pixel frames
plus the text HUD produced by the existing Game. The terminal build is
unchanged; this module is only the web transport and the canvas renderer. No
external dependency is used.
"""

import base64
import json
import threading
import time
from pathlib import Path

from .inspect import build_game

DT = 1.0 / 20.0
VALID_TOKENS = frozenset((
    "w", "a", "s", "d", "up", "down", "left", "right", "space", "shift",
    "b", "e", "i", "m", "h", "esc", "enter", "tab", "f1", "+", "=", "-",
    "q", "c", "n", "x", "1", "2", "3", "4", "5", "6", "7", "8", "9",
))
MOUSE_KINDS = frozenset(("ldown", "rdown", "up", "move", "wheel"))
MAX_QUEUED_MOUSE = 64


def encode_frame(screen, pixels=None):
    """Rows of glyphs plus packed RGB colours for the canvas client.

    When ``pixels`` is a graphics FrameBuffer its column-major truecolor bytes
    are base64-encoded; the client transposes them into an ImageData.
    """
    data = {"chars": ["".join(row) for row in screen.chars],
            "colors": [[int(c) for c in row] for row in screen.fg]}
    if pixels is not None:
        data["gfx"] = {
            "w": pixels.w,
            "h": pixels.h,
            "rgb": base64.b64encode(bytes(pixels.data)).decode("ascii"),
        }
    return data


class WebTerm:
    """Terminal double used by Game; queues input and ignores output."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pressed = []
        self.held = set()
        self.mouse = []

    def size(self):
        return self.width, self.height

    def poll(self):
        pressed = self.pressed
        self.pressed = []
        return pressed, set(self.held)

    def take_mouse(self):
        events = self.mouse
        self.mouse = []
        return events

    def write(self, text):
        return None

    def flush(self):
        return None


def _clean_mouse(events):
    cleaned = []
    for ev in events[:8]:
        if not isinstance(ev, list) or len(ev) != 5:
            continue
        kind, col, row, buttons, wheel = ev
        if kind not in MOUSE_KINDS:
            continue
        try:
            col = max(-2, min(4000, int(col)))
            row = max(-2, min(4000, int(row)))
            buttons = int(buttons)
            wheel = int(wheel)
        except (TypeError, ValueError):
            continue
        cleaned.append((kind, col, row, buttons, wheel))
    return cleaned


class WebGame:
    """One live session: Game + WebTerm + a 20 fps simulation thread."""

    def __init__(self, seed=7, width=132, height=60, gfx=True,
                 gfx_size=(288, 162), render_mode=None):
        self.width = width
        self.height = height
        if render_mode is None:
            render_mode = "pixel" if gfx else "ascii"
        self.render_mode = render_mode
        self.gfx = render_mode == "pixel"
        self.game = build_game(seed=seed, width=width, height=height,
                               gfx=self.gfx, gfx_size=gfx_size,
                               render_mode=render_mode)
        self.game.save_path = str(
            Path(__file__).resolve().parent.parent / "saves" /
            ("aldervale_web3d.json" if render_mode == "webgl"
             else "aldervale_web.json"))
        self.term = WebTerm(width, height)
        self.game.term = self.term
        self.game.state = "play"
        self.game.fps = int(round(1.0 / DT))
        self.game.dt = DT
        self.lock = threading.RLock()
        self.running = True
        self.seq = 0
        self.frame = None
        if self.gfx:
            self.frame = encode_frame(self.game.screen, self.game.frame)
        self._world_bundle = None
        self._model_bundle = None
        self.last_poll = time.monotonic()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def set_input(self, pressed=None, held=None, mouse=None):
        with self.lock:
            for token in (pressed or [])[:8]:
                if token in VALID_TOKENS:
                    self.term.pressed.append(token)
            if held is not None:
                self.term.held = {t for t in held[:16] if t in VALID_TOKENS}
            self.term.mouse.extend(_clean_mouse(mouse or []))
            # A modal menu stops draining mouse events; keep the queue bounded
            # so a long session in a menu cannot grow it without limit.
            if len(self.term.mouse) > MAX_QUEUED_MOUSE:
                del self.term.mouse[:-MAX_QUEUED_MOUSE]

    def _player(self):
        p = self.game.world.player
        return {"x": round(p.x, 2), "z": round(p.z, 2),
                "hp": round(p.hp, 1), "max_hp": p.max_hp,
                "stamina": round(p.stamina, 1), "state": p.state}

    def snapshot(self):
        """Latest frame plus a small state header; marks the client alive."""
        with self.lock:
            self.last_poll = time.monotonic()
            payload = {"status": "ready", "seq": self.seq,
                       "w": self.width, "h": self.height,
                       "gfx": bool(self.frame and self.frame.get("gfx")),
                       "state": self.game.state,
                       "weather": self.game.world.weather,
                       "day_t": round(self.game.world.day_t, 3),
                       "player": self._player()}
            if self.frame is not None:
                payload["frame"] = self.frame
            else:
                payload["render_mode"] = self.render_mode
            return payload

    def scene(self):
        """Per-tick WebGL scene: camera, entities and HUD text."""
        from .webglscene import scene as encode_scene
        with self.lock:
            self.last_poll = time.monotonic()
            if self.game._last_env is None:
                from .render import Env
                self.game._last_env = Env(self.game.world.day_t,
                                          self.game.world.time)
            return encode_scene(self.game, self.game.world, self.seq)

    def world_bundle(self):
        from .webglscene import world_bundle
        with self.lock:
            if self._world_bundle is None:
                self._world_bundle = world_bundle(self.game.world)
            return self._world_bundle

    def model_bundle(self):
        from .webglscene import model_bundle
        with self.lock:
            if self._model_bundle is None:
                self._model_bundle = model_bundle(self.game.atlas)
            return self._model_bundle

    def state(self):
        """Diagnostics for tests and the agent; does not count as a client poll."""
        with self.lock:
            return {"status": "ready", "seq": self.seq,
                    "state": self.game.state,
                    "gfx": bool(self.frame and self.frame.get("gfx")),
                    "render_mode": self.render_mode,
                    "weather": self.game.world.weather,
                    "day_t": round(self.game.world.day_t, 3),
                    "player": self._player()}

    def step(self):
        """One client frame: input, the shared simulation step, then render.

        `Game.tick` is the same step the terminal loop runs, so a browser
        session pauses in menus, dies and wins exactly like the terminal build.
        """
        with self.lock:
            self.game._handle_keys()
            env = self.game.tick(DT)
            self.game._render(env)
            if getattr(self, "gfx", True):
                self.frame = encode_frame(self.game.screen,
                                          getattr(self.game, "frame", None))
            self.seq += 1

    def _loop(self):
        while self.running:
            if time.monotonic() - self.last_poll > 20.0:
                time.sleep(0.25)
                continue
            started = time.monotonic()
            self.step()
            rest = DT - (time.monotonic() - started)
            if rest > 0:
                time.sleep(rest)

    def close(self):
        self.running = False


PLAY_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aldervale - Browser</title>
<style>
:root{--bg:#070a10;--panel:#0f1520;--line:#263043;--ink:#dce5f2;
      --dim:#8491a6;--gold:#e8c45a;--green:#7fd18a;--red:#e07a7a}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--ink)}
body{font-family:"Cascadia Mono",Consolas,"Courier New",monospace;
     display:flex;flex-direction:column;align-items:center;padding:14px}
header{width:min(1400px,100%);display:flex;align-items:baseline;gap:18px;
       flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:8px}
h1{font-size:16px;letter-spacing:.22em;color:var(--gold);margin:0}
#status{color:var(--dim);font-size:12px}
#hud{margin-left:auto;color:var(--dim);font-size:12px}
#stage{position:relative;margin-top:14px;display:flex;align-items:center;
       justify-content:center;min-height:240px}
canvas{background:#05070a;border:1px solid var(--line);outline:none;
       image-rendering:pixelated;display:block}
#loading{position:absolute;inset:0;display:flex;align-items:center;
         justify-content:center;background:rgba(5,7,10,.82);
         color:var(--gold);font-size:14px;letter-spacing:.14em;text-align:center;
         padding:24px}
#loading.hide{display:none}
footer{width:min(1400px,100%);margin-top:12px;color:var(--dim);font-size:12px;
       line-height:1.8;display:flex;flex-wrap:wrap;gap:18px}
a{color:var(--gold);text-decoration:none}a:hover{text-decoration:underline}
kbd{border:1px solid var(--line);border-radius:3px;padding:1px 5px;
    color:var(--ink);font:inherit;font-size:11px}
.note{color:#596477}
</style>
</head>
<body>
<header>
  <h1>ALDERVALE</h1>
  <span id="status">Connecting to the forge...</span>
  <span id="hud"></span>
</header>
<div id="stage">
  <canvas id="game" tabindex="0" aria-label="Aldervale game view"></canvas>
  <div id="loading">FORGING THE REALM...</div>
</div>
<footer>
  <span><kbd>WASD</kbd> move <kbd>arrows</kbd> move/turn
        <kbd>SPACE</kbd> attack <kbd>SHIFT</kbd> sprint <kbd>B</kbd> guard</span>
  <span><kbd>E</kbd> talk/take <kbd>I</kbd> bag <kbd>M</kbd> map
        <kbd>H</kbd> help <kbd>ESC</kbd> pause</span>
  <span>click to walk/attack . right-drag to look . wheel to zoom</span>
  <span><a href="/studio/" target="_blank" rel="noopener">Studio</a></span>
  <span><a href="/">Launcher</a></span>
  <span class="note">pixel graphics on the same Python engine . the terminal build is ASCII</span>
</footer>
<script>
const TOKEN = "__TOKEN__";
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");
const hudEl = document.getElementById("hud");
const loadingEl = document.getElementById("loading");
let frame = null, lastSeq = -1, busy = false, ready = false;
let cellW = 10, cellH = 16, dpr = 1, fitted = false;
let held = new Set();
let pressed = [];
let mouse = [];
let dragging = false;
let framesThisSecond = 0, fps = 0, fpsAt = performance.now();
const off = document.createElement("canvas");
const offctx = off.getContext("2d");
const MODAL = new Set(["title", "inventory", "help", "pause", "shop",
                       "dialogue", "dead"]);

function hex(c){ return "#" + c.toString(16).padStart(6, "0"); }

function showLoading(text){
  loadingEl.classList.remove("hide");
  loadingEl.textContent = text;
}

function decodeGfx(gfx){
  const bin = atob(gfx.rgb);
  const raw = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) raw[i] = bin.charCodeAt(i);
  return {w: gfx.w, h: gfx.h, raw: raw};
}

function drawGfx(cssW, cssH){
  const g = frame.gfx;
  const gw = g.w, gh = g.h, raw = g.raw;
  if (off.width !== gw || off.height !== gh){
    off.width = gw;
    off.height = gh;
  }
  const img = offctx.createImageData(gw, gh);
  const d = img.data;
  for (let x = 0; x < gw; x++){
    let so = x * gh * 3;
    for (let y = 0; y < gh; y++, so += 3){
      const q = (y * gw + x) * 4;
      d[q] = raw[so];
      d[q + 1] = raw[so + 1];
      d[q + 2] = raw[so + 2];
      d[q + 3] = 255;
    }
  }
  offctx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(off, 0, 0, gw, gh, 0, 0, cssW, cssH);
}

function drawTextGrid(cssW, cssH, shadow){
  const w = frame.w, h = frame.h;
  const cw = cssW / w, ch = cssH / h;
  ctx.font = Math.max(8, Math.floor(ch * 0.92)) +
    'px "Cascadia Mono",Consolas,monospace';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let y = 0; y < h; y++){
    const chars = frame.chars[y], colors = frame.colors[y];
    let x = 0;
    while (x < w){
      const color = colors[x];
      let end = x + 1;
      while (end < w && colors[end] === color) end++;
      const ink = hex(color);
      for (let i = x; i < end; i++){
        const glyph = chars[i];
        if (glyph === " ") continue;
        const px = i * cw + cw * 0.5;
        const py = y * ch + ch * 0.52;
        if (shadow){
          ctx.fillStyle = "rgba(3,5,9,.88)";
          ctx.fillText(glyph, px + 1, py + 1);
        }
        ctx.fillStyle = ink;
        ctx.fillText(glyph, px, py);
      }
      x = end;
    }
  }
}

function render(){
  if (!frame) return;
  const started = performance.now();
  const cssW = canvas.width / dpr, cssH = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#05070a";
  ctx.fillRect(0, 0, cssW, cssH);
  if (frame.gfx){
    drawGfx(cssW, cssH);
    if (MODAL.has(frame.state)){
      ctx.fillStyle = frame.state === "title"
        ? "rgba(4,6,10,.38)" : "rgba(4,6,10,.62)";
      ctx.fillRect(0, 0, cssW, cssH);
    }
    drawTextGrid(cssW, cssH, true);
  } else {
    drawTextGrid(cssW, cssH, false);
  }
  window.__renderMs = performance.now() - started;
}

function fit(){
  if (!frame) return;
  const maxW = Math.max(320, innerWidth - 36);
  const maxH = Math.max(220, innerHeight - 190);
  dpr = Math.min(2, window.devicePixelRatio || 1);
  let cssW, cssH;
  if (frame.gfx){
    const aspect = frame.gfx.w / frame.gfx.h;
    cssW = maxW;
    cssH = Math.floor(cssW / aspect);
    if (cssH > maxH){
      cssH = maxH;
      cssW = Math.floor(cssH * aspect);
    }
    cssW = Math.max(320, cssW);
    cssH = Math.max(180, Math.floor(cssW / aspect));
  } else {
    let ch = Math.floor(Math.min(maxH / frame.h, maxW / (frame.w * 0.62)));
    ch = Math.max(7, Math.min(20, ch));
    cellH = ch;
    cellW = Math.max(4, Math.floor(ch * 0.62));
    cssW = frame.w * cellW;
    cssH = frame.h * cellH;
  }
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = Math.floor(cssW) + "px";
  canvas.style.height = Math.floor(cssH) + "px";
  window.__fitted = true;
  render();
}

function updateHud(data){
  const p = data.player || {};
  hudEl.textContent = "HP " + Math.round(p.hp) + "/" + p.max_hp +
    "  STA " + Math.round(p.stamina) + "  " +
    (data.weather || "clear") + "  " + fps + " fps";
}

async function poll(){
  if (busy) return;
  busy = true;
  try {
    const r = await fetch("/api/frame", {cache: "no-store"});
    const data = await r.json();
    if (data.status === "ready"){
      if (!ready){
        ready = true;
        showLoading("");
        loadingEl.classList.add("hide");
        statusEl.textContent = "Connected.";
        canvas.focus();
      }
      if (data.seq !== lastSeq){
        lastSeq = data.seq;
        frame = {w: data.w, h: data.h, chars: data.frame.chars,
                 colors: data.frame.colors, state: data.state,
                 seq: data.seq,
                 gfx: data.frame.gfx ? decodeGfx(data.frame.gfx) : null};
        framesThisSecond++;
        const now = performance.now();
        if (now - fpsAt >= 1000){
          fps = Math.round(framesThisSecond * 1000 / (now - fpsAt));
          framesThisSecond = 0;
          fpsAt = now;
        }
        window.__frameSeq = data.seq;
        window.__gfx = !!frame.gfx;
        window.__frameW = frame.w;
        window.__frameH = frame.h;
        if (!window.__gfxLabeled){
          statusEl.textContent = frame.gfx ? "Pixel graphics." : "ASCII cells.";
          window.__gfxLabeled = true;
        }
        if (!fitted){ fitted = true; fit(); } else render();
        updateHud(data);
      }
    } else if (data.status === "error"){
      showLoading("The forge failed: " + data.message);
      statusEl.textContent = "Error.";
    } else {
      showLoading("FORGING THE REALM...");
    }
  } catch (err) {
    showLoading("Connection lost: " + err);
  } finally {
    busy = false;
  }
}

async function sendInput(){
  if (!ready) return;
  const body = {pressed: pressed.splice(0), held: [...held],
                mouse: mouse.splice(0)};
  if (!body.pressed.length && !body.mouse.length && !body.held.length &&
      !heldChanged) return;
  heldChanged = false;
  try {
    await fetch("/api/input", {
      method: "POST",
      headers: {"Content-Type": "application/json",
                "X-Aldervale-Token": TOKEN},
      body: JSON.stringify(body)
    });
  } catch (err) {
    statusEl.textContent = "Input lost: " + err;
  }
}

let heldChanged = false;
const KEYMAP = {"ArrowUp":"up", "ArrowDown":"down", "ArrowLeft":"left",
                "ArrowRight":"right", " ":"space", "Shift":"shift",
                "Escape":"esc", "Enter":"enter", "Tab":"tab", "F1":"f1"};
function tokenFor(e){
  if (KEYMAP[e.key]) return KEYMAP[e.key];
  if (e.key === "+" || e.key === "=") return "+";
  if (e.key === "-" || e.key === "_") return "-";
  if (e.key.length === 1 && /[a-z0-9]/i.test(e.key))
    return e.key.toLowerCase();
  return null;
}
function block(e){
  return ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " ", "Tab"]
    .includes(e.key);
}
window.addEventListener("keydown", e => {
  const t = tokenFor(e);
  if (!t) return;
  if (block(e)) e.preventDefault();
  if (e.repeat || held.has(t)) return;
  held.add(t);
  pressed.push(t);
  heldChanged = true;
  sendInput();
});
window.addEventListener("keyup", e => {
  const t = tokenFor(e);
  if (!t) return;
  if (block(e)) e.preventDefault();
  if (!held.delete(t)) return;
  heldChanged = true;
  sendInput();
});
window.addEventListener("blur", () => {
  held.clear();
  heldChanged = true;
  sendInput();
});

function cellAt(e){
  if (!frame) return [0, 0];
  const r = canvas.getBoundingClientRect();
  return [Math.floor((e.clientX - r.left) / r.width * frame.w),
          Math.floor((e.clientY - r.top) / r.height * frame.h)];
}
function flushMouse(){
  const events = mouse.splice(0);
  if (!events.length) return;
  fetch("/api/input", {
    method: "POST",
    headers: {"Content-Type": "application/json",
              "X-Aldervale-Token": TOKEN},
    body: JSON.stringify({held: [...held], mouse: events})
  }).catch(() => {});
}
let moveAt = 0;
canvas.addEventListener("mousedown", e => {
  canvas.focus();
  const [col, row] = cellAt(e);
  if (e.button === 0){
    mouse.push(["ldown", col, row, 1, 0]);
    mouse.push(["up", col, row, 0, 0]);
    flushMouse();
  } else if (e.button === 2){
    dragging = true;
    mouse.push(["rdown", col, row, 2, 0]);
    flushMouse();
  }
});
canvas.addEventListener("mousemove", e => {
  if (!dragging) return;
  const now = performance.now();
  if (now - moveAt < 45) return;
  moveAt = now;
  const [col, row] = cellAt(e);
  mouse.push(["move", col, row, 2, 0]);
  flushMouse();
});
window.addEventListener("mouseup", e => {
  if (e.button !== 2 || !dragging) return;
  dragging = false;
  const [col, row] = cellAt(e);
  mouse.push(["up", col, row, 0, 0]);
  flushMouse();
});
canvas.addEventListener("contextmenu", e => e.preventDefault());
canvas.addEventListener("wheel", e => {
  if (!frame) return;
  e.preventDefault();
  const [col, row] = cellAt(e);
  mouse.push(["wheel", col, row, 0, e.deltaY < 0 ? 1 : -1]);
  flushMouse();
}, {passive: false});
canvas.addEventListener("click", () => canvas.focus());
window.addEventListener("resize", fit);

setInterval(poll, 50);
poll();
</script>
</body>
</html>
""".replace("__TOKEN__", "__TOKEN__")
