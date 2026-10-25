"""Browser studio: render the exact char-cell frame with a real terminal font.

The PNG capture uses a small built-in bitmap font and tinted cell backgrounds,
which is convenient but not what the game actually looks like.  This module
writes a standalone HTML page and a JSON payload of raw cells, so a browser (or
headless Edge/Chrome) shows the same grid the terminal receives, and a sprite
gallery can be inspected at any zoom.

No third-party Python dependency is used.  Headless screenshots are an optional
convenience that shells out to a browser the user already has installed.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

STUDIO_MODELS = (
    ("knight", ("idle", "walk1", "atk1")),
    ("guard", ("idle",)),
    ("skeleton", ("idle", "atk")),
    ("captain", ("idle", "atk")),
    ("wolf", ("idle", "atk")),
    ("bandit", ("idle", "atk")),
    ("elder", ("idle",)),
    ("smith", ("idle",)),
)
YAW_SAMPLES = 8


def encode_screen(screen):
    """Raw cells and packed colours for one rendered frame."""
    return {
        "w": screen.w,
        "h": screen.h,
        "chars": ["".join(row) for row in screen.chars],
        "colors": [[int(c) for c in row] for row in screen.fg],
    }


def encode_sprite(sprite):
    """Raw cells and packed colours for one baked sprite."""
    return {
        "w": sprite.w,
        "h": sprite.h,
        "chars": ["".join(row) for row in sprite.chars],
        "colors": [[int(c) for c in row] for row in sprite.colors],
    }


def collect_models(atlas):
    """Sample every studio model/pose at evenly spaced yaw frames."""
    yaw_steps = max(1, int(getattr(atlas, "yaw_steps", 20)))
    yaw_indices = sorted({int(i * yaw_steps // YAW_SAMPLES) % yaw_steps
                          for i in range(YAW_SAMPLES)})
    entries = {}
    for model, poses in STUDIO_MODELS:
        pose_data = {}
        for pose in poses:
            frames = []
            for idx in yaw_indices:
                sprite = atlas.get(model, pose, idx)
                frames.append(encode_sprite(sprite) if sprite is not None
                              else None)
            if any(frames):
                pose_data[pose] = frames
        if pose_data:
            entries[model] = pose_data
    return {"yaw_steps": yaw_steps, "yaw_indices": yaw_indices,
            "entries": entries}


def write_studio(outdir, seed, viewport, scenes, models, checks):
    """Write index.html + studio-data.js; return their paths."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seed": seed, "viewport": list(viewport),
            "scenes": scenes, "models": models, "checks": checks}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    data_path = out / "studio-data.js"
    data_path.write_text("window.STUDIO = " + blob + ";\n", encoding="utf-8")
    html_path = out / "index.html"
    html_path.write_text(STUDIO_HTML, encoding="utf-8")
    return str(html_path), str(data_path)


def find_browser():
    """First installed Chromium-family browser, or None."""
    override = os.environ.get("ALDERVALE_BROWSER")
    if override and Path(override).is_file():
        return override
    for name in ("msedge", "chrome", "chromium", "google-chrome",
                 "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    roots = [os.environ.get("ProgramFiles(x86)"),
             os.environ.get("ProgramFiles"),
             os.environ.get("LOCALAPPDATA")]
    rel = (r"Microsoft\Edge\Application\msedge.exe",
           r"Google\Chrome\Application\chrome.exe")
    for root in roots:
        if not root:
            continue
        for tail in rel:
            candidate = Path(root) / tail
            if candidate.is_file():
                return str(candidate)
    for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                      "/usr/bin/google-chrome",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
        if Path(candidate).is_file():
            return candidate
    return None


def screenshot_studio(html_path, out_path, query="", size=(1600, 1000)):
    """Screenshot a studio page with headless Edge/Chrome; return (ok, detail)."""
    browser = find_browser()
    if browser is None:
        return False, "no Edge/Chrome found"
    html = Path(html_path).resolve()
    if not html.is_file():
        return False, "studio page missing: %s" % html
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    url = html.as_uri()
    if query:
        url += "?" + query.lstrip("?")
    width = max(320, int(size[0]))
    height = max(240, int(size[1]))
    profile = tempfile.mkdtemp(prefix="aldervale-web-")
    try:
        base = [browser, "--disable-gpu", "--hide-scrollbars",
                "--no-first-run", "--no-default-browser-check",
                "--virtual-time-budget=2500",
                "--window-size=%d,%d" % (width, height),
                "--user-data-dir=" + profile,
                "--screenshot=" + str(out), url]
        for mode in ("--headless=new", "--headless"):
            result = subprocess.run([browser, mode] + base[1:],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=90, check=False)
            if out.is_file() and out.stat().st_size > 0:
                return True, "%s (%d bytes)" % (out, out.stat().st_size)
            if result.returncode == 0:
                break
        return False, "browser produced no screenshot"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


STUDIO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aldervale Studio</title>
<style>
:root{--bg:#0b0e14;--panel:#121722;--line:#232b39;--ink:#dce5f2;
      --dim:#8b97aa;--gold:#e8c45a;--green:#7fd18a;--red:#e07a7a}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font-family:"Cascadia Mono",Consolas,"Courier New",monospace}
header{display:flex;flex-wrap:wrap;align-items:center;gap:16px;
       padding:12px 16px;border-bottom:1px solid var(--line);
       background:var(--panel)}
h1{font-size:16px;letter-spacing:.18em;margin:0;color:var(--gold)}
.sub{color:var(--dim);font-size:11px}
.tabs{display:flex;gap:6px;margin-left:auto}
.tabs button,.controls button,.controls select,.controls input{
  background:#0e1420;color:var(--ink);border:1px solid var(--line);
  border-radius:4px;padding:5px 9px;font:inherit;font-size:12px}
.tabs button.on{border-color:var(--gold);color:var(--gold)}
main{padding:14px 16px 24px}
.panel{display:none}
.panel.on{display:block}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
          margin-bottom:12px;font-size:12px;color:var(--dim)}
.controls label{display:flex;align-items:center;gap:6px}
.frame-host{overflow:auto;background:#000;border:1px solid var(--line);
            padding:14px;max-height:78vh}
.frame-host.dark{background:#05070a}
.frame-pre{margin:0;line-height:1;letter-spacing:0;white-space:pre;
           font-family:"Cascadia Mono",Consolas,"Courier New",monospace}
.frame-pre span{white-space:pre}
.caption{margin-top:8px;color:var(--dim);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left}
th{color:var(--gold);font-weight:normal}
.ok{color:var(--green)}.bad{color:var(--red)}
body.shot{background:#000}
body.shot header,body.shot .controls{display:none}
body.shot main{padding:0}
body.shot .panel{display:none}
body.shot .panel.on{display:flex;min-height:100vh;align-items:center;
                    justify-content:center}
body.shot .frame-host{border:0;padding:0;max-height:none;background:#000;
                      overflow:hidden}
body.shot .caption{position:fixed;left:10px;bottom:6px;margin:0;
                   font-size:11px;color:#4f5968}
</style>
</head>
<body>
<header>
  <h1>ALDERVALE STUDIO</h1>
  <span class="sub" id="subtitle"></span>
  <nav class="tabs">
    <button data-tab="scenes" class="on">Scenes</button>
    <button data-tab="models">Models</button>
    <button data-tab="checks">Checks</button>
  </nav>
</header>
<main>
  <section class="panel on" id="panel-scenes">
    <div class="controls">
      <label>Scene <select id="sceneSelect"></select></label>
      <label>Scale <input id="sceneScale" type="range" min="0.5" max="3"
             step="0.25" value="1"></label>
      <label><input id="sceneFit" type="checkbox"> fit window</label>
      <span id="sceneInfo"></span>
    </div>
    <div class="frame-host" id="sceneHost"><pre class="frame-pre"></pre></div>
    <div class="caption" id="sceneCaption"></div>
  </section>
  <section class="panel" id="panel-models">
    <div class="controls">
      <label>Model <select id="modelSelect"></select></label>
      <label>Pose <select id="poseSelect"></select></label>
      <label>Yaw <select id="yawSelect"></select></label>
      <label>Scale <input id="modelScale" type="range" min="1" max="8"
             step="0.5" value="4"></label>
      <label><input id="modelFit" type="checkbox"> fit window</label>
      <label><input id="modelGrid" type="checkbox"> grid</label>
      <label><input id="modelSpin" type="checkbox"> spin</label>
      <label><input id="modelTurn" type="checkbox"> all yaws</label>
      <span id="modelInfo"></span>
    </div>
    <div class="frame-host" id="modelHost"><pre class="frame-pre"></pre></div>
    <div class="caption" id="modelCaption"></div>
  </section>
  <section class="panel" id="panel-checks">
    <table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
    <tbody id="checkBody"></tbody></table>
  </section>
</main>
<script src="studio-data.js"></script>
<script>
const S = window.STUDIO;
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let current = {scene: 0, model: 0, pose: 0, yaw: 0};
let spinTimer = null;

function hex(c){ return "#" + c.toString(16).padStart(6, "0"); }

function renderFrame(host, frame, scale, grid){
  host.replaceChildren();
  const pre = document.createElement("pre");
  pre.className = "frame-pre";
  pre.style.fontSize = (8 * scale) + "px";
  if (grid){
    pre.style.backgroundImage =
      "linear-gradient(#1a2230 1px, transparent 1px)," +
      "linear-gradient(90deg, #1a2230 1px, transparent 1px)";
    pre.style.backgroundSize = (8 * scale) + "px " + (8 * scale) + "px";
  }
  for (let y = 0; y < frame.h; y++){
    const chars = frame.chars[y], colors = frame.colors[y];
    let start = 0, col = colors[0];
    for (let x = 1; x <= frame.w; x++){
      if (x === frame.w || colors[x] !== col){
        const span = document.createElement("span");
        span.textContent = chars.slice(start, x);
        span.style.color = hex(col);
        pre.appendChild(span);
        if (x < frame.w){ start = x; col = colors[x]; }
      }
    }
    if (y < frame.h - 1) pre.appendChild(document.createTextNode("\\n"));
  }
  host.appendChild(pre);
}

function fitScale(frame, maxW, maxH){
  const cellW = 4.8, cellH = 8;
  return Math.max(0.5, Math.min(maxW / (frame.w * cellW),
                                maxH / (frame.h * cellH)));
}

function sceneFrame(){ return S.scenes[current.scene].frame; }
function modelFrame(){
  const entry = S.models.entries[$("modelSelect").value];
  const pose = $("poseSelect").value;
  return {frame: entry[pose][current.yaw],
          label: $("modelSelect").value + "  " + pose +
                 "  yaw#" + S.models.yaw_indices[current.yaw]};
}

function drawScene(){
  const meta = S.scenes[current.scene];
  const fit = $("sceneFit").checked;
  const scale = fit ? fitScale(meta.frame, innerWidth - 40,
                               innerHeight - 120)
                    : parseFloat($("sceneScale").value);
  renderFrame($("sceneHost"), meta.frame, scale, false);
  $("sceneInfo").textContent = meta.frame.w + "x" + meta.frame.h +
    "  scale " + scale.toFixed(2);
  $("sceneCaption").textContent =
    "scene " + meta.name + "  .  day " + Number(meta.day_t).toFixed(2);
}

function drawTurnaround(){
  const host = $("modelHost");
  host.replaceChildren();
  const entry = S.models.entries[$("modelSelect").value];
  const pose = $("poseSelect").value;
  const scale = parseFloat($("modelScale").value);
  const wrap = document.createElement("div");
  wrap.style.display = "grid";
  wrap.style.gridTemplateColumns = "repeat(4, max-content)";
  wrap.style.gap = "14px 18px";
  wrap.style.alignItems = "flex-start";
  S.models.yaw_indices.forEach((yaw, i) => {
    const cell = document.createElement("div");
    const cap = document.createElement("div");
    cap.className = "sub";
    cap.textContent = "yaw " + yaw;
    cap.style.marginBottom = "4px";
    const inner = document.createElement("div");
    inner.className = "frame-host";
    inner.style.padding = "4px";
    renderFrame(inner, entry[pose][i], scale, $("modelGrid").checked);
    cell.appendChild(cap);
    cell.appendChild(inner);
    wrap.appendChild(cell);
  });
  host.appendChild(wrap);
  $("modelInfo").textContent = S.models.yaw_indices.length +
    " yaws  " + entry[pose][0].w + "x" + entry[pose][0].h +
    "  scale " + scale.toFixed(2);
  $("modelCaption").textContent = $("modelSelect").value + "  " + pose +
    "  turnaround";
}

function drawModel(){
  if ($("modelTurn").checked){ drawTurnaround(); return; }
  const picked = modelFrame();
  if (!picked.frame) return;
  const fit = $("modelFit").checked;
  const scale = fit ? fitScale(picked.frame, innerWidth - 40,
                               innerHeight - 120)
                    : parseFloat($("modelScale").value);
  renderFrame($("modelHost"), picked.frame, scale, $("modelGrid").checked);
  $("modelInfo").textContent = picked.frame.w + "x" + picked.frame.h +
    "  scale " + scale.toFixed(2);
  $("modelCaption").textContent = picked.label;
}

function setSpin(on){
  if (spinTimer){ clearInterval(spinTimer); spinTimer = null; }
  if (!on) return;
  spinTimer = setInterval(() => {
    if (!S.models.yaw_indices.length) return;
    current.yaw = (current.yaw + 1) % S.models.yaw_indices.length;
    $("yawSelect").value = String(current.yaw);
    drawModel();
  }, 200);
}

function refreshPoses(){
  const entry = S.models.entries[$("modelSelect").value];
  $("poseSelect").replaceChildren(...Object.keys(entry).map(p => {
    const o = document.createElement("option"); o.value = p;
    o.textContent = p; return o;
  }));
  current.pose = 0;
  refreshYaws();
}
function refreshYaws(){
  $("yawSelect").replaceChildren(...S.models.yaw_indices.map((v, i) => {
    const o = document.createElement("option"); o.value = String(i);
    o.textContent = "yaw " + v; return o;
  }));
  current.yaw = 0;
}

function setTab(name){
  document.querySelectorAll(".tabs button").forEach(b =>
    b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach(p =>
    p.classList.toggle("on", p.id === "panel-" + name));
  if (name === "scenes") drawScene();
  if (name === "models") drawModel();
}

document.querySelectorAll(".tabs button").forEach(b =>
  b.addEventListener("click", () => setTab(b.dataset.tab)));

function init(){
  $("subtitle").textContent = "seed " + S.seed + " . " +
    S.viewport[0] + "x" + S.viewport[1] + " . " + S.generated;
  $("sceneSelect").replaceChildren(...S.scenes.map((s, i) => {
    const o = document.createElement("option"); o.value = String(i);
    o.textContent = s.name; return o;
  }));
  $("modelSelect").replaceChildren(...Object.keys(S.models.entries).map(m => {
    const o = document.createElement("option"); o.value = m;
    o.textContent = m; return o;
  }));
  const tbody = $("checkBody");
  S.checks.forEach(c => {
    const tr = document.createElement("tr");
    [c.name, c.ok ? "PASS" : "FAIL", c.detail].forEach((v, i) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (i === 1) td.className = c.ok ? "ok" : "bad";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  const sceneName = params.get("scene");
  if (sceneName){
    const idx = S.scenes.findIndex(s => s.name === sceneName);
    if (idx >= 0) current.scene = idx;
  }
  $("sceneSelect").value = String(current.scene);
  if (params.get("sceneScale")) $("sceneScale").value = params.get("sceneScale");
  if (params.get("sceneFit") === "1") $("sceneFit").checked = true;

  const modelName = params.get("model");
  if (modelName && S.models.entries[modelName])
    $("modelSelect").value = modelName;
  refreshPoses();
  const pose = params.get("pose");
  if (pose && [...$("poseSelect").options].some(o => o.value === pose))
    $("poseSelect").value = pose;
  const yaw = parseInt(params.get("yaw") || "0", 10);
  if (yaw >= 0 && yaw < S.models.yaw_indices.length) current.yaw = yaw;
  $("yawSelect").value = String(current.yaw);
  if (params.get("scale")) $("modelScale").value = params.get("scale");
  if (params.get("fit") === "1") $("modelFit").checked = true;
  if (params.get("grid") === "1") $("modelGrid").checked = true;
  if (params.get("spin") === "1") $("modelSpin").checked = true;
  if (params.get("turn") === "1") $("modelTurn").checked = true;

  $("sceneSelect").addEventListener("change", e => {
    current.scene = parseInt(e.target.value, 10); drawScene();
  });
  $("sceneScale").addEventListener("input", drawScene);
  $("sceneFit").addEventListener("change", drawScene);
  $("modelSelect").addEventListener("change", () => { refreshPoses(); drawModel(); });
  $("poseSelect").addEventListener("change", () => { current.pose = 0; drawModel(); });
  $("yawSelect").addEventListener("change", e => {
    current.yaw = parseInt(e.target.value, 10); drawModel();
  });
  $("modelScale").addEventListener("input", drawModel);
  $("modelFit").addEventListener("change", drawModel);
  $("modelGrid").addEventListener("change", drawModel);
  $("modelSpin").addEventListener("change", e => setSpin(e.target.checked));
  $("modelTurn").addEventListener("change", drawModel);

  if (params.get("shot") === "1") document.body.classList.add("shot");
  setSpin($("modelSpin").checked);
  const tab = params.get("tab") || "scenes";
  setTab(tab === "models" ? "models" : (tab === "checks" ? "checks" : "scenes"));
  if (document.body.classList.contains("shot")){
    if (tab === "models"){
      $("modelFit").checked = true;
      drawModel();
    } else if (tab === "scenes"){
      $("sceneFit").checked = true;
      drawScene();
    }
  }
}
init();
</script>
</body>
</html>
"""
