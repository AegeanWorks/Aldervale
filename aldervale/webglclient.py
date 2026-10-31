"""WebGL browser client for the Aldervale GPU path.

The page receives a static heightfield/material bundle, a triangle-soup model
bundle, and a compact scene description per tick.  Rendering happens in WebGL2;
the existing text HUD is drawn on a transparent 2D canvas above it.
"""

PLAY3D_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aldervale - 3D</title>
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
#glcanvas,#hudcanvas{position:absolute;left:0;top:0;display:block}
#glcanvas{background:#05070a;border:1px solid var(--line);outline:none}
#hudcanvas{pointer-events:none;background:transparent}
#loading{position:absolute;inset:0;display:flex;align-items:center;
         justify-content:center;background:rgba(5,7,10,.88);
         color:var(--gold);font-size:14px;letter-spacing:.14em;text-align:center;
         padding:24px;z-index:4}
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
  <span id="status">Connecting to the 3D forge...</span>
  <span id="hud"></span>
</header>
<div id="stage">
  <canvas id="glcanvas" tabindex="0" aria-label="Aldervale 3D game view"></canvas>
  <canvas id="hudcanvas"></canvas>
  <div id="loading">FORGING THE GPU REALM...</div>
</div>
<footer>
  <span><kbd>WASD</kbd> move <kbd>arrows</kbd> move/turn
        <kbd>SPACE</kbd> attack <kbd>SHIFT</kbd> sprint <kbd>B</kbd> guard</span>
  <span><kbd>E</kbd> talk/take <kbd>I</kbd> bag <kbd>M</kbd> map
        <kbd>H</kbd> help <kbd>ESC</kbd> pause</span>
  <span>click to walk/attack . right-drag to look . wheel to zoom</span>
  <span><a href="/play">Pixel fallback</a></span>
  <span><a href="/">Launcher</a></span>
  <span class="note">WebGL2 GPU view over the same Python engine</span>
</footer>
<script>
window.addEventListener("error", e => {
  const el = document.getElementById("loading");
  if (el){ el.classList.remove("hide"); el.textContent = "JS error: " + e.message; }
});
const TOKEN = "__TOKEN__";
const glCanvas = document.getElementById("glcanvas");
const hudCanvas = document.getElementById("hudcanvas");
const gl = glCanvas.getContext("webgl2", {alpha: false, antialias: true});
const hctx = hudCanvas.getContext("2d");
const statusEl = document.getElementById("status");
const hudEl = document.getElementById("hud");
const loadingEl = document.getElementById("loading");
const stage = document.getElementById("stage");
window.addEventListener("error", e => {
  const el = document.getElementById("loading");
  if (el){ el.classList.remove("hide"); el.textContent = "JS error: " + e.message; }
});

let scene = null, world = null, models = null, glFailed = false;
let mapCanvas = null;
let lastSeq = -1, busy = false, ready = false, loading = false;
let dpr = 1, fitted = false;
let held = new Set(), pressed = [], mouse = [], dragging = false;
let heldChanged = false;
let framesThisSecond = 0, fps = 0, fpsAt = performance.now();
const MODAL = new Set(["title", "inventory", "help", "pause", "shop",
                       "dialogue", "dead"]);

function fail(text){
  loadingEl.classList.remove("hide");
  loadingEl.textContent = text;
  statusEl.textContent = "Error.";
}

function showLoading(text){
  loadingEl.classList.remove("hide");
  loadingEl.textContent = text;
}

function b64bytes(s){
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function b64float(s){
  const b = b64bytes(s);
  return new Float32Array(b.buffer);
}

/* ---------- tiny mat4 helpers (column-major) ---------- */
function mat4(){
  const m = new Float32Array(16);
  m[0] = m[5] = m[10] = m[15] = 1;
  return m;
}
function mul(a, b){
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++)
    for (let r = 0; r < 4; r++)
      o[c*4+r] = a[0*4+r]*b[c*4+0] + a[1*4+r]*b[c*4+1] +
                 a[2*4+r]*b[c*4+2] + a[3*4+r]*b[c*4+3];
  return o;
}
function perspective(fx, fy, near, far){
  const m = mat4();
  m[0] = fx; m[5] = fy;
  m[10] = (far + near) / (near - far);
  m[11] = -1;
  m[14] = (2 * far * near) / (near - far);
  m[15] = 0;
  return m;
}
function viewMatrix(cam){
  const s = Math.sin(cam.yaw), c = Math.cos(cam.yaw);
  const rx = c, rz = -s;       // right
  const fx = s, fz = c;        // forward
  const m = mat4();
  m[0] = rx; m[2] = rz;
  m[4] = 0;  m[6] = 0;
  m[8] = -fx; m[10] = -fz;
  m[12] = -(rx * cam.x + rz * cam.z);
  m[13] = -cam.y;
  m[14] = (fx * cam.x + fz * cam.z);
  return m;
}
function modelMatrix(x, y, z, yaw, scale){
  const s = Math.sin(yaw), c = Math.cos(yaw);
  const m = mat4();
  m[0] = c * scale; m[2] = -s * scale;
  m[5] = scale;
  m[8] = s * scale; m[10] = c * scale;
  m[12] = x; m[13] = y; m[14] = z;
  return m;
}
function norm3(v){
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}
function cross3(a, b){
  return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
          a[0]*b[1]-a[1]*b[0]];
}
function dot3(a, b){ return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
function lookAt(eye, center, up){
  const z = norm3([eye[0]-center[0], eye[1]-center[1], eye[2]-center[2]]);
  const x = norm3(cross3(up, z));
  const y = cross3(z, x);
  const m = mat4();
  m[0] = x[0]; m[1] = y[0]; m[2] = z[0];
  m[4] = x[1]; m[5] = y[1]; m[6] = z[1];
  m[8] = x[2]; m[9] = y[2]; m[10] = z[2];
  m[12] = -dot3(x, eye); m[13] = -dot3(y, eye); m[14] = -dot3(z, eye);
  return m;
}
function ortho(l, r, b, t, n, f){
  const m = mat4();
  m[0] = 2 / (r - l); m[5] = 2 / (t - b); m[10] = -2 / (f - n);
  m[12] = -(r + l) / (r - l); m[13] = -(t + b) / (t - b);
  m[14] = -(f + n) / (f - n);
  return m;
}
function lightMatrices(){
  const el = Math.max(0.12, scene.env.sun_el);
  const az = 2.35;
  const dir = norm3([Math.sin(az) * Math.cos(el), Math.sin(el),
                     Math.cos(az) * Math.cos(el)]);
  const c = scene.camera;
  const center = [c.x, 0, c.z];
  const eye = [center[0] + dir[0] * 100, center[1] + dir[1] * 100,
               center[2] + dir[2] * 100];
  const view = lookAt(eye, center, [0, 1, 0]);
  const proj = ortho(-50, 50, -50, 50, 0.1, 220);
  return {dir, vp: mul(proj, view),
          on: (shadowMapTex && scene.env.sun_el > 0.08) ? 1 : 0};
}
const lightPos = new Float32Array(18);
const lightCol = new Float32Array(18);
const lightRad = new Float32Array(6);
const lightFlick = new Float32Array(6);
function setPointLights(prog){
  const src = scene.lights || [];
  const n = Math.min(6, src.length);
  lightPos.fill(0); lightCol.fill(0); lightRad.fill(1); lightFlick.fill(1);
  const now = performance.now() / 1000;
  for (let i = 0; i < n; i++){
    const l = src[i];
    lightPos[i*3] = l.x; lightPos[i*3+1] = l.y; lightPos[i*3+2] = l.z;
    lightCol[i*3] = l.c[0]; lightCol[i*3+1] = l.c[1];
    lightCol[i*3+2] = l.c[2];
    lightRad[i] = l.r;
    const f = l.f === undefined ? 0.4 : l.f;
    lightFlick[i] = 1.0 + f * (0.10 * Math.sin(now * 9.0 + i * 2.3) +
                               0.06 * Math.sin(now * 15.7 + i * 1.7));
  }
  gl.uniform3fv(loc(prog, "uPointPos[0]"), lightPos);
  gl.uniform3fv(loc(prog, "uPointCol[0]"), lightCol);
  gl.uniform1fv(loc(prog, "uPointRadius[0]"), lightRad);
  gl.uniform1fv(loc(prog, "uPointFlick[0]"), lightFlick);
  gl.uniform1i(loc(prog, "uPointCount"), n);
  gl.uniform1f(loc(prog, "uPointPower"),
               0.10 + 0.32 * (1.0 - scene.env.daylight));
}

/* ---------- shader helpers ---------- */
function compile(type, src){
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw new Error(gl.getShaderInfoLog(s));
  return s;
}
function program(vs, fs){
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
  gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS))
    throw new Error(gl.getProgramInfoLog(p));
  return p;
}
function loc(p, name){ return gl.getUniformLocation(p, name); }

const SKY_VS = `#version 300 es
in vec2 aPos; out vec2 vUV;
void main(){ vUV = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.999, 1.0); }`;
const SKY_FS = `#version 300 es
precision mediump float; in vec2 vUV; out vec4 outColor;
uniform vec3 uZenith, uHorizon, uSun;
uniform vec2 uSunUV, uMoonUV;
uniform float uSunVis, uNight, uTime, uCloudAmt, uStarVis, uCloudBias;
float hash(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p){
  float v = 0.0; float a = 0.5;
  for (int i = 0; i < 3; i++){ v += noise(p) * a; p *= 2.03; a *= 0.5; }
  return v;
}
void main(){
  float t = clamp(vUV.y, 0.0, 1.0);
  vec3 c = mix(uHorizon, uZenith, pow(t, 0.75));
  vec2 cuv = vUV * vec2(6.5, 3.8);
  float base = fbm(cuv + vec2(uTime * 0.005, 0.0));
  float detail = fbm(cuv * 2.3 + vec2(uTime * 0.008, 0.02));
  float cl = smoothstep(0.56 - uCloudBias, 0.68 - uCloudBias,
                        base * 0.72 + detail * 0.32);
  float wisps = smoothstep(0.64 - uCloudBias, 0.82 - uCloudBias,
      fbm(vUV * vec2(12.0, 5.5) + vec2(uTime * 0.012, 0.0)));
  float cover = clamp(cl + wisps * 0.24, 0.0, 1.0);
  cover *= 0.5 + 0.5 * smoothstep(0.0, 0.30, vUV.y);
  vec3 cloudCol = mix(uHorizon * 1.05 + vec3(0.10), vec3(0.16, 0.18, 0.24),
                      uNight);
  cloudCol *= 0.88 + 0.14 * detail;
  cloudCol *= 0.80 + 0.30 * smoothstep(0.0, 0.70, vUV.y);
  float sd = distance(vUV * vec2(1.777, 1.0), uSunUV * vec2(1.777, 1.0));
  cloudCol += uSun * smoothstep(0.45, 0.0, sd) * 0.14 * (1.0 - uNight);
  c = mix(c, cloudCol, cover * uCloudAmt);
  if (uNight > 0.02){
    vec2 sp = vUV * vec2(240.0, 150.0);
    vec2 cell = floor(sp);
    vec2 f = fract(sp) - 0.5;
    float h = hash(cell);
    if (h > 0.982){
      float tw = 0.65 + 0.35 * sin(uNight * 9.0 + h * 80.0);
      float star = smoothstep(0.18, 0.0, length(f));
      c += vec3(0.75, 0.8, 0.95) * (h - 0.982) * 120.0 * tw * uNight * star * uStarVis;
    }
  }
  if (uSunVis > 0.0){
    float d = distance(vUV * vec2(1.777, 1.0), uSunUV * vec2(1.777, 1.0));
    c += uSun * smoothstep(0.55, 0.0, d) * 0.14 * uSunVis;
    c += uSun * smoothstep(0.16, 0.0, d) * 0.55 * uSunVis;
    c += uSun * smoothstep(0.035, 0.0, d) * 0.8 * uSunVis;
  }
  if (uNight > 0.05){
    float d = distance(vUV * vec2(1.777, 1.0), uMoonUV * vec2(1.777, 1.0));
    c += vec3(0.72, 0.76, 0.9) * smoothstep(0.30, 0.0, d) * 0.18 * uNight * uStarVis;
    c += vec3(0.72, 0.76, 0.9) * smoothstep(0.10, 0.0, d) * 0.45 * uNight * uStarVis;
    c += vec3(0.9, 0.92, 1.0) * smoothstep(0.025, 0.0, d) * 0.8 * uNight * uStarVis;
  }
  outColor = vec4(c, 1.0);
}`;

const TERRAIN_VS = `#version 300 es
in vec2 aXZ;
uniform sampler2D uHeight;
uniform float uW;
uniform mat4 uView, uProj;
out vec3 vWorld; out vec3 vNormal; out vec2 vUV;
float H(vec2 p){ return texture(uHeight, (p + 0.5) / uW).r; }
void main(){
  float h = H(aXZ);
  float hl = H(aXZ + vec2(-1.0, 0.0));
  float hr = H(aXZ + vec2( 1.0, 0.0));
  float hd = H(aXZ + vec2(0.0, -1.0));
  float hu = H(aXZ + vec2(0.0,  1.0));
  vNormal = normalize(vec3(hl - hr, 2.0, hd - hu));
  vWorld = vec3(aXZ.x, h, aXZ.y);
  vUV = (aXZ + 0.5) / uW;
  gl_Position = uProj * uView * vec4(vWorld, 1.0);
}`;
const TERRAIN_FS = `#version 300 es
precision mediump float;
in vec3 vWorld; in vec3 vNormal; in vec2 vUV;
out vec4 outColor;
uniform sampler2D uColor;
uniform sampler2D uShadowMap;
uniform mat4 uLightVP;
uniform vec3 uLight, uFog, uCam;
uniform vec3 uPointPos[6], uPointCol[6];
uniform float uPointRadius[6], uPointPower, uPointFlick[6];
uniform int uPointCount;
uniform float uDaylight, uFogStart, uFogEnd, uShadowOn, uWet, uSnow;
uniform float uSunLight, uCloud, uTime;
float hash22(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash22(i);
  float b = hash22(i + vec2(1.0, 0.0));
  float c = hash22(i + vec2(0.0, 1.0));
  float d = hash22(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
vec3 pointLight(vec3 p){
  vec3 add = vec3(0.0);
  for (int i = 0; i < 6; i++){
    if (i >= uPointCount) break;
    vec3 d = uPointPos[i] - p;
    float dist = length(d);
    float a = clamp(1.0 - dist / uPointRadius[i], 0.0, 1.0);
    add += uPointCol[i] * a * a * uPointPower * uPointFlick[i];
  }
  return add;
}
float cloudShade(vec2 p){
  float c = sin(p.x * 0.045 + uTime * 0.018) *
            sin(p.y * 0.038 - uTime * 0.012);
  return 1.0 - smoothstep(0.15, 0.85, c) * 0.16 * uCloud;
}
float shadowAt(vec3 world){
  if (uShadowOn < 0.5) return 1.0;
  vec4 lp = uLightVP * vec4(world, 1.0);
  vec3 p = lp.xyz / lp.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0)
    return 1.0;
  float bias = 0.0016;
  vec2 t = vec2(1.0 / 1024.0);
  float s = step(p.z - bias, texture(uShadowMap, p.xy).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + vec2(t.x, 0.0)).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + vec2(0.0, t.y)).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + t).r);
  return s * 0.25;
}
void main(){
  vec4 tex = texture(uColor, vUV);
  vec3 base = tex.rgb;
  float mat = tex.a * 255.0;
  float n = vnoise(vWorld.xz * 2.2);
  float fine = hash22(floor(vWorld.xz * 6.0));
  if (mat < 0.5){
    base *= 0.94 + 0.08 * sin(vWorld.x * 1.7 + vWorld.z * 0.9);
  } else if (mat < 1.5){
    base *= 0.90 + 0.16 * n;
    if (fine > 0.97) base = mix(base, vec3(0.82, 0.72, 0.28), 0.65);
  } else if (mat < 2.5){
    base *= 0.86 + 0.18 * n;
  } else if (mat < 3.5){
    base *= 0.92 + 0.12 * n;
    if (fine > 0.95) base = mix(base, vec3(0.72, 0.62, 0.50), 0.35);
  } else if (mat < 4.5){
    base *= 0.88 + 0.18 * vnoise(vWorld.xz * 3.4);
    base *= 0.95 + 0.05 * sin(vWorld.y * 3.0);
  } else {
    base = mix(base, vec3(0.92, 0.94, 0.98), 0.25 + 0.15 * fine);
  }
  base *= mix(1.0, 0.76, uWet);
  base = mix(base, vec3(0.82, 0.86, 0.93), uSnow * 0.58);
  float diff = max(dot(normalize(vNormal), uLight), 0.0);
  vec3 c = base * (0.72 + 0.34 * diff * uSunLight);
  c *= 0.55 + 0.45 * uDaylight;
  c *= mix(0.55, 1.0, shadowAt(vWorld + normalize(vNormal) * 0.35));
  c *= cloudShade(vWorld.xz);
  c += pointLight(vWorld);
  float dist = length(vWorld - uCam);
  float fog = clamp((dist - uFogStart) / (uFogEnd - uFogStart), 0.0, 1.0);
  outColor = vec4(mix(c, uFog, fog), 1.0);
}`;

const WATER_VS = `#version 300 es
in vec2 aXZ; uniform float uWater; uniform mat4 uView, uProj;
out vec3 vWorld;
void main(){ vWorld = vec3(aXZ.x, uWater, aXZ.y);
  gl_Position = uProj * uView * vec4(vWorld, 1.0); }`;
const WATER_FS = `#version 300 es
precision mediump float; in vec3 vWorld; out vec4 outColor;
uniform vec3 uDeep, uLit, uHorizon, uFog, uCam, uLight, uSunCol;
uniform float uTime, uFogStart, uFogEnd, uW, uRain;
uniform highp float uWater;
uniform sampler2D uHeight;
float hash22(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
void main(){
  vec2 hp = vWorld.xz;
  vec2 hb = (floor(hp) + 0.5) / uW;
  vec2 hf = fract(hp);
  float h00 = texture(uHeight, hb).r;
  float h10 = texture(uHeight, hb + vec2(1.0 / uW, 0.0)).r;
  float h01 = texture(uHeight, hb + vec2(0.0, 1.0 / uW)).r;
  float h11 = texture(uHeight, hb + vec2(1.0 / uW, 1.0 / uW)).r;
  float h = mix(mix(h00, h10, hf.x), mix(h01, h11, hf.x), hf.y);
  float depth = uWater - h;
  if (depth < 0.02) discard;
  float w = sin(vWorld.x * 0.55 + uTime * 1.3) +
            sin(vWorld.z * 0.83 - uTime * 1.1) * 0.7;
  float nx = cos(vWorld.x * 0.55 + uTime * 1.3) * 0.55 +
             cos(vWorld.z * 1.9 + uTime * 0.7) * 0.20;
  float nz = cos(vWorld.z * 0.83 - uTime * 1.1) * 0.58 +
             cos(vWorld.x * 1.7 - uTime * 0.9) * 0.18;
  vec3 nrm = normalize(vec3(nx * 0.11, 1.0, nz * 0.11));
  vec3 c = mix(uDeep, uLit, 0.5 + 0.18 * w);
  vec3 shallow = mix(uLit, vec3(0.20, 0.50, 0.46), 0.55);
  c = mix(shallow, c, smoothstep(0.15, 2.8, depth));
  vec3 v = normalize(uCam - vWorld);
  float fres = pow(1.0 - max(dot(nrm, v), 0.0), 3.0);
  c = mix(c, uHorizon, 0.28 + 0.42 * fres);
  vec3 hv = normalize(uLight + v);
  float spec = pow(max(dot(nrm, hv), 0.0), 90.0);
  c += uSunCol * spec;
  if (uRain > 0.5){
    vec2 rp = vWorld.xz * 1.15;
    vec2 f = fract(rp) - 0.5;
    float phase = fract(uTime * 0.85 + hash22(floor(rp)));
    float ring = smoothstep(0.055, 0.0, abs(length(f) - phase * 0.42));
    c += vec3(0.42, 0.52, 0.60) * ring * (1.0 - phase) * 0.45;
  }
  float foam = smoothstep(0.85, 0.02, depth);
  c = mix(c, vec3(0.82, 0.9, 0.94), foam * 0.55);
  float dist = length(vWorld - uCam);
  float fog = clamp((dist - uFogStart) / (uFogEnd - uFogStart), 0.0, 1.0);
  outColor = vec4(mix(c, uFog, fog), 0.80 + 0.14 * (1.0 - foam));
}`;

const MODEL_VS = `#version 300 es
in vec3 aPos; in vec3 aNorm; in vec3 aColor;
uniform mat4 uModel, uView, uProj;
out vec3 vNormal; out vec3 vColor; out vec3 vWorld;
void main(){
  vec4 w = uModel * vec4(aPos, 1.0);
  vWorld = w.xyz;
  vNormal = mat3(uModel) * aNorm;
  vColor = aColor;
  gl_Position = uProj * uView * w;
}`;
const MODEL_FS = `#version 300 es
precision mediump float;
in vec3 vNormal; in vec3 vColor; in vec3 vWorld;
out vec4 outColor;
uniform sampler2D uShadowMap;
uniform mat4 uLightVP;
uniform vec3 uLight, uFog, uCam, uTint;
uniform vec3 uPointPos[6], uPointCol[6];
uniform float uPointRadius[6], uPointPower, uPointFlick[6];
uniform int uPointCount;
uniform float uDaylight, uFogStart, uFogEnd, uFlash, uShadowOn;
uniform float uWet, uSnow, uSnowCap;
uniform float uSunLight, uCloud, uTime;
vec3 pointLight(vec3 p){
  vec3 add = vec3(0.0);
  for (int i = 0; i < 6; i++){
    if (i >= uPointCount) break;
    vec3 d = uPointPos[i] - p;
    float dist = length(d);
    float a = clamp(1.0 - dist / uPointRadius[i], 0.0, 1.0);
    add += uPointCol[i] * a * a * uPointPower * uPointFlick[i];
  }
  return add;
}
float cloudShade(vec2 p){
  float c = sin(p.x * 0.045 + uTime * 0.018) *
            sin(p.y * 0.038 - uTime * 0.012);
  return 1.0 - smoothstep(0.15, 0.85, c) * 0.16 * uCloud;
}
float shadowAt(vec3 world){
  if (uShadowOn < 0.5) return 1.0;
  vec4 lp = uLightVP * vec4(world, 1.0);
  vec3 p = lp.xyz / lp.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0)
    return 1.0;
  float bias = 0.0016;
  vec2 t = vec2(1.0 / 1024.0);
  float s = step(p.z - bias, texture(uShadowMap, p.xy).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + vec2(t.x, 0.0)).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + vec2(0.0, t.y)).r);
  s += step(p.z - bias, texture(uShadowMap, p.xy + t).r);
  return s * 0.25;
}
void main(){
  vec3 n = normalize(vNormal);
  float diff = max(dot(n, uLight), 0.0);
  vec3 c = vColor * uTint * (0.44 + 0.56 * diff * uSunLight);
  c *= mix(1.0, 0.88, uWet);
  float up = smoothstep(0.45, 0.88, n.y);
  vec3 snow = vec3(0.84, 0.88, 0.95) * (0.45 + 0.55 * uDaylight);
  c = mix(c, snow, uSnow * uSnowCap * up * 0.78);
  c *= mix(0.55, 1.0, shadowAt(vWorld + n * 0.18));
  c *= cloudShade(vWorld.xz);
  c += pointLight(vWorld);
  if (uWet > 0.01){
    vec3 v = normalize(uCam - vWorld);
    vec3 hv = normalize(uLight + v);
    float spec = pow(max(dot(n, hv), 0.0), 26.0);
    c += vec3(0.40, 0.44, 0.50) * spec * 0.35;
  }
  c = mix(c, vec3(1.0, 0.92, 0.75), uFlash * 0.5);
  float dist = length(vWorld - uCam);
  float fog = clamp((dist - uFogStart) / (uFogEnd - uFogStart), 0.0, 1.0);
  outColor = vec4(mix(c, uFog, fog), 1.0);
}`;

const TERRAIN_DEPTH_VS = `#version 300 es
in vec2 aXZ;
uniform sampler2D uHeight;
uniform float uW;
uniform mat4 uLightVP;
void main(){
  vec2 uv = (aXZ + 0.5) / uW;
  float h = texture(uHeight, uv).r;
  gl_Position = uLightVP * vec4(aXZ.x, h, aXZ.y, 1.0);
}`;
const MODEL_DEPTH_VS = `#version 300 es
in vec3 aPos;
uniform mat4 uModel, uLightVP;
void main(){ gl_Position = uLightVP * uModel * vec4(aPos, 1.0); }`;
const DEPTH_FS = `#version 300 es
precision mediump float; out vec4 outColor;
void main(){ outColor = vec4(1.0); }`;

const WEATHER_VS = `#version 300 es
in vec2 aPos; out vec2 vUV;
void main(){ vUV = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`;
const WEATHER_FS = `#version 300 es
precision mediump float; in vec2 vUV; out vec4 outColor;
uniform float uWeather, uTime, uNight, uFlash;
float hash(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
void main(){
  if (uFlash > 0.002){
    outColor = vec4(0.82, 0.88, 1.0, uFlash);
    return;
  }
  if (uWeather < 0.5) discard;
  if (uWeather < 1.5){
    vec2 g = vUV * vec2(300.0, 180.0);
    g.y += uTime * 18.0;
    g.x += uTime * 2.5;
    vec2 f = fract(g);
    float h = hash(floor(g));
    if (h < 0.12 && f.x < 0.18 && f.y < 0.60){
      outColor = vec4(0.58, 0.69, 0.84, 0.55);
    } else discard;
  } else {
    vec2 g = vUV * vec2(140.0, 84.0);
    g.y += uTime * 2.4;
    g.x += sin(uTime * 0.7 + g.y) * 0.5;
    vec2 f = fract(g) - 0.5;
    float h = hash(floor(g));
    if (h > 0.94 && length(f) < 0.18){
      outColor = vec4(0.92, 0.95, 1.0, 0.75);
    } else discard;
  }
}`;

const SHADOW_VS = `#version 300 es
in vec2 aDisc; out vec2 vUV;
uniform mat4 uModel, uView, uProj;
void main(){ vUV = aDisc * 0.5 + 0.5;
  gl_Position = uProj * uView * uModel * vec4(aDisc.x, 0.0, aDisc.y, 1.0); }`;
const SHADOW_FS = `#version 300 es
precision mediump float; in vec2 vUV; out vec4 outColor;
uniform sampler2D uShadow; uniform float uAlpha;
void main(){ outColor = vec4(0.015, 0.02, 0.028,
  texture(uShadow, vUV).a * uAlpha); }`;

let skyProg, terrainProg, waterProg, modelProg, shadowProg, weatherProg;
let terrainDepthProg, modelDepthProg;
let skyVAO, skyBuf;
let weatherVAO;
let shadowVAO, shadowCount, shadowTex;
let shadowFBO, shadowMapTex;
const SHADOW_SIZE = 1024;

let heightTex, colorTex, gridVAO, gridCount;
let gridPosBuffer, gridIndexBuffer, terrainDepthVAO;
let modelVS, modelNorm, modelCol, modelVAO, modelDepthVAO;

function initGL(){
  skyProg = program(SKY_VS, SKY_FS);
  terrainProg = program(TERRAIN_VS, TERRAIN_FS);
  waterProg = program(WATER_VS, WATER_FS);
  modelProg = program(MODEL_VS, MODEL_FS);
  shadowProg = program(SHADOW_VS, SHADOW_FS);
  weatherProg = program(WEATHER_VS, WEATHER_FS);
  terrainDepthProg = program(TERRAIN_DEPTH_VS, DEPTH_FS);
  modelDepthProg = program(MODEL_DEPTH_VS, DEPTH_FS);
  shadowMapTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, shadowMapTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.DEPTH_COMPONENT24,
                SHADOW_SIZE, SHADOW_SIZE, 0, gl.DEPTH_COMPONENT,
                gl.UNSIGNED_INT, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  shadowFBO = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFBO);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT,
                          gl.TEXTURE_2D, shadowMapTex, 0);
  gl.drawBuffers([gl.NONE]);
  gl.readBuffer(gl.NONE);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
    shadowMapTex = null;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  skyBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, skyBuf);
  gl.bufferData(gl.ARRAY_BUFFER,
    new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  skyVAO = gl.createVertexArray();
  gl.bindVertexArray(skyVAO);
  gl.bindBuffer(gl.ARRAY_BUFFER, skyBuf);
  const a = gl.getAttribLocation(skyProg, "aPos");
  gl.enableVertexAttribArray(a);
  gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  weatherVAO = gl.createVertexArray();
  gl.bindVertexArray(weatherVAO);
  gl.bindBuffer(gl.ARRAY_BUFFER, skyBuf);
  const wa = gl.getAttribLocation(weatherProg, "aPos");
  gl.enableVertexAttribArray(wa);
  gl.vertexAttribPointer(wa, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);

  const disc = [];
  const seg = 18;
  for (let i = 0; i < seg; i++){
    const a0 = i / seg * Math.PI * 2;
    const a1 = (i + 1) / seg * Math.PI * 2;
    disc.push(0, 0, Math.cos(a0), Math.sin(a0), Math.cos(a1), Math.sin(a1));
  }
  const sb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, sb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(disc), gl.STATIC_DRAW);
  shadowVAO = gl.createVertexArray();
  gl.bindVertexArray(shadowVAO);
  const sd = gl.getAttribLocation(shadowProg, "aDisc");
  gl.enableVertexAttribArray(sd);
  gl.vertexAttribPointer(sd, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  shadowCount = seg * 3;
  const sc = document.createElement("canvas");
  sc.width = sc.height = 64;
  const sg = sc.getContext("2d");
  const grad = sg.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0.0, "rgba(0,0,0,0.7)");
  grad.addColorStop(0.55, "rgba(0,0,0,0.42)");
  grad.addColorStop(1.0, "rgba(0,0,0,0)");
  sg.fillStyle = grad;
  sg.fillRect(0, 0, 64, 64);
  shadowTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, shadowTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, sc);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
}

function uploadWorld(wb){
  const w = wb.meta.w;
  world = wb;
  const hs = b64float(wb.heights);
  const cs = b64bytes(wb.colors);
  heightTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, heightTex);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, w, w, 0, gl.RED, gl.FLOAT, hs);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  colorTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, colorTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, w, 0, gl.RGBA,
                gl.UNSIGNED_BYTE, cs);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

  const n = w * w;
  const mc = document.createElement("canvas");
  mc.width = mc.height = w;
  const mctx = mc.getContext("2d");
  const mimg = mctx.createImageData(w, w);
  const md = mimg.data;
  for (let i = 0; i < n; i++){
    let r = cs[i*4], g = cs[i*4+1], b = cs[i*4+2];
    if (hs[i] <= wb.meta.water){
      r = r * 0.25 + 26; g = g * 0.25 + 54; b = b * 0.25 + 92;
    }
    md[i*4] = r; md[i*4+1] = g; md[i*4+2] = b; md[i*4+3] = 255;
  }
  mctx.putImageData(mimg, 0, 0);
  mapCanvas = mc;
  const pos = new Float32Array(n * 2);
  let o = 0;
  for (let z = 0; z < w; z++)
    for (let x = 0; x < w; x++){ pos[o++] = x; pos[o++] = z; }
  const idx = new Uint32Array((w - 1) * (w - 1) * 6);
  o = 0;
  for (let z = 0; z < w - 1; z++)
    for (let x = 0; x < w - 1; x++){
      const a = z * w + x, b = a + 1, c = a + w, d = c + 1;
      idx[o++] = a; idx[o++] = c; idx[o++] = b;
      idx[o++] = b; idx[o++] = c; idx[o++] = d;
    }
  gridVAO = gl.createVertexArray();
  gl.bindVertexArray(gridVAO);
  const vb = gl.createBuffer();
  gridPosBuffer = vb;
  gl.bindBuffer(gl.ARRAY_BUFFER, vb);
  gl.bufferData(gl.ARRAY_BUFFER, pos, gl.STATIC_DRAW);
  const aXZ = gl.getAttribLocation(terrainProg, "aXZ");
  gl.enableVertexAttribArray(aXZ);
  gl.vertexAttribPointer(aXZ, 2, gl.FLOAT, false, 0, 0);
  const ib = gl.createBuffer();
  gridIndexBuffer = ib;
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
  gridCount = idx.length;
  gl.bindVertexArray(null);

  terrainDepthVAO = gl.createVertexArray();
  gl.bindVertexArray(terrainDepthVAO);
  gl.bindBuffer(gl.ARRAY_BUFFER, gridPosBuffer);
  const dax = gl.getAttribLocation(terrainDepthProg, "aXZ");
  gl.enableVertexAttribArray(dax);
  gl.vertexAttribPointer(dax, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gridIndexBuffer);
  gl.bindVertexArray(null);

  const waterVAO = gl.createVertexArray();
  gl.bindVertexArray(waterVAO);
  const wbuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, wbuf);
  gl.bufferData(gl.ARRAY_BUFFER,
    new Float32Array([0,0, w,0, 0,w, w,0, w,w, 0,w]), gl.STATIC_DRAW);
  const wa = gl.getAttribLocation(waterProg, "aXZ");
  gl.enableVertexAttribArray(wa);
  gl.vertexAttribPointer(wa, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  world.waterVAO = waterVAO;
}

function uploadModels(mb){
  models = {meta: mb.meta};
  const pos = b64float(mb.pos);
  const norm = new Int8Array(b64bytes(mb.norm).buffer);
  const col = new Uint8Array(b64bytes(mb.col).buffer);
  modelVS = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, modelVS);
  gl.bufferData(gl.ARRAY_BUFFER, pos, gl.STATIC_DRAW);
  modelNorm = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, modelNorm);
  gl.bufferData(gl.ARRAY_BUFFER, norm, gl.STATIC_DRAW);
  modelCol = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, modelCol);
  gl.bufferData(gl.ARRAY_BUFFER, col, gl.STATIC_DRAW);
  modelVAO = gl.createVertexArray();
  gl.bindVertexArray(modelVAO);
  const ap = gl.getAttribLocation(modelProg, "aPos");
  const an = gl.getAttribLocation(modelProg, "aNorm");
  const ac = gl.getAttribLocation(modelProg, "aColor");
  gl.bindBuffer(gl.ARRAY_BUFFER, modelVS); gl.enableVertexAttribArray(ap);
  gl.vertexAttribPointer(ap, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, modelNorm); gl.enableVertexAttribArray(an);
  gl.vertexAttribPointer(an, 3, gl.BYTE, true, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, modelCol); gl.enableVertexAttribArray(ac);
  gl.vertexAttribPointer(ac, 3, gl.UNSIGNED_BYTE, true, 0, 0);
  gl.bindVertexArray(null);
  modelDepthVAO = gl.createVertexArray();
  gl.bindVertexArray(modelDepthVAO);
  gl.bindBuffer(gl.ARRAY_BUFFER, modelVS);
  const dp = gl.getAttribLocation(modelDepthProg, "aPos");
  gl.enableVertexAttribArray(dp);
  gl.vertexAttribPointer(dp, 3, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
}

function resize(){
  const maxW = Math.max(320, innerWidth - 36);
  const maxH = Math.max(220, innerHeight - 190);
  const aspect = 16 / 9;
  let cssW = maxW, cssH = Math.floor(cssW / aspect);
  if (cssH > maxH){ cssH = maxH; cssW = Math.floor(cssH * aspect); }
  cssW = Math.max(320, cssW);
  cssH = Math.max(180, Math.floor(cssW / aspect));
  dpr = Math.min(2, window.devicePixelRatio || 1);
  for (const c of [glCanvas, hudCanvas]){
    c.width = Math.floor(cssW * dpr);
    c.height = Math.floor(cssH * dpr);
    c.style.width = Math.floor(cssW) + "px";
    c.style.height = Math.floor(cssH) + "px";
  }
  stage.style.width = Math.floor(cssW) + "px";
  stage.style.height = Math.floor(cssH) + "px";
  gl.viewport(0, 0, glCanvas.width, glCanvas.height);
  fitted = true;
}

function drawShadowPass(light){
  if (!shadowMapTex || !light.on) return;
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFBO);
  gl.viewport(0, 0, SHADOW_SIZE, SHADOW_SIZE);
  gl.clear(gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);
  gl.disable(gl.BLEND);
  gl.enable(gl.CULL_FACE);
  gl.cullFace(gl.FRONT);
  gl.useProgram(terrainDepthProg);
  gl.bindVertexArray(terrainDepthVAO);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, heightTex);
  gl.uniform1i(loc(terrainDepthProg, "uHeight"), 0);
  gl.uniformMatrix4fv(loc(terrainDepthProg, "uLightVP"), false, light.vp);
  gl.uniform1f(loc(terrainDepthProg, "uW"), world.meta.w);
  gl.drawElements(gl.TRIANGLES, gridCount, gl.UNSIGNED_INT, 0);
  if (models){
    gl.useProgram(modelDepthProg);
    gl.bindVertexArray(modelDepthVAO);
    gl.uniformMatrix4fv(loc(modelDepthProg, "uLightVP"), false, light.vp);
    for (const ent of scene.entities){
      const poses = models.meta[ent.model];
      if (!poses) continue;
      const mesh = poses[ent.pose] || poses.idle;
      if (!mesh || !mesh.count) continue;
      const m = modelMatrix(ent.x, ent.y, ent.z, ent.yaw, ent.scale);
      gl.uniformMatrix4fv(loc(modelDepthProg, "uModel"), false, m);
      gl.drawArrays(gl.TRIANGLES, mesh.offset, mesh.count);
    }
  }
  gl.bindVertexArray(null);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.disable(gl.CULL_FACE);
  gl.viewport(0, 0, glCanvas.width, glCanvas.height);
}

function mix3(a, b, t){
  return [a[0] + (b[0] - a[0]) * t,
          a[1] + (b[1] - a[1]) * t,
          a[2] + (b[2] - a[2]) * t];
}
function weatherEnv(){
  const e = scene.env, dl = e.daylight;
  const dusk = 0.18 + 0.82 * dl;
  let zen = e.zenith, hor = e.horizon, fog = e.fog;
  let sun = Math.max(0, e.sun_el);
  let fogStart = 45.0, fogEnd = 210.0;
  let cloud = 0.40, stars = 1.0, sunLight = 1.0, cloudBias = -0.02;
  const w = scene.weather;
  if (w === "rain"){
    zen = mix3(zen, [0.10 * dusk, 0.12 * dusk, 0.16 * dusk], 0.72);
    hor = mix3(hor, [0.30 * dusk, 0.34 * dusk, 0.40 * dusk], 0.70);
    fog = mix3(fog, [0.32 * dusk, 0.36 * dusk, 0.43 * dusk], 0.75);
    sun *= 0.10; fogStart = 26.0; fogEnd = 140.0;
    cloud = 0.70; stars = 0.08; sunLight = 0.30; cloudBias = 0.10;
  } else if (w === "snow"){
    zen = mix3(zen, [0.44 * dusk, 0.49 * dusk, 0.58 * dusk], 0.68);
    hor = mix3(hor, [0.70 * dusk, 0.74 * dusk, 0.80 * dusk], 0.72);
    fog = mix3(fog, [0.70 * dusk, 0.75 * dusk, 0.82 * dusk], 0.70);
    sun *= 0.22; fogStart = 30.0; fogEnd = 155.0;
    cloud = 0.62; stars = 0.18; sunLight = 0.62; cloudBias = 0.08;
  }
  return {zen, hor, fog, sun, fogStart, fogEnd, cloud, stars, sunLight,
          cloudBias, cloudShade: cloud * (0.25 + 0.75 * dl)};
}

function drawSky(wenv){
  gl.disable(gl.DEPTH_TEST);
  gl.useProgram(skyProg);
  gl.bindVertexArray(skyVAO);
  const e = scene.env, c = scene.camera;
  gl.uniform3fv(loc(skyProg, "uZenith"), wenv.zen);
  gl.uniform3fv(loc(skyProg, "uHorizon"), wenv.hor);
  gl.uniform3f(loc(skyProg, "uSun"), 1.0, 0.92, 0.72);
  gl.uniform1f(loc(skyProg, "uSunVis"), wenv.sun);
  gl.uniform1f(loc(skyProg, "uCloudAmt"), wenv.cloud);
  gl.uniform1f(loc(skyProg, "uCloudBias"), wenv.cloudBias);
  gl.uniform1f(loc(skyProg, "uStarVis"), wenv.stars);
  const rel = 2.35 - c.yaw;
  const sx = Math.max(-1, Math.min(1, Math.tan(rel) / Math.tan(0.61)));
  const sy = Math.max(0, Math.min(1, 0.55 + e.sun_el * 0.3));
  gl.uniform2f(loc(skyProg, "uSunUV"), (sx + 1) * 0.5, sy);
  const mrel = 2.35 + Math.PI - c.yaw;
  const mx = Math.max(-1, Math.min(1, Math.tan(mrel) / Math.tan(0.61)));
  const my = Math.max(0, Math.min(1, 0.55 - e.sun_el * 0.3));
  gl.uniform2f(loc(skyProg, "uMoonUV"), (mx + 1) * 0.5, my);
  gl.uniform1f(loc(skyProg, "uNight"), 1.0 - e.daylight);
  gl.uniform1f(loc(skyProg, "uTime"), performance.now() / 1000.0);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.enable(gl.DEPTH_TEST);
}

function drawTerrain(proj, view, light, wenv){
  gl.useProgram(terrainProg);
  gl.bindVertexArray(gridVAO);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, heightTex);
  gl.uniform1i(loc(terrainProg, "uHeight"), 0);
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, colorTex);
  gl.uniform1i(loc(terrainProg, "uColor"), 1);
  gl.activeTexture(gl.TEXTURE2);
  gl.bindTexture(gl.TEXTURE_2D, shadowMapTex);
  gl.uniform1i(loc(terrainProg, "uShadowMap"), 2);
  const e = scene.env, c = scene.camera;
  gl.uniformMatrix4fv(loc(terrainProg, "uView"), false, view);
  gl.uniformMatrix4fv(loc(terrainProg, "uProj"), false, proj);
  gl.uniformMatrix4fv(loc(terrainProg, "uLightVP"), false, light.vp);
  gl.uniform1f(loc(terrainProg, "uShadowOn"), light.on);
  gl.uniform1f(loc(terrainProg, "uW"), world.meta.w);
  gl.uniform3fv(loc(terrainProg, "uLight"), light.dir);
  gl.uniform3fv(loc(terrainProg, "uFog"), wenv.fog);
  gl.uniform3f(loc(terrainProg, "uCam"), c.x, c.y, c.z);
  gl.uniform1f(loc(terrainProg, "uDaylight"), e.daylight);
  gl.uniform1f(loc(terrainProg, "uFogStart"), wenv.fogStart);
  gl.uniform1f(loc(terrainProg, "uFogEnd"), wenv.fogEnd);
  gl.uniform1f(loc(terrainProg, "uWet"), scene.weather === "rain" ? 1.0 : 0.0);
  gl.uniform1f(loc(terrainProg, "uSnow"), scene.weather === "snow" ? 1.0 : 0.0);
  gl.uniform1f(loc(terrainProg, "uSunLight"), wenv.sunLight);
  gl.uniform1f(loc(terrainProg, "uCloud"), wenv.cloudShade);
  gl.uniform1f(loc(terrainProg, "uTime"), performance.now() / 1000);
  setPointLights(terrainProg);
  gl.drawElements(gl.TRIANGLES, gridCount, gl.UNSIGNED_INT, 0);
}

function drawWater(proj, view, light, wenv){
  gl.useProgram(waterProg);
  gl.bindVertexArray(world.waterVAO);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  const e = scene.env, c = scene.camera;
  gl.uniformMatrix4fv(loc(waterProg, "uView"), false, view);
  gl.uniformMatrix4fv(loc(waterProg, "uProj"), false, proj);
  gl.uniform3f(loc(waterProg, "uDeep"), 0.09, 0.19, 0.31);
  gl.uniform3f(loc(waterProg, "uLit"), 0.26, 0.48, 0.64);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, heightTex);
  gl.uniform1i(loc(waterProg, "uHeight"), 0);
  gl.uniform1f(loc(waterProg, "uW"), world.meta.w);
  gl.uniform1f(loc(waterProg, "uWater"), world.meta.water);
  gl.uniform3fv(loc(waterProg, "uHorizon"), wenv.hor);
  gl.uniform3fv(loc(waterProg, "uFog"), wenv.fog);
  gl.uniform3f(loc(waterProg, "uCam"), c.x, c.y, c.z);
  gl.uniform3fv(loc(waterProg, "uLight"), light.dir);
  gl.uniform3f(loc(waterProg, "uSunCol"), 0.62 * e.daylight * wenv.sunLight,
               0.55 * e.daylight * wenv.sunLight,
               0.40 * e.daylight * wenv.sunLight);
  gl.uniform1f(loc(waterProg, "uRain"), scene.weather === "rain" ? 1.0 : 0.0);
  gl.uniform1f(loc(waterProg, "uTime"), performance.now() / 1000);
  gl.uniform1f(loc(waterProg, "uFogStart"), wenv.fogStart);
  gl.uniform1f(loc(waterProg, "uFogEnd"), wenv.fogEnd);
  gl.drawArrays(gl.TRIANGLES, 0, 6);
  gl.depthMask(true);
  gl.disable(gl.BLEND);
}

function drawShadows(proj, view){
  if (!scene || !scene.entities.length) return;
  gl.useProgram(shadowProg);
  gl.bindVertexArray(shadowVAO);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  gl.uniformMatrix4fv(loc(shadowProg, "uView"), false, view);
  gl.uniformMatrix4fv(loc(shadowProg, "uProj"), false, proj);
  const alpha = 0.08 + 0.09 * scene.env.daylight;
  gl.uniform1f(loc(shadowProg, "uAlpha"), alpha);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, shadowTex);
  gl.uniform1i(loc(shadowProg, "uShadow"), 0);
  for (const ent of scene.entities){
    const r = Math.max(0.22, (ent.radius || 0.4) * 1.05);
    const m = modelMatrix(ent.x, ent.y + 0.05, ent.z, 0.0, r);
    gl.uniformMatrix4fv(loc(shadowProg, "uModel"), false, m);
    gl.drawArrays(gl.TRIANGLES, 0, shadowCount);
  }
  gl.depthMask(true);
  gl.disable(gl.BLEND);
}

function drawModels(proj, view, light, wenv){
  if (!models || !scene.entities.length) return;
  gl.useProgram(modelProg);
  gl.bindVertexArray(modelVAO);
  gl.activeTexture(gl.TEXTURE2);
  gl.bindTexture(gl.TEXTURE_2D, shadowMapTex);
  gl.uniform1i(loc(modelProg, "uShadowMap"), 2);
  gl.uniformMatrix4fv(loc(modelProg, "uView"), false, view);
  gl.uniformMatrix4fv(loc(modelProg, "uProj"), false, proj);
  gl.uniformMatrix4fv(loc(modelProg, "uLightVP"), false, light.vp);
  gl.uniform1f(loc(modelProg, "uShadowOn"), light.on);
  const e = scene.env, c = scene.camera;
  gl.uniform3fv(loc(modelProg, "uLight"), light.dir);
  gl.uniform3fv(loc(modelProg, "uFog"), wenv.fog);
  gl.uniform3f(loc(modelProg, "uCam"), c.x, c.y, c.z);
  gl.uniform1f(loc(modelProg, "uDaylight"), e.daylight);
  gl.uniform1f(loc(modelProg, "uFogStart"), wenv.fogStart);
  gl.uniform1f(loc(modelProg, "uFogEnd"), wenv.fogEnd);
  gl.uniform1f(loc(modelProg, "uWet"), scene.weather === "rain" ? 1.0 : 0.0);
  gl.uniform1f(loc(modelProg, "uSnow"), scene.weather === "snow" ? 1.0 : 0.0);
  gl.uniform1f(loc(modelProg, "uSunLight"), wenv.sunLight);
  gl.uniform1f(loc(modelProg, "uCloud"), wenv.cloudShade);
  gl.uniform1f(loc(modelProg, "uTime"), performance.now() / 1000);
  setPointLights(modelProg);
  for (const ent of scene.entities){
    const poses = models.meta[ent.model];
    if (!poses) continue;
    const mesh = poses[ent.pose] || poses.idle;
    if (!mesh || !mesh.count) continue;
    const m = modelMatrix(ent.x, ent.y, ent.z, ent.yaw, ent.scale);
    gl.uniformMatrix4fv(loc(modelProg, "uModel"), false, m);
    gl.uniform3fv(loc(modelProg, "uTint"), ent.tint);
    gl.uniform1f(loc(modelProg, "uFlash"), ent.flash || 0);
    gl.uniform1f(loc(modelProg, "uSnowCap"),
                 (ent.model === "campfire" || ent.model === "torch" ||
                  ent.model === "wyvern") ? 0.0 : 1.0);
    gl.drawArrays(gl.TRIANGLES, mesh.offset, mesh.count);
  }
}

function lightningAt(t){
  const slot = Math.floor(t / 11.0);
  const phase = t - slot * 11.0;
  const h = Math.abs(Math.sin(slot * 12.9898) * 43758.5453) % 1;
  const start = 2.0 + h * 5.0;
  const d = phase - start;
  if (d < 0.0 || d > 0.45) return 0.0;
  return Math.max(0.0, Math.sin(d * 34.0)) * Math.exp(-d * 7.0) * 0.26;
}

function drawWeather(){
  if (!scene) return;
  const w = scene.weather;
  if (w !== "rain" && w !== "snow") return;
  gl.disable(gl.DEPTH_TEST);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.useProgram(weatherProg);
  gl.bindVertexArray(weatherVAO);
  gl.uniform1f(loc(weatherProg, "uWeather"), w === "rain" ? 1.0 : 2.0);
  gl.uniform1f(loc(weatherProg, "uTime"), performance.now() / 1000.0);
  gl.uniform1f(loc(weatherProg, "uNight"), 1.0 - scene.env.daylight);
  gl.uniform1f(loc(weatherProg, "uFlash"),
               w === "rain" ? lightningAt(performance.now() / 1000.0) : 0.0);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.bindVertexArray(null);
  gl.disable(gl.BLEND);
  gl.enable(gl.DEPTH_TEST);
}

const HUD_FONT = '"Cascadia Mono",Consolas,monospace';

function hudBar(x, y, w, h, frac, color, label, value, fontPx){
  frac = Math.max(0, Math.min(1, frac || 0));
  hctx.fillStyle = "rgba(255,255,255,.09)";
  hctx.fillRect(x, y, w, h);
  hctx.fillStyle = color;
  hctx.fillRect(x, y, w * frac, h);
  hctx.strokeStyle = "rgba(255,255,255,.18)";
  hctx.lineWidth = 1;
  hctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  hctx.font = (fontPx || 10) + "px " + HUD_FONT;
  hctx.textBaseline = "middle";
  hctx.textAlign = "left";
  hctx.fillStyle = "rgba(235,240,248,.94)";
  hctx.fillText(label, x + 6, y + h * 0.55);
  hctx.textAlign = "right";
  hctx.fillText(value, x + w - 6, y + h * 0.55);
}

function clipText(text, maxW){
  if (hctx.measureText(text).width <= maxW) return text;
  let s = text;
  while (s.length > 4 && hctx.measureText(s + "\u2026").width > maxW)
    s = s.slice(0, -2);
  return s + "\u2026";
}

function drawStatusPanel(cssW, cssH, panelH){
  const st = scene.hud_status;
  if (!st) return;
  const x = 12, y = cssH - panelH, w = cssW - 24, h = panelH;
  const pad = 12;
  const compact = panelH < 80;
  hctx.fillStyle = "rgba(6,9,15,.82)";
  hctx.fillRect(x, y, w, h);
  hctx.fillStyle = "rgba(232,196,90,.65)";
  hctx.fillRect(x, y, 2, h);
  hctx.strokeStyle = "rgba(232,196,90,.22)";
  hctx.beginPath();
  hctx.moveTo(x, y + 0.5);
  hctx.lineTo(x + w, y + 0.5);
  hctx.stroke();

  const top = y + (compact ? 13 : 20);
  hctx.textBaseline = "alphabetic";
  hctx.textAlign = "left";
  hctx.font = '600 ' + (compact ? 13 : 16) +
    'px "Segoe UI",system-ui,sans-serif';
  hctx.fillStyle = "#e8c45a";
  const nameW = hctx.measureText(st.name).width;
  hctx.fillText(st.name, x + pad, top);
  hctx.font = "11px " + HUD_FONT;
  hctx.fillStyle = "#8491a6";
  hctx.fillText("LEVEL " + st.level, x + pad + nameW + 12, top);

  hctx.textAlign = "right";
  hctx.font = "11px " + HUD_FONT;
  hctx.fillStyle = "#e8c45a";
  const gold = "GOLD " + st.gold;
  hctx.fillText(gold, x + w - pad, top);

  const gap = 8;
  const barH = compact ? 8 : 11;
  const barY = y + (compact ? 19 : 30);
  const barBottom = barY + barH;
  const barFont = compact ? 9 : 10;
  const barArea = Math.min(1180, w - pad * 2);
  const bw = (barArea - gap * 2) / 3;
  hudBar(x + pad, barY, bw, barH, st.hp / st.max_hp,
         st.hp <= st.max_hp * 0.35 ? "#e07a7a" : "#7fd18a",
         "HP", Math.ceil(st.hp) + " / " + st.max_hp, barFont);
  hudBar(x + pad + bw + gap, barY, bw, barH, st.stamina / st.max_stamina,
         "#78a0e6", "STA", Math.ceil(st.stamina), barFont);
  hudBar(x + pad + (bw + gap) * 2, barY, bw, barH, st.xp / st.xp_next,
         "#be96e6", "XP", st.xp + " / " + st.xp_next, barFont);

  hctx.font = (compact ? "9px " : "10px ") + HUD_FONT;
  hctx.textBaseline = "alphabetic";
  const gearY = Math.max(y + h - (compact ? 20 : 30),
                         barY + barH + (compact ? 11 : 12));
  hctx.textAlign = "left";
  hctx.fillStyle = "#9aa6ba";
  const gear = st.weapon.toUpperCase() + "  ATK " + st.weapon_atk +
    "    " + st.armor.toUpperCase() + "  DEF " + st.armor_def;
  hctx.fillText(clipText(gear, w - pad * 2 - (compact ? 96 : 130)),
                x + pad, gearY);
  hctx.textAlign = "right";
  hctx.fillStyle = "#f0a05a";
  hctx.fillText("POTIONS " + st.potions + " / 9", x + w - pad, gearY);
  hctx.textAlign = "left";
  hctx.fillStyle = "rgba(222,200,140,.92)";
  const questY = y + h - (compact ? 5 : 11);
  hctx.font = (compact ? 10 : 11) + "px " + HUD_FONT;
  hctx.fillText(clipText("QUEST  " + st.quest, w - pad * 2),
                x + pad, questY);
}

function projectPoint(x, y, z, vp, cssW, cssH, cam){
  const cx = vp[0] * x + vp[4] * y + vp[8] * z + vp[12];
  const cy = vp[1] * x + vp[5] * y + vp[9] * z + vp[13];
  const w = vp[3] * x + vp[7] * y + vp[11] * z + vp[15];
  if (w <= 0.15) return null;
  const sx = (cx / w * 0.5 + 0.5) * cssW;
  const sy = (0.5 - cy / w * 0.5) * cssH;
  if (sx < -250 || sx > cssW + 250 || sy < -250 || sy > cssH + 250)
    return null;
  return {x: sx, y: sy,
          dist: Math.hypot(x - cam.x, y - cam.y, z - cam.z)};
}

function projectLight(light, vp, cssW, cssH, cam){
  const p = projectPoint(light.x, light.y, light.z, vp, cssW, cssH, cam);
  if (!p || p.dist > 70.0) return null;
  const lightGlowRadius = 0.38;
  const fx = cam.f / (cam.w * 0.5);
  const radius = Math.max(18.0, Math.min(220.0,
    (light.r || 4.0) * lightGlowRadius * fx * cssW * 0.5 /
    Math.max(1.0, p.dist)));
  return {x: p.x, y: p.y, r: radius, dist: p.dist};
}

function drawLightGlow(cssW, cssH){
  const lights = scene.lights || [];
  if (!lights.length) return;
  const night = 1.0 - scene.env.daylight;
  if (night < 0.04) return;
  const cam = scene.camera;
  const fx = cam.f / (cam.w * 0.5);
  const fy = cam.fy / (cam.h * 0.5);
  const vp = mul(perspective(fx, fy, 0.4, 260.0), viewMatrix(cam));
  const now = performance.now() / 1000.0;
  hctx.save();
  hctx.globalCompositeOperation = "lighter";
  for (let i = 0; i < lights.length && i < 6; i++){
    const light = lights[i];
    const p = projectLight(light, vp, cssW, cssH, cam);
    if (!p) continue;
    const col = light.c || [1.0, 0.62, 0.30];
    const r = Math.round(col[0] * 255);
    const g = Math.round(col[1] * 255);
    const b = Math.round(col[2] * 255);
    const flick = 1.0 + (light.f === undefined ? 0.3 : light.f) * 0.12 *
      Math.sin(now * 9.0 + i * 2.1);
    const alpha = (0.10 + 0.30 * night) * flick;
    const grad = hctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
    grad.addColorStop(0.0, "rgba(" + r + "," + g + "," + b + "," +
                     (alpha * 0.52).toFixed(3) + ")");
    grad.addColorStop(0.28, "rgba(" + r + "," + g + "," + b + "," +
                     (alpha * 0.20).toFixed(3) + ")");
    grad.addColorStop(0.62, "rgba(" + r + "," + g + "," + b + "," +
                     (alpha * 0.05).toFixed(3) + ")");
    grad.addColorStop(1.0, "rgba(" + r + "," + g + "," + b + ",0)");
    hctx.fillStyle = grad;
    hctx.beginPath();
    hctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    hctx.fill();
  }
  hctx.restore();
}

let smokeSprite = null;

function smokePuff(){
  if (smokeSprite) return smokeSprite;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0.0, "rgba(236,239,244,1)");
  grad.addColorStop(0.55, "rgba(222,226,234,0.55)");
  grad.addColorStop(1.0, "rgba(210,214,224,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  smokeSprite = c;
  return c;
}

function drawChimneySmoke(cssW, cssH){
  const smoke = scene.smoke || [];
  if (!smoke.length) return;
  const cam = scene.camera;
  const fx = cam.f / (cam.w * 0.5);
  const fy = cam.fy / (cam.h * 0.5);
  const vp = mul(perspective(fx, fy, 0.4, 260.0), viewMatrix(cam));
  const now = performance.now() / 1000.0;
  const night = 1.0 - scene.env.daylight;
  hctx.save();
  for (const src of smoke){
    for (let i = 0; i < 4; i++){
      const t = (now * 0.05 + src.phase + i * 0.25) % 1.0;
      const drift = Math.sin(now * 0.5 + src.phase * 6.28 + i * 1.7) * 0.28
        + t * 1.35;
      const p = projectPoint(src.x + drift, src.y + t * 3.6,
                             src.z + drift * 0.45, vp, cssW, cssH, cam);
      if (!p) continue;
      const radius = Math.max(9.0, Math.min(64.0,
        (0.40 + t * 1.10) * fx * cssW * 0.5 / Math.max(1.0, p.dist)));
      const alpha = (1.0 - t) * (0.28 + 0.06 * night);
      hctx.globalAlpha = alpha;
      hctx.drawImage(smokePuff(), p.x - radius, p.y - radius,
                     radius * 2, radius * 2);
      hctx.globalAlpha = 1.0;
    }
  }
  hctx.restore();
}

function drawHud(){
  const cssW = hudCanvas.width / dpr, cssH = hudCanvas.height / dpr;
  hctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  hctx.clearRect(0, 0, cssW, cssH);
  if (!scene) return;
  if (MODAL.has(scene.state)){
    hctx.fillStyle = scene.state === "title"
      ? "rgba(4,6,10,.35)" : "rgba(4,6,10,.62)";
    hctx.fillRect(0, 0, cssW, cssH);
  } else {
    drawLightGlow(cssW, cssH);
    drawChimneySmoke(cssW, cssH);
  }
  const w = scene.camera.w, h = scene.camera.h;
  const cw = cssW / w, ch = cssH / h;
  const graphical = !!scene.hud_status && !MODAL.has(scene.state) && ch >= 11;
  if (!MODAL.has(scene.state)){
    hctx.fillStyle = "rgba(5,8,13,.42)";
    hctx.fillRect(0, cssH - ch * 5.2, cssW, ch * 5.2);
  }
  if (scene.show_map && mapCanvas){
    const ms = Math.min(180, Math.floor(cssH * 0.30));
    const mx = cssW - ms - 12, my = 12;
    const span = 110.0;
    const p = scene.player || {x: 0, z: 0};
    const sx = p.x - span * 0.5, sz = p.z - span * 0.5;
    hctx.imageSmoothingEnabled = false;
    hctx.drawImage(mapCanvas, sx, sz, span, span, mx, my, ms, ms);
    hctx.strokeStyle = "rgba(232,196,90,.55)";
    hctx.lineWidth = 1;
    hctx.strokeRect(mx + 0.5, my + 0.5, ms - 1, ms - 1);
    for (const ent of scene.entities){
      if (ent.model === "knight" || ent.kind === "player") continue;
      if (ent.x < sx || ent.x > sx + span || ent.z < sz ||
          ent.z > sz + span) continue;
      const ex = mx + (ent.x - sx) / span * ms;
      const ey = my + (ent.z - sz) / span * ms;
      const k = ent.kind || "";
      hctx.fillStyle = (k === "wolf" || k === "bandit" ||
                        k === "skeleton" || k === "captain")
        ? "#e07a7a" : (k === "villager" || k === "guard") ? "#7fd18a"
        : (k === "chicken") ? "#e8e8e8" : "#8b97aa";
      hctx.fillRect(ex - 1.5, ey - 1.5, 3, 3);
    }
    const px = mx + (p.x - sx) / span * ms;
    const py = my + (p.z - sz) / span * ms;
    hctx.fillStyle = "#ffe08a";
    hctx.beginPath();
    hctx.arc(px, py, 3.2, 0, Math.PI * 2);
    hctx.fill();
    hctx.fillStyle = "rgba(232,196,90,.9)";
    hctx.font = "10px monospace";
    hctx.textAlign = "center";
    hctx.fillText("N", mx + ms * 0.5, my + 12);
    hctx.textAlign = "center";
  }
  hctx.font = Math.max(8, Math.floor(ch * 0.92)) +
    'px "Cascadia Mono",Consolas,monospace';
  hctx.textAlign = "center";
  hctx.textBaseline = "middle";
  const chars = scene.hud.chars, colors = scene.hud.colors;
  for (let y = 0; y < (graphical ? h - 5 : h); y++){
    let x = 0;
    while (x < w){
      const color = colors[y][x];
      let end = x + 1;
      while (end < w && colors[y][end] === color) end++;
      const ink = "#" + color.toString(16).padStart(6, "0");
      for (let i = x; i < end; i++){
        const g = chars[y][i];
        if (g === " ") continue;
        const px = i * cw + cw * 0.5, py = y * ch + ch * 0.52;
        hctx.fillStyle = "rgba(3,5,9,.88)";
        hctx.fillText(g, px + 1, py + 1);
        hctx.fillStyle = ink;
        hctx.fillText(g, px, py);
      }
      x = end;
    }
  }
  if (graphical) drawStatusPanel(cssW, cssH, ch * 5.2);
}

function render(){
  if (!scene || !world || !models) return;
  const started = performance.now();
  const c = scene.camera, e = scene.env;
  const fx = c.f / (c.w * 0.5);
  const fy = c.fy / (c.h * 0.5);
  const proj = perspective(fx, fy, 0.4, 260.0);
  const view = viewMatrix(c);
  const light = lightMatrices();
  const wenv = weatherEnv();
  drawShadowPass(light);
  gl.clearColor(0.03, 0.04, 0.07, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);
  gl.disable(gl.CULL_FACE);
  drawSky(wenv);
  drawTerrain(proj, view, light, wenv);
  drawShadows(proj, view);
  drawWater(proj, view, light, wenv);
  drawModels(proj, view, light, wenv);
  drawWeather();
  drawHud();
  window.__renderMs = performance.now() - started;
}

function frameLoop(){
  requestAnimationFrame(frameLoop);
  if (!ready) return;
  render();
  framesThisSecond++;
  const now = performance.now();
  if (now - fpsAt >= 1000){
    fps = Math.round(framesThisSecond * 1000 / (now - fpsAt));
    framesThisSecond = 0; fpsAt = now;
  }
}

async function loadAssets(){
  if (loading || glFailed) return;
  if (!gl){ fail("WebGL2 is not available."); return; }
  loading = true;
  try {
    showLoading("FORGING THE GPU REALM...");
    const wb = await (await fetch("/api/world3d", {cache: "no-store"})).json();
    if (wb.status !== "ready"){ loading = false; return; }
    uploadWorld(wb);
    showLoading("RAISING THE MODELS...");
    const mb = await (await fetch("/api/models3d", {cache: "no-store"})).json();
    if (mb.status !== "ready"){ loading = false; return; }
    uploadModels(mb);
    ready = true;
    loadingEl.classList.add("hide");
    statusEl.textContent = "WebGL2 3D.";
    glCanvas.focus();
  } catch (err){
    fail("Asset load failed: " + err);
  }
}

function updateHud(data){
  hudEl.textContent = (data.weather || "clear") + "  " + fps + " fps";
}

async function poll(){
  if (busy) return;
  busy = true;
  try {
    const r = await fetch("/api/scene3d", {cache: "no-store"});
    const data = await r.json();
    if (data.status === "ready"){
      scene = data;
      if (!ready) loadAssets();
      if (!fitted) resize();
      updateHud(data);
      window.__sceneSeq = data.seq;
    } else if (data.status === "error"){
      fail("The forge failed: " + data.message);
    } else {
      showLoading("FORGING THE GPU REALM...");
    }
  } catch (err){
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
    await fetch("/api/input3d", {method: "POST",
      headers: {"Content-Type": "application/json",
                "X-Aldervale-Token": TOKEN},
      body: JSON.stringify(body)});
  } catch (err) {
    statusEl.textContent = "Input lost: " + err;
  }
}

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
  return ["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"," ","Tab"]
    .includes(e.key);
}
window.addEventListener("keydown", e => {
  const t = tokenFor(e);
  if (!t) return;
  if (block(e)) e.preventDefault();
  if (e.repeat || held.has(t)) return;
  held.add(t); pressed.push(t); heldChanged = true; sendInput();
});
window.addEventListener("keyup", e => {
  const t = tokenFor(e);
  if (!t) return;
  if (block(e)) e.preventDefault();
  if (!held.delete(t)) return;
  heldChanged = true; sendInput();
});
window.addEventListener("blur", () => {
  held.clear(); heldChanged = true; sendInput();
});

function cellAt(e){
  if (!scene) return [0, 0];
  const r = glCanvas.getBoundingClientRect();
  return [Math.floor((e.clientX - r.left) / r.width * scene.camera.w),
          Math.floor((e.clientY - r.top) / r.height * scene.camera.h)];
}
function flushMouse(){
  const events = mouse.splice(0);
  if (!events.length) return;
  fetch("/api/input3d", {method: "POST",
    headers: {"Content-Type": "application/json",
              "X-Aldervale-Token": TOKEN},
    body: JSON.stringify({held: [...held], mouse: events})}).catch(() => {});
}
let moveAt = 0;
glCanvas.addEventListener("mousedown", e => {
  glCanvas.focus();
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
glCanvas.addEventListener("mousemove", e => {
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
glCanvas.addEventListener("contextmenu", e => e.preventDefault());
glCanvas.addEventListener("wheel", e => {
  if (!scene) return;
  e.preventDefault();
  const [col, row] = cellAt(e);
  mouse.push(["wheel", col, row, 0, e.deltaY < 0 ? 1 : -1]);
  flushMouse();
}, {passive: false});
glCanvas.addEventListener("click", () => glCanvas.focus());
window.addEventListener("resize", () => { if (scene){ resize(); } });

try {
  if (!gl) throw new Error("WebGL2 is not available");
  initGL();
} catch (err){
  glFailed = true;
  fail("WebGL2 failed: " + err);
}
setInterval(poll, 50);
poll();
requestAnimationFrame(frameLoop);
</script>
</body>
</html>
""".replace("__TOKEN__", "__TOKEN__")
