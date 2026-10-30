"""Scene renderer: animated sky, voxel-marched terrain and billboard sprites.

The terrain uses a column ray-march over the heightfield (front-to-back with a
per-column hidden-row buffer and per-cell depth), then entities are blitted
far-to-near as depth-tested billboards with fog and day/night tinting.
"""

import math

from .buffer import pack_rgb, FAR
from .noise import fbm, rand01
from .terrain import M_DIRT, M_FOREST, M_GRASS, M_ROCK, M_SNOW

FOV = 1.22
MAX_DIST = 230.0
FOG_START = 55.0

SKY_ZENITH_DAY = pack_rgb(88, 140, 204)
SKY_HORIZON_DAY = pack_rgb(168, 200, 226)
SKY_ZENITH_NIGHT = pack_rgb(7, 9, 20)
SKY_HORIZON_NIGHT = pack_rgb(24, 28, 46)
SKY_DAWN = pack_rgb(224, 138, 84)
SUN_COLOR = pack_rgb(255, 238, 188)
SUN_AZ = 2.35
FIRE_COLOR = pack_rgb(255, 186, 96)
MOON_COLOR = pack_rgb(208, 216, 238)
STAR_COLOR = pack_rgb(198, 208, 238)
CLOUD_DAY = pack_rgb(228, 234, 242)
CLOUD_NIGHT = pack_rgb(52, 58, 78)
WATER_DEEP = pack_rgb(22, 48, 80)
WATER_LIT = pack_rgb(66, 122, 162)

_SIN64 = [math.sin(i * math.pi / 32.0) for i in range(64)]
_CLOUDS = None
_CLOUD_W = 256
_CLOUD_H = 26
_BAYER8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)
_RIDGES = None

def _tile(text):
    return (text + " " * 16)[:16]


GROUND_TILES = (
    (_tile(".  . .  , .  . ."), _tile("..,..`..,..`.  .")),
    (_tile("'  , .  '  ` ,  "), _tile("',,`';,.,`'`; ,.")),
    (_tile(";  : ,  ;  . ,  "), _tile(";;:,;,.::;,:,.;")),
    (_tile("-  . ,  -  ` .  "), _tile("--..,-`.-,.-..`")),
    (_tile("/ \\  | /  # \\  "), _tile("//\\\\||##/\\|#/\\")),
    (_tile("  .    '  .   `  "), _tile(" ..'`..'...`.'.. ")),
)
RIDGE_COLOR = pack_rgb(38, 46, 66)


def _ridges():
    global _RIDGES
    if _RIDGES is None:
        layers = []
        for layer in range(3):
            vals = []
            for x in range(768):
                v = fbm(x * 0.013 + layer * 9.0, layer * 2.7, 700 + layer, 3)
                r = max(0.0, 1.0 - abs(v - 0.5) * 2.0)
                vals.append(r ** 1.5)
            layers.append(vals)
        _RIDGES = layers
    return _RIDGES


def _clouds():
    global _CLOUDS
    if _CLOUDS is None:
        _CLOUDS = []
        for y in range(_CLOUD_H):
            row = []
            for x in range(_CLOUD_W):
                v = fbm(x * 0.045, y * 0.11, 909, 3)
                v += (1.0 - y / _CLOUD_H) * 0.06
                row.append(v)
            _CLOUDS.append(row)
    return _CLOUDS


def clear_camera_distance(terrain, px, pz, eye_y, fx, fz, cam_y, desired):
    """Pull the camera in when a hill would sit between it and the player."""
    steps = 9
    for i in range(1, steps + 1):
        t = i / steps
        sx = px - fx * desired * t
        sz = pz - fz * desired * t
        gh = terrain.height(sx, sz)
        line = eye_y + (cam_y - eye_y) * t
        if gh > line - 0.15:
            return max(2.2, desired * t - 0.5)
    return desired


class Camera:
    """View parameters plus precomputed per-column ray angles."""

    __slots__ = ("x", "y", "z", "yaw", "pitch", "w", "h", "f", "fy", "horizon",
                 "col_angle", "dist")

    def __init__(self, w, h, x, z, y, yaw, pitch=0.30, dist=7.0):
        self.w, self.h = w, h
        self.x, self.y, self.z = x, y, z
        self.yaw = yaw
        self.pitch = pitch
        self.dist = dist
        self.f = (w * 0.5) / math.tan(FOV * 0.5)
        self.fy = self.f * 0.5
        horizon = int(h * 0.5 - math.tan(pitch) * self.fy)
        self.horizon = max(3, min(h - 3, horizon))
        half_tan = math.tan(FOV * 0.5)
        self.col_angle = [math.atan((x - w * 0.5 + 0.5) / (w * 0.5) * half_tan)
                          for x in range(w)]


class Env:
    """Per-frame atmosphere derived from the world clock."""

    __slots__ = ("t", "day_t", "daylight", "night", "warm", "ambient", "fog",
                 "zenith", "horizon_col", "sun_el")

    def __init__(self, day_t, t):
        self.t = t
        self.day_t = day_t
        phase = day_t * 2.0 * math.pi
        sun_el = math.sin(phase)
        self.sun_el = sun_el
        daylight = max(0.0, min(1.0, (sun_el + 0.1) * 2.6))
        self.daylight = daylight
        self.night = 1.0 - daylight
        self.warm = max(0.0, 1.0 - abs(sun_el) * 2.8)
        zen = _mix(SKY_ZENITH_NIGHT, SKY_ZENITH_DAY, daylight)
        hor = _mix(SKY_HORIZON_NIGHT, SKY_HORIZON_DAY, daylight)
        hor = _mix(hor, SKY_DAWN, self.warm * 0.6)
        zen = _mix(zen, SKY_DAWN, self.warm * 0.18)
        self.zenith = zen
        self.horizon_col = hor
        self.fog = hor
        ar = 0.36 + 0.64 * daylight
        ag = 0.40 + 0.58 * daylight
        ab = 0.55 + 0.39 * daylight
        wk = self.warm * 0.5
        self.ambient = (min(1.1, ar * (1.0 + wk * 0.1)), ag * (1.0 - wk * 0.04),
                        ab * (1.0 - wk * 0.1))


def _mix(c1, c2, t):
    if t <= 0.0:
        return c1
    if t >= 1.0:
        return c2
    return pack_rgb(
        ((c1 >> 16) & 255) + (((c2 >> 16) & 255) - ((c1 >> 16) & 255)) * t,
        ((c1 >> 8) & 255) + (((c2 >> 8) & 255) - ((c1 >> 8) & 255)) * t,
        (c1 & 255) + ((c2 & 255) - (c1 & 255)) * t,
    )


def render_scene(screen, world, cam, env):
    """Draw sky, terrain, entities, smoke and weather into the screen buffer."""
    weather = getattr(world, "weather", "clear")
    _sky(screen, cam, env)
    _terrain(screen, world.terrain, cam, env,
             wet=0.20 if weather == "rain" else 0.0,
             snow=0.22 if weather == "snow" else 0.0)
    _light_pools(screen, world, cam, env)
    _entities(screen, world, cam, env)
    _smoke(screen, world, cam, env)
    _weather(screen, weather, env)
    if env.night > 0.15:
        _fireflies(screen, world, cam, env)


def _weather(screen, weather, env):
    """Deterministic rain streaks or drifting snow, drawn above the world."""
    if weather not in ("rain", "snow"):
        return
    w, h = screen.w, screen.h
    t = env.t
    if weather == "rain":
        color = pack_rgb(146, 176, 212)
        drops = max(16, (w * h) // 220)
        for i in range(drops):
            x = int(rand01(i, 7, 31) * w + t * 26.0 + i * 3) % w
            y = int(rand01(i, 11, 37) * h + t * 62.0 + i * 5) % h
            screen.set(x, y, "/" if i & 1 else "\\", color, 0.0)
            if y > 0:
                screen.set(x, y - 1, "|", color, 0.0)
    else:
        color = pack_rgb(226, 236, 248)
        flakes = max(18, (w * h) // 260)
        for i in range(flakes):
            x = int(rand01(i, 5, 41) * w +
                    math.sin(t * 0.8 + i) * 2.2 + i * 1.7) % w
            y = int(rand01(i, 9, 43) * h + t * 7.0 + i * 2.3) % h
            screen.set(x, y, "*" if i % 9 == 0 else '"', color, 0.0)


def _sky(screen, cam, env):
    w, h = screen.w, screen.h
    chars, fg, depth = screen.chars, screen.fg, screen.depth
    horizon = cam.horizon
    zenith, horc = env.zenith, env.horizon_col
    zr, zg, zb = (zenith >> 16) & 255, (zenith >> 8) & 255, zenith & 255
    hr, hgc, hb = (horc >> 16) & 255, (horc >> 8) & 255, horc & 255
    rows = max(1, horizon)
    row_colors = []
    for y in range(min(horizon, h)):
        t = y / rows
        t2 = t * t * (3.0 - 2.0 * t)
        row_colors.append(pack_rgb(hr + (zr - hr) * t2, hgc + (zg - hgc) * t2,
                                   hb + (zb - hb) * t2))
    for y in range(min(horizon, h)):
        col = row_colors[y]
        crow = chars[y]
        frow = fg[y]
        drow = depth[y]
        tt = y / rows
        fill = 0.10 + 0.30 * (1.0 - tt)
        fill2 = fill * 0.5
        for x in range(w):
            v = (_BAYER8[(y + ((x * 3) >> 4)) & 7][(x + (y >> 1)) & 7]
                 + 0.5) / 64.0
            if v < fill:
                if v < fill2 * 0.45:
                    crow[x] = ","
                elif v < fill2:
                    crow[x] = ":"
                else:
                    crow[x] = "."
            else:
                crow[x] = " "
            frow[x] = col
            drow[x] = FAR
    if env.night > 0.05:
        alpha = env.night
        for i in range(110):
            if rand01(i, 3, 42) > alpha:
                continue
            az = rand01(i, 1, 42) * 6.28318
            el = 0.06 + rand01(i, 2, 42) * 0.85
            rel = az - cam.yaw
            while rel > math.pi:
                rel -= 6.28318
            while rel < -math.pi:
                rel += 6.28318
            if abs(rel) > FOV * 0.62:
                continue
            col = int(w * 0.5 + math.tan(rel) / math.tan(FOV * 0.5) * w * 0.5)
            row = int(horizon - el * cam.fy * 0.85)
            if 0 <= col < w and 0 <= row < horizon:
                bright = rand01(i, 4, 42)
                chars[row][col] = "+" if bright > 0.8 else "."
                fg[row][col] = STAR_COLOR
    sun_az = SUN_AZ
    _disc(screen, cam, sun_az, env.sun_el * 0.6 + 0.05, 4, SUN_COLOR, "@#")
    moon_el = -env.sun_el * 0.6 + 0.05
    if env.night > 0.2 and moon_el > -0.05:
        _disc(screen, cam, sun_az + math.pi, moon_el, 3, MOON_COLOR, "@%")
    _mountains(screen, cam, env)
    _clouds_draw(screen, cam, env)
    _birds(screen, cam, env)


def _birds(screen, cam, env):
    """Three birds cross the day sky, flapping on a slow rhythm."""
    if env.daylight < 0.35 or cam.horizon < 8:
        return
    soft = pack_rgb(58, 66, 84)
    for i in range(3):
        az = (0.7 + i * 1.9 + env.t * (0.016 + i * 0.004)) % 6.28318
        rel = az - cam.yaw
        while rel > math.pi:
            rel -= 6.28318
        while rel < -math.pi:
            rel += 6.28318
        if abs(rel) > FOV * 0.55:
            continue
        el = 0.62 + 0.10 * math.sin(env.t * 0.2 + i * 1.7)
        col = int(screen.w * 0.5 +
                  math.tan(rel) / math.tan(FOV * 0.5) * screen.w * 0.5)
        row = int(cam.horizon - el * cam.fy)
        if 0 <= col < screen.w and 0 <= row < cam.horizon:
            flap = math.sin(env.t * 2.6 + i * 2.1)
            screen.set(col, row, "v" if flap > 0.0 else "^", soft, FAR)


def _mountains(screen, cam, env):
    """Three fogged ridge layers above the horizon, each with a broken edge."""
    ridges = _ridges()
    w = screen.w
    horizon = cam.horizon
    if horizon < 6:
        return
    layers = ((0.24, 0.16, " ."), (0.17, 0.24, " :"),
              (0.11, 0.34, ".:"))
    for li, (amp, dark, edge) in enumerate(layers):
        vals = ridges[li]
        base = _mix(env.horizon_col, RIDGE_COLOR, dark)
        body = _mix(base, RIDGE_COLOR, 0.35)
        shade = _mix(body, RIDGE_COLOR, 0.35)
        for x in range(w):
            az = cam.yaw + cam.col_angle[x] + math.pi
            idx = int((az % 6.28318) / 6.28318 * 767) & 767
            r = vals[idx]
            peak = int(r * horizon * amp)
            if peak < 1:
                continue
            top = horizon - peak
            prev = vals[(idx - 1) & 767]
            slope = r - prev
            for y in range(max(0, top), horizon):
                hsh = (x * 1103515245 + y * 12345) & 7
                if y == top:
                    if slope > 0.012 and hsh < 2:
                        ch = "/"
                    elif slope < -0.012 and hsh < 2:
                        ch = "\\"
                    elif hsh == 0:
                        ch = "^"
                    else:
                        continue
                    col = base
                elif hsh < 6:
                    ch = edge[1] if y < top + 3 else (
                        ":" if hsh < 4 else ("." if hsh < 5 else ";"))
                    col = body if ((x + y) & 3) else shade
                else:
                    continue
                screen.chars[y][x] = ch
                screen.fg[y][x] = col
                screen.depth[y][x] = FAR


def _disc(screen, cam, az, el, radius, color, chars_pair):
    w = screen.w
    rel = az - cam.yaw
    while rel > math.pi:
        rel -= 6.28318
    while rel < -math.pi:
        rel += 6.28318
    if abs(rel) > FOV * 0.75 or el < -0.1:
        return
    col = int(w * 0.5 + math.tan(rel) / math.tan(FOV * 0.5) * w * 0.5)
    row = int(cam.horizon - el * cam.fy)
    r2 = radius * radius
    for dy in range(-radius - 1, radius + 2):
        for dx in range(-radius - 1, radius + 2):
            d2 = dx * dx + dy * dy * 2.6
            px, py = col + dx, row + dy
            if 0 <= px < screen.w and 0 <= py < screen.h:
                if d2 <= r2 * 0.45:
                    screen.chars[py][px] = chars_pair[0]
                    screen.fg[py][px] = color
                elif d2 <= r2:
                    screen.chars[py][px] = chars_pair[1]
                    screen.fg[py][px] = color


def _clouds_draw(screen, cam, env):
    clouds = _clouds()
    w, h = screen.w, screen.h
    horizon = cam.horizon
    chars, fg = screen.chars, screen.fg
    drift = int(env.t * 1.4)
    ccol = _mix(CLOUD_NIGHT, CLOUD_DAY, env.daylight)
    top = max(0, horizon - int(horizon * 0.9))
    for y in range(top, max(top, horizon - 1)):
        ty = int((horizon - y) / max(1.0, horizon) * _CLOUD_H * 1.7)
        if ty >= _CLOUD_H:
            continue
        crow = clouds[ty]
        crow_chars = chars[y]
        frow = fg[y]
        for x in range(w):
            v = crow[(x + drift) & 255]
            if v > 0.50:
                d = (v - 0.50) * 3.6
                if ((x * 7 + y * 13) & 15) < d * 16:
                    if d < 0.35:
                        ch = "`"
                    elif d < 0.7:
                        ch = ","
                    elif d < 1.05:
                        ch = ":"
                    else:
                        ch = "~"
                    crow_chars[x] = ch
                    frow[x] = ccol


def _terrain(screen, ter, cam, env, wet=0.0, snow=0.0):
    w, h = screen.w, screen.h
    chars, fg, depth = screen.chars, screen.fg, screen.depth
    heights, colors, lights = ter.heights, ter.colors, ter.lights
    mats = getattr(ter, "materials", None)
    texs = getattr(ter, "texture", None)
    W = ter.W
    water = ter.water
    camx, camy, camz = cam.x, cam.y, cam.z
    yaw = cam.yaw
    horizon = cam.horizon
    fy = cam.fy
    col_angle = cam.col_angle
    t = env.t
    ar, ag, ab = env.ambient
    fogc = env.fog
    fgr = ((fogc >> 16) & 255) / 255.0
    fgg = ((fogc >> 8) & 255) / 255.0
    fgb = (fogc & 255) / 255.0
    fog_end = MAX_DIST * 0.96
    inv_fog = 1.0 / (fog_end - FOG_START)
    sin64 = _SIN64
    wdr, wdg, wdb = (WATER_DEEP >> 16) & 255, (WATER_DEEP >> 8) & 255, WATER_DEEP & 255
    wlr, wlg, wlb = (WATER_LIT >> 16) & 255, (WATER_LIT >> 8) & 255, WATER_LIT & 255
    water_hi = water + 0.03
    foam_hi = water + 0.55
    sun_az = SUN_AZ if env.daylight > 0.18 else SUN_AZ + math.pi
    for x in range(w):
        ang = yaw + col_angle[x]
        rel_sun = sun_az - ang
        while rel_sun > math.pi:
            rel_sun -= 6.28318
        while rel_sun < -math.pi:
            rel_sun += 6.28318
        glint = 1.0 - abs(rel_sun) / 0.26 if abs(rel_sun) < 0.26 else 0.0
        dx = math.sin(ang)
        dz = math.cos(ang)
        hidden = h
        z = 0.6
        step = 0.34
        stag = 0
        while z < MAX_DIST and hidden > 0:
            wx = camx + dx * z
            wz = camz + dz * z
            if 0.0 <= wx < W - 1.0 and 0.0 <= wz < W - 1.0:
                ix = int(wx)
                iz = int(wz)
                gh = heights[iz][ix]
            else:
                gh = water - 2.5
            dy = gh - camy
            py = int(horizon - dy / z * fy)
            if py < hidden:
                fog = z - FOG_START
                if fog <= 0.0:
                    fog = 0.0
                else:
                    fog *= inv_fog
                    if fog > 1.0:
                        fog = 1.0
                inv_f = 1.0 - fog
                sp = sin64[int(wx * 3.1 + wz * 1.7 + t * 5.0) & 63]
                sp2 = sin64[int(wz * 2.3 - wx * 1.4 + t * 2.6) & 63]
                if gh <= water_hi:
                    k = (sp + 1.0) * 0.5
                    r = (wdr + (wlr - wdr) * k) * inv_f + fgr * fog * 255.0
                    g = (wdg + (wlg - wdg) * k) * inv_f + fgg * fog * 255.0
                    b = (wdb + (wlb - wdb) * k) * inv_f + fgb * fog * 255.0
                    packed = pack_rgb(r, g, b)
                    if glint > 0.0 and ((int(wx * 7.0 + wz * 3.0 + t * 8.0)
                                         & 63) == 0):
                        light = SUN_COLOR if env.daylight > 0.18 else MOON_COLOR
                        packed = _mix(packed, light, 0.14 + 0.30 * glint)
                        chs = ("*", "^", "*", "^") if glint > 0.9 else (
                            "^", "~", "*", "~")
                    elif sp > 0.72 and sp2 > 0.1:
                        chs = ("^", "*", "~", "^")
                    elif sp > 0.34:
                        chs = ("~", "-", "=", " ")
                    elif sp > -0.18:
                        chs = ("-", "~", " ", ".")
                    else:
                        chs = (".", " ", "-", " ")
                else:
                    c = colors[iz][ix]
                    r = ((c >> 16) & 255) * ar * inv_f + fgr * fog * 255.0
                    g = ((c >> 8) & 255) * ag * inv_f + fgg * fog * 255.0
                    b = (c & 255) * ab * inv_f + fgb * fog * 255.0
                    packed = pack_rgb(r, g, b)
                    if gh <= foam_hi:
                        if sp > 0.15:
                            chs = ("~", "^", "~", "*")
                            packed = _mix(packed,
                                          pack_rgb(228, 240, 244), 0.38)
                        else:
                            chs = (",", ".", ",", " ")
                            packed = _mix(packed, WATER_DEEP, 0.18)
                    elif gh <= water + 1.25:
                        chs = (",", ".", "'", " ")
                        packed = _mix(packed, WATER_DEEP, 0.26)
                    else:
                        mat = mats[iz][ix] if mats is not None else 1
                        tv = texs[iz][ix] if texs is not None else 128
                        row = GROUND_TILES[mat][1 if tv >= 128 else 0]
                        hv = (int(wx) * 73856093) ^ (int(wz) * 19349663)
                        chs = (row[hv & 15], row[(hv >> 4) & 15],
                               row[(hv >> 8) & 15], row[(hv >> 12) & 15])
                        if z < 46.0:
                            clutter = (ix * 374761393 + iz * 668265263) & 127
                            if clutter < 2:
                                if mat in (M_GRASS, M_FOREST):
                                    chs = ('"',) * 4
                                    packed = _mix(packed,
                                                  pack_rgb(150, 196, 96), 0.45)
                                elif mat == M_DIRT:
                                    chs = ("o",) * 4
                                    packed = _mix(packed,
                                                  pack_rgb(150, 140, 126), 0.4)
                                elif mat == M_ROCK:
                                    chs = ("^",) * 4
                                    packed = _mix(packed,
                                                  pack_rgb(176, 176, 170), 0.35)
                                elif mat == M_SNOW:
                                    chs = ("*",) * 4
                                    packed = _mix(packed,
                                                  pack_rgb(250, 252, 255), 0.5)
                                else:
                                    chs = ("'",) * 4
                            elif clutter == 2 and mat in (M_GRASS, M_FOREST):
                                chs = ("*",) * 4
                                flower = (pack_rgb(236, 206, 92),
                                          pack_rgb(224, 128, 150),
                                          pack_rgb(200, 160, 228),
                                          pack_rgb(238, 238, 244))
                                packed = _mix(packed, flower[(hv >> 9) & 3], 0.7)
                        if snow:
                            packed = _mix(packed, pack_rgb(226, 236, 248),
                                          snow * 0.7)
                            if (hv & 31) == 0:
                                chs = ("*",) * 4
                        if wet:
                            packed = _mix(packed, pack_rgb(38, 48, 62),
                                          wet * 0.35)
                            if (hv & 127) == 0:
                                chs = ("~",) * 4
                                packed = _mix(packed, pack_rgb(150, 180, 210),
                                              0.35)
                crow0, crow1, crow2, crow3 = chs
                frow = fg
                seg = (int(wx) * 196613 ^ int(wz) * 30103) & 3
                for y in range(py, hidden):
                    depth[y][x] = z
                    m = (seg ^ y) & 3
                    if m == 0:
                        chars[y][x] = crow0
                    elif m == 1:
                        chars[y][x] = crow1
                    elif m == 2:
                        chars[y][x] = crow2
                    else:
                        chars[y][x] = crow3
                    frow[y][x] = packed
                hidden = py
                stag = 0
            else:
                stag += 1
                if stag > 55 and hidden <= horizon:
                    break
            z += step
            step *= 1.0135


def _light_pools(screen, world, cam, env):
    """Warm stippled pools under campfires and shrines, strongest at night."""
    if screen.w < 8 or screen.h < 8:
        return
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    night = 0.25 + 0.75 * max(0.0, env.night)
    for ent in world.entities:
        is_house = ent.model.startswith("house")
        if ent.model not in ("campfire", "shrine", "torch") and not is_house:
            continue
        lx, lz, ly = ent.x, ent.z, ent.ground_y
        if is_house:
            lx = ent.x + math.sin(ent.yaw) * 2.05
            lz = ent.z + math.cos(ent.yaw) * 2.05
            ly = world.terrain.height(lx, lz)
        dx = lx - cam.x
        dz = lz - cam.z
        depth = dx * sin_y + dz * cos_y
        if depth < 1.5 or depth > 46.0:
            continue
        side = dx * cos_y - dz * sin_y
        col = cam.w * 0.5 + side / depth * cam.f
        row = cam.horizon - (ly - cam.y) / depth * cam.fy
        if ent.model == "torch":
            radius = max(3, min(12, int(2.0 / depth * cam.f)))
        elif is_house:
            radius = max(2, min(9, int(1.5 / depth * cam.f)))
        else:
            radius = max(3, min(14, int(2.2 / depth * cam.f)))
        if col < -radius or col > screen.w + radius:
            continue
        col = int(col)
        row = int(row)
        for py in range(max(0, row - radius),
                        min(screen.h, row + radius + 1)):
            for px in range(max(0, col - radius),
                            min(screen.w, col + radius + 1)):
                if screen.depth[py][px] >= FAR:
                    continue
                ex = (px - col) / radius
                ey = (py - row) / max(1.0, radius * 0.5)
                d = ex * ex + ey * ey
                if d >= 1.0:
                    continue
                k = (1.0 - d) ** 1.8 * night
                if k <= 0.01:
                    continue
                if d > 0.28 and ((px * 11 + py * 7) & 15) > k * 14.0:
                    continue
                if d < 0.5 and ((px * 7 + py * 13) & 31) == 0:
                    screen.chars[py][px] = "`"
                if ent.model == "torch":
                    strength = 0.82
                elif is_house:
                    strength = 0.48
                else:
                    strength = 0.62
                screen.fg[py][px] = _mix(screen.fg[py][px], FIRE_COLOR,
                                         min(strength, k * 0.8))


def _entities(screen, world, cam, env):
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    half_tan = math.tan(FOV * 0.5)
    ar, ag, ab = env.ambient
    fogc = env.fog
    fgr = ((fogc >> 16) & 255) / 255.0
    fgg = ((fogc >> 8) & 255) / 255.0
    fgb = (fogc & 255) / 255.0
    fog_end = MAX_DIST * 0.96
    inv_fog = 1.0 / (fog_end - FOG_START)
    vis = []
    max_d2 = MAX_DIST * MAX_DIST
    near_clip = max(1.2, cam.dist * 0.6)
    candidates = list(world.entities)
    player = getattr(world, "player", None)
    if player is not None and player not in candidates:
        candidates.append(player)
    for ent in candidates:
        dx = ent.x - cam.x
        dz = ent.z - cam.z
        if dx * dx + dz * dz > max_d2:
            continue
        depth_z = dx * sin_y + dz * cos_y
        if depth_z < near_clip:
            continue
        side = dx * cos_y - dz * sin_y
        lim = depth_z * half_tan * 1.35 + 8.0
        if side < -lim or side > lim:
            continue
        vis.append((depth_z, side, ent))
    vis.sort(key=lambda e: -e[0])
    atlas = world.atlas
    for depth_z, side, ent in vis:
        rows = ent.height * ent.scale / depth_z * cam.fy
        gy = ent.ground_y + ent.y_off
        bottom = cam.horizon - (gy - cam.y) / depth_z * cam.fy
        if bottom < -2 or bottom - rows > cam.h + 2:
            continue
        col = cam.w * 0.5 + side / depth_z * cam.f
        fog = depth_z - FOG_START
        if fog <= 0.0:
            fog = 0.0
        else:
            fog *= inv_fog
            if fog > 1.0:
                fog = 1.0
        tr = ar * (1.0 - fog) + fgr * fog
        tg = ag * (1.0 - fog) + fgg * fog
        tb = ab * (1.0 - fog) + fgb * fog
        frame = atlas.yaw_frame(ent.yaw, cam.yaw)
        sprite = atlas.get(ent.model, ent.pose, frame)
        if sprite is None:
            continue
        if rows < 1.2:
            py = int(bottom)
            if 0 <= py < screen.h and 0 <= int(col) < screen.w:
                screen.set(int(col), py, "." if rows < 0.7 else ":", sprite.colors[0][0],
                           depth_z)
            continue
        flash = ent.flash_color if ent.flash > 0.0 else None
        ent_depth = depth_z - 0.02
        if rows > 2.5:
            foot = int(bottom)
            fx = int(col)
            wide = 1 if ent.height < 2.2 else 2
            for sx in range(-wide, wide + 1):
                px = fx + sx
                if not (0 <= px < screen.w):
                    continue
                for dy, half in ((0, wide), (1, max(0, wide - 1))):
                    if abs(sx) > half:
                        continue
                    py = foot + dy
                    if not (0 <= py < screen.h):
                        continue
                    gdepth = screen.depth[py][px]
                    if gdepth >= FAR or abs(gdepth - depth_z) > 4.0:
                        continue
                    edge = abs(sx) == half
                    if edge and ((px * 13 + py * 7) & 3) == 0:
                        continue
                    shade = _mix(screen.fg[py][px], pack_rgb(6, 8, 12),
                                 0.42 if not edge else 0.55)
                    screen.set(px, py, "." if not edge else ",",
                               shade, depth_z)
        if env.daylight > 0.25 and env.sun_el > 0.08:
            length = min(7.0, (ent.height * 0.5) /
                         max(0.18, env.sun_el))
            sdx = -math.sin(SUN_AZ)
            sdz = -math.cos(SUN_AZ)
            steps = 4
            for i in range(1, steps + 1):
                t = i / steps
                wx = ent.x + sdx * length * t
                wz = ent.z + sdz * length * t
                gy = world.terrain.height(wx, wz)
                dx = wx - cam.x
                dz = wz - cam.z
                sdepth = dx * sin_y + dz * cos_y
                if sdepth < depth_z + 0.3:
                    continue
                side = dx * cos_y - dz * sin_y
                px = int(cam.w * 0.5 + side / sdepth * cam.f)
                py = int(cam.horizon - (gy - cam.y) / sdepth * cam.fy)
                half = 1 if t < 0.55 else 0
                for off in range(-half, half + 1):
                    cx = px + off
                    if not (0 <= cx < screen.w and 0 <= py < screen.h):
                        continue
                    gd = screen.depth[py][cx]
                    if gd >= FAR or abs(gd - sdepth) > 4.0:
                        continue
                    shade = _mix(screen.fg[py][cx], pack_rgb(6, 8, 12),
                                 0.30 + 0.15 * t)
                    screen.set(cx, py, "." if off == 0 else ",",
                               shade, sdepth)
        screen.blit(sprite, col, bottom, rows, tint=(tr, tg, tb),
                    depth=ent_depth, flash=flash)
        if sprite.glow is not None and env.night > 0.12:
            screen.blit(sprite.glow, col, bottom, rows, tint=(1.0, 1.0, 0.9),
                        depth=depth_z, alpha=min(0.95, env.night * 1.1))


def _smoke(screen, world, cam, env):
    """Thin chimney smoke above village roofs, drifting with the wind."""
    if screen.w < 20 or screen.h < 12:
        return
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    base = _mix(pack_rgb(70, 76, 92), pack_rgb(188, 196, 210),
                max(0.0, env.daylight))
    for ent in world.entities:
        if not ent.model.startswith("house"):
            continue
        ox = 1.35 * math.cos(ent.yaw) - 0.35 * math.sin(ent.yaw)
        oz = 1.35 * math.sin(ent.yaw) + 0.35 * math.cos(ent.yaw)
        for i in range(3):
            age = (env.t * 0.20 + i / 3.0) % 1.0
            wx = ent.x + ox + age * 0.7 + math.sin(env.t * 0.6 + i * 2.0) * 0.12
            wz = ent.z + oz + age * 0.25
            wy = ent.ground_y + ent.height * 0.90 + 0.2 + age * 2.2
            dx = wx - cam.x
            dz = wz - cam.z
            depth = dx * sin_y + dz * cos_y
            if depth < 4.0 or depth > 70.0:
                continue
            side = dx * cos_y - dz * sin_y
            col = int(cam.w * 0.5 + side / depth * cam.f)
            row = int(cam.horizon - (wy - cam.y) / depth * cam.fy)
            if not (0 <= col < screen.w and 0 <= row < cam.horizon):
                continue
            if ((col * 7 + row * 13) & 7) < 2 + age * 3:
                ch = "," if age < 0.30 else ("'" if age < 0.65 else ".")
                fog = min(0.8, max(0.0, (depth - FOG_START) /
                                   (MAX_DIST * 0.96 - FOG_START)))
                screen.set(col, row, ch, _mix(base, env.fog, fog), depth)


def _fireflies(screen, world, cam, env):
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    t = env.t
    for i, (fx, fz, phase) in enumerate(world.fireflies):
        wx = fx + math.sin(t * 0.7 + phase) * 1.2
        wz = fz + math.cos(t * 0.5 + phase * 1.3) * 1.2
        wy = world.terrain.height(wx, wz) + 0.8 + math.sin(t * 1.3 + phase) * 0.4
        dx = wx - cam.x
        dz = wz - cam.z
        depth_z = dx * sin_y + dz * cos_y
        if depth_z < 0.8 or depth_z > 60.0:
            continue
        side = dx * cos_y - dz * sin_y
        col = int(cam.w * 0.5 + side / depth_z * cam.f)
        row = int(cam.horizon - (wy - cam.y) / depth_z * cam.fy)
        if 0 <= col < screen.w and 0 <= row < screen.h:
            blink = math.sin(t * 3.0 + phase * 7.0)
            if blink > 0.1:
                screen.set(col, row, "o" if blink > 0.7 else ".",
                           pack_rgb(200, 255, 130), depth_z)
