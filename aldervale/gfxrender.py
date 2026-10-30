"""Truecolor scene renderer: sky, raster terrain, 3D models, billboards, weather.

This is the graphics sibling of ``render.py``.  It reuses the same world clock,
camera parameters and heightfield, but writes an RGB frame instead of glyph
cells.  The column march fills vertical runs directly, which keeps pure-Python
terrain rendering inside the browser frame budget.  Nearby actors and props are
rasterised from their real meshes; distant ones use the baked pixel atlas.
"""

import math

from .buffer import FAR, pack_rgb
from .noise import rand01
from .render import (CLOUD_DAY, CLOUD_NIGHT, FOG_START, FOV, MAX_DIST,
                     MOON_COLOR, RIDGE_COLOR, STAR_COLOR, SUN_COLOR,
                     WATER_DEEP, WATER_LIT, _SIN64, _clouds, _mix, _ridges)
from .terrain import M_DIRT, M_FOREST, M_GRASS, M_ROCK, M_SAND, M_SNOW

GROUND_GAIN = 1.42
WATER_GAIN = 1.18
DETAIL_RADIUS = 13
MODEL3D_RANGE = 12.0
MAX_MODEL3D = 4
PROP3D_RANGE = 16.0
MAX_PROP3D = 2
PLAYER_DEPTH_BIAS = 1.6
PROP3D_MODELS = frozenset((
    "house0", "house1", "house2", "well", "cart", "fence", "shrine",
    "banner0", "banner1", "tree_oak", "tree_pine", "tree_birch",
    "tree_dead", "haystack", "anvil", "castle",
))


class GfxCamera:
    """Pixel projection derived from the cell camera, same view and alignment."""

    __slots__ = ("w", "h", "f", "fy", "horizon", "col_angle",
                 "x", "y", "z", "yaw", "pitch", "dist")

    def __init__(self, w, h, x, z, y, yaw, pitch, f, fy, horizon, col_angle,
                 dist=0.0):
        self.w, self.h = w, h
        self.x, self.z, self.y = x, z, y
        self.yaw, self.pitch = yaw, pitch
        self.f, self.fy = f, fy
        self.horizon = horizon
        self.col_angle = col_angle
        self.dist = dist

    @classmethod
    def from_camera(cls, cam, w, h):
        sx = w / float(cam.w)
        sy = h / float(cam.h)
        half_tan = math.tan(FOV * 0.5)
        col_angle = [math.atan((x - w * 0.5 + 0.5) / (w * 0.5) * half_tan)
                     for x in range(w)]
        horizon = int(round(cam.horizon * sy))
        horizon = max(3, min(h - 3, horizon))
        return cls(w, h, cam.x, cam.z, cam.y, cam.yaw, cam.pitch,
                   cam.f * sx, cam.fy * sy, horizon, col_angle,
                   getattr(cam, "dist", 0.0))


def render_scene(fb, world, cam, env, cell_w=None, cell_h=None, models=None):
    """Draw a complete pixel frame; return the cell-depth grid for picking."""
    fb.clear()
    weather = getattr(world, "weather", "clear")
    _sky(fb, cam, env)
    _terrain(fb, world.terrain, cam, env,
             wet=0.20 if weather == "rain" else 0.0,
             snow=0.22 if weather == "snow" else 0.0)
    _ground_details(fb, world, cam, env)
    _cast_shadows(fb, world, cam, env)
    _light_pools(fb, world, cam, env)
    _entities(fb, world, cam, env, models)
    _weather(fb, weather, env)
    if env.night > 0.15:
        _fireflies(fb, world, cam, env)
    _hurt_vignette(fb, world)
    return _cell_depth(fb, cam, cell_w or cam.w, cell_h or cam.h)


def _cell_depth(fb, cam, cw, ch):
    rows = []
    sx = fb.w / float(cw)
    sy = fb.h / float(ch)
    for cy in range(ch):
        py = min(fb.h - 1, int((cy + 0.5) * sy))
        row = []
        for cx in range(cw):
            px = min(fb.w - 1, int((cx + 0.5) * sx))
            row.append(fb.sample_depth(px, py))
        rows.append(row)
    return rows


def _sky(fb, cam, env):
    w, h = fb.w, fb.h
    horizon = cam.horizon
    zr, zg, zb = (env.zenith >> 16) & 255, (env.zenith >> 8) & 255, env.zenith & 255
    hr, hg, hb = (env.horizon_col >> 16) & 255, (env.horizon_col >> 8) & 255, \
        env.horizon_col & 255
    fr, fg, fb_ = (env.fog >> 16) & 255, (env.fog >> 8) & 255, env.fog & 255
    column = bytearray(h * 3)
    for y in range(h):
        o = y * 3
        if y < horizon:
            t = y / max(1.0, horizon)
            t2 = t * t * (3.0 - 2.0 * t)
            column[o] = int(zr + (hr - zr) * t2)
            column[o + 1] = int(zg + (hg - zg) * t2)
            column[o + 2] = int(zb + (hb - zb) * t2)
        else:
            column[o], column[o + 1], column[o + 2] = fr, fg, fb_
    pattern = bytes(column)
    stride = h * 3
    data = fb.data
    for x in range(w):
        o = x * stride
        data[o:o + stride] = pattern

    if env.night > 0.05:
        for i in range(120):
            if rand01(i, 3, 42) > env.night:
                continue
            az = rand01(i, 1, 42) * 6.28318
            el = 0.06 + rand01(i, 2, 42) * 0.85
            rel = az - cam.yaw
            rel = (rel + math.pi) % 6.28318 - math.pi
            if abs(rel) > FOV * 0.62:
                continue
            px = int(w * 0.5 + math.tan(rel) / math.tan(FOV * 0.5) * w * 0.5)
            py = int(horizon - el * cam.fy * 0.85)
            if 0 <= px < w and 0 <= py < horizon:
                fb.set(px, py, STAR_COLOR)
                if rand01(i, 4, 42) > 0.8:
                    fb.set(px, py, _mix(STAR_COLOR, 0xFFFFFF, 0.4))

    _disc(fb, cam, 2.35, env.sun_el * 0.6 + 0.05, max(3, w // 48), SUN_COLOR)
    if env.night > 0.2:
        _disc(fb, cam, 2.35 + math.pi, -env.sun_el * 0.6 + 0.05,
              max(2, w // 60), MOON_COLOR)
    _mountains(fb, cam, env)
    _clouds_draw(fb, cam, env)
    _birds(fb, cam, env)


def _disc(fb, cam, az, el, radius, color):
    rel = az - cam.yaw
    rel = (rel + math.pi) % 6.28318 - math.pi
    if abs(rel) > FOV * 0.8 or el < -0.12:
        return
    cx = int(fb.w * 0.5 + math.tan(rel) / math.tan(FOV * 0.5) * fb.w * 0.5)
    cy = int(cam.horizon - el * cam.fy)
    r2 = radius * radius
    for dy in range(-radius - 2, radius + 3):
        span = int(math.sqrt(max(0.0, r2 - dy * dy)))
        for spread, alpha in ((2, 0.18), (0, 1.0)):
            half = span + spread
            if half <= 0:
                continue
            y = cy + dy
            if not (0 <= y < cam.horizon):
                continue
            if alpha >= 1.0:
                for x in range(max(0, cx - half), min(fb.w, cx + half + 1)):
                    fb.set(x, y, color)
            else:
                for x in range(max(0, cx - half), min(fb.w, cx + half + 1)):
                    fb.blend(x, y, color, alpha)


def _mountains(fb, cam, env):
    ridges = _ridges()
    horizon = cam.horizon
    if horizon < 6:
        return
    layers = ((0.24, 0.16, 0.10), (0.17, 0.24, 0.20), (0.11, 0.34, 0.34))
    for li, (amp, dark, rim) in enumerate(layers):
        vals = ridges[li]
        base = _mix(env.horizon_col, RIDGE_COLOR, dark)
        body = _mix(base, RIDGE_COLOR, 0.35)
        top_col = _mix(body, 0xFFFFFF, rim * 0.30)
        for x in range(fb.w):
            az = cam.yaw + cam.col_angle[x] + math.pi
            idx = int((az % 6.28318) / 6.28318 * 767) & 767
            r = vals[idx]
            peak = int(r * horizon * amp)
            if peak < 1:
                continue
            top = max(0, horizon - peak)
            fb.fill_column(x, top, horizon, body)
            if top < horizon:
                fb.set(x, top, top_col)


def _clouds_draw(fb, cam, env):
    clouds = _clouds()
    horizon = cam.horizon
    ccol = _mix(CLOUD_NIGHT, CLOUD_DAY, env.daylight)
    drift = int(env.t * 1.4)
    top = max(0, horizon - int(horizon * 0.88))
    if top >= horizon:
        return
    # Cheap wisps: one sampled band every few rows, two pixels wide.  A full
    # per-pixel cloud pass costs more than the terrain march in pure Python.
    for band in range(10):
        y = top + (horizon - top) * band // 10
        ty = int((horizon - y) / max(1.0, horizon) * 26 * 1.7)
        if ty >= 26:
            continue
        crow = clouds[ty]
        for x in range(0, fb.w, 3):
            v = crow[(x + drift) & 255]
            if v > 0.60:
                alpha = min(0.75, (v - 0.60) * 2.4)
                fb.blend(x, y, ccol, alpha)
                if x + 1 < fb.w:
                    fb.blend(x + 1, y, ccol, alpha * 0.65)
                if band & 1 and y + 1 < horizon:
                    fb.blend(x, y + 1, ccol, alpha * 0.45)


def _birds(fb, cam, env):
    if env.daylight < 0.35 or cam.horizon < 8:
        return
    soft = pack_rgb(58, 66, 84)
    for i in range(3):
        az = (0.7 + i * 1.9 + env.t * (0.016 + i * 0.004)) % 6.28318
        rel = (az - cam.yaw + math.pi) % 6.28318 - math.pi
        if abs(rel) > FOV * 0.55:
            continue
        el = 0.62 + 0.10 * math.sin(env.t * 0.2 + i * 1.7)
        col = int(fb.w * 0.5 + math.tan(rel) / math.tan(FOV * 0.5) * fb.w * 0.5)
        row = int(cam.horizon - el * cam.fy)
        if not (0 <= col < fb.w and 0 <= row < cam.horizon):
            continue
        flap = math.sin(env.t * 2.6 + i * 2.1)
        if flap > 0.0:
            fb.set(col - 1, row + 1, soft)
            fb.set(col, row, soft)
            fb.set(col + 1, row + 1, soft)
        else:
            fb.set(col - 1, row, soft)
            fb.set(col, row + 1, soft)
            fb.set(col + 1, row, soft)


def _ground_palette(ter):
    """Cache the static material/light/texture gain per heightfield cell."""
    pal = getattr(ter, "gfx_colors", None)
    if pal is not None:
        return pal
    W = ter.W
    colors, lights = ter.colors, ter.lights
    mats = getattr(ter, "materials", None)
    texs = getattr(ter, "texture", None)
    pal = []
    for iz in range(W):
        row = []
        crow = colors[iz]
        lrow = lights[iz]
        mrow = mats[iz] if mats is not None else None
        trow = texs[iz] if texs is not None else None
        for ix in range(W):
            c = crow[ix]
            light = lrow[ix] / 255.0
            mat = mrow[ix] if mrow is not None else M_GRASS
            tv = trow[ix] if trow is not None else 128
            gain = GROUND_GAIN * (0.86 + 0.28 * light)
            if mat in (M_GRASS, M_FOREST):
                if tv > 190:
                    gain *= 1.10
                elif tv < 64:
                    gain *= 0.93
            elif mat == M_DIRT or mat == M_SAND:
                gain *= 0.98 + (tv / 255.0) * 0.10
            elif mat == M_ROCK:
                gain *= 0.92 + (tv / 255.0) * 0.14
            elif mat == M_SNOW:
                gain *= 1.05
            # Per-cell grain breaks the flat slabs the column march produces.
            jitter = (((ix * 374761393) ^ (iz * 668265263)) & 31) / 31.0 - 0.5
            gain *= 1.0 + jitter * 0.18
            row.append(pack_rgb(((c >> 16) & 255) * gain,
                                ((c >> 8) & 255) * gain,
                                (c & 255) * gain))
        pal.append(row)
    ter.gfx_colors = pal
    return pal


def _fill_run(fb, x, y0, y1, color, depth):
    """Fill a terrain run, adding a soft vertical grain when it is large."""
    if y1 - y0 < 30:
        fb.fill_column(x, y0, y1, color, depth)
        return
    r = (color >> 16) & 255
    g = (color >> 8) & 255
    b = color & 255
    hi = pack_rgb(min(255, r * 1.012), min(255, g * 1.012),
                  min(255, b * 1.012))
    lo = pack_rgb(min(255, r * 0.988), min(255, g * 0.988),
                  min(255, b * 0.988))
    base = bytes((r, g, b))
    high = bytes(((hi >> 16) & 255, (hi >> 8) & 255, hi & 255))
    low = bytes(((lo >> 16) & 255, (lo >> 8) & 255, lo & 255))
    rows = (base, high, base, base, low, base, high, base,
            base, low, base, base, high, base, low, base)
    strip = b"".join(rows)
    phase = (x * 2654435761 + int(depth * 97)) & 15
    fb.fill_column_pattern(x, y0, y1, strip, depth, phase=phase)


def _terrain(fb, ter, cam, env, wet=0.0, snow=0.0):
    w, h = fb.w, fb.h
    heights = ter.heights
    palette = _ground_palette(ter)
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
    hor = env.horizon_col
    hr = (hor >> 16) & 255
    hg = (hor >> 8) & 255
    hb = hor & 255
    fog_end = MAX_DIST * 0.96
    inv_fog = 1.0 / (fog_end - FOG_START)
    sin64 = _SIN64
    wdr, wdg, wdb = (WATER_DEEP >> 16) & 255, (WATER_DEEP >> 8) & 255, \
        WATER_DEEP & 255
    wlr, wlg, wlb = (WATER_LIT >> 16) & 255, (WATER_LIT >> 8) & 255, \
        WATER_LIT & 255
    water_hi = water + 0.03
    foam_hi = water + 0.55
    sun_az = 2.35 if env.daylight > 0.18 else 2.35 + math.pi
    water_k = 0.28 + 0.72 * env.daylight
    for x in range(w):
        ang = yaw + col_angle[x]
        rel_sun = sun_az - ang
        rel_sun = (rel_sun + math.pi) % 6.28318 - math.pi
        glint = 1.0 - abs(rel_sun) / 0.26 if abs(rel_sun) < 0.26 else 0.0
        dx = math.sin(ang)
        dz = math.cos(ang)
        hidden = h
        z = 0.6
        stag = 0
        run_top = None
        run_bottom = h
        run_col = 0
        run_z = 0.0
        while z < MAX_DIST and hidden > 0:
            wx = camx + dx * z
            wz = camz + dz * z
            if 0.0 <= wx < W - 1.0 and 0.0 <= wz < W - 1.0:
                ix = int(wx)
                iz = int(wz)
                gh = heights[iz][ix]
            else:
                ix = iz = -1
                gh = water - 2.5
            py = int(horizon - (gh - camy) / z * fy)
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
                if gh <= water_hi:
                    sp2 = sin64[int(wz * 2.3 - wx * 1.4 + t * 2.6) & 63]
                    k = (sp + 1.0) * 0.5
                    r = (wdr + (wlr - wdr) * k) * WATER_GAIN * water_k * inv_f + \
                        fgr * fog * 255.0
                    g = (wdg + (wlg - wdg) * k) * WATER_GAIN * water_k * inv_f + \
                        fgg * fog * 255.0
                    b = (wdb + (wlb - wdb) * k) * WATER_GAIN * water_k * inv_f + \
                        fgb * fog * 255.0
                    refl = 0.14 + 0.38 * (1.0 - inv_f)
                    r = r * (1.0 - refl) + hr * refl
                    g = g * (1.0 - refl) + hg * refl
                    b = b * (1.0 - refl) + hb * refl
                    if glint > 0.0 and ((int(wx * 7.0 + wz * 3.0 + t * 8.0) & 63) == 0):
                        r += 22.0 * glint
                        g += 20.0 * glint
                        b += 14.0 * glint
                    if sp2 > 0.55 and sp > 0.2:
                        r += 10.0
                        g += 10.0
                        b += 8.0
                else:
                    c = palette[iz][ix]
                    r = ((c >> 16) & 255) * ar * inv_f + fgr * fog * 255.0
                    g = ((c >> 8) & 255) * ag * inv_f + fgg * fog * 255.0
                    b = (c & 255) * ab * inv_f + fgb * fog * 255.0
                    if gh <= foam_hi:
                        if sp > 0.15:
                            r = r * 0.62 + 228 * 0.38
                            g = g * 0.62 + 240 * 0.38
                            b = b * 0.62 + 244 * 0.38
                        else:
                            r *= 0.82
                            g *= 0.82
                            b *= 0.82
                    if snow:
                        k2 = snow * 0.55
                        r = r * (1.0 - k2) + 226 * k2
                        g = g * (1.0 - k2) + 236 * k2
                        b = b * (1.0 - k2) + 248 * k2
                    if wet:
                        k2 = wet * 0.35
                        r = r * (1.0 - k2) + 38 * k2
                        g = g * (1.0 - k2) + 48 * k2
                        b = b * (1.0 - k2) + 62 * k2
                packed = pack_rgb(r, g, b)
                if py < 0:
                    py = 0
                if py < hidden:
                    if run_top is None:
                        run_col = packed
                        run_top = py
                        run_bottom = hidden
                        run_z = z
                    else:
                        dr = ((packed >> 16) & 255) - ((run_col >> 16) & 255)
                        dg = ((packed >> 8) & 255) - ((run_col >> 8) & 255)
                        db = (packed & 255) - (run_col & 255)
                        if abs(dr) + abs(dg) + abs(db) <= 24:
                            run_top = py
                            run_z = z
                        else:
                            if run_top < run_bottom:
                                _fill_run(fb, x, run_top, run_bottom,
                                          run_col, run_z)
                            run_col = packed
                            run_top = py
                            run_bottom = hidden
                            run_z = z
                hidden = py
                stag = 0
            else:
                stag += 1
                if stag > 24 and hidden <= horizon:
                    break
            z += max(0.65, z * 0.07)
        if run_top is not None and run_top < run_bottom:
            _fill_run(fb, x, run_top, run_bottom, run_col, run_z)


def _ground_details(fb, world, cam, env):
    ter = world.terrain
    W = ter.W
    cx0 = int(cam.x) - DETAIL_RADIUS
    cz0 = int(cam.z) - DETAIL_RADIUS
    seed = getattr(world, "seed", 7)
    cols = (pack_rgb(236, 206, 92), pack_rgb(224, 128, 150),
            pack_rgb(200, 160, 228), pack_rgb(238, 238, 244),
            pack_rgb(120, 178, 82))
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    for iz in range(cz0, cz0 + DETAIL_RADIUS * 2 + 1):
        if iz < 1 or iz >= W - 1:
            continue
        for ix in range(cx0, cx0 + DETAIL_RADIUS * 2 + 1):
            if ix < 1 or ix >= W - 1:
                continue
            r = rand01(ix, iz, seed + 313)
            if r > 0.46:
                continue
            mat = ter.materials[iz][ix]
            if mat == M_SNOW:
                continue
            wx = ix + 0.5
            wz = iz + 0.5
            wy = ter.height(wx, wz) + 0.06
            ddx = wx - cam.x
            ddz = wz - cam.z
            depth = ddx * sin_y + ddz * cos_y
            if depth < 1.5 or depth > 34.0:
                continue
            side = ddx * cos_y - ddz * sin_y
            px = int(cam.w * 0.5 + side / depth * cam.f)
            py = int(cam.horizon - (wy - cam.y) / depth * cam.fy)
            if not (0 <= px < fb.w and 0 <= py < fb.h):
                continue
            if abs(fb.sample_depth(px, py) - depth) > 3.0:
                continue
            if mat in (M_GRASS, M_FOREST):
                if r < 0.10:
                    col = cols[int(rand01(ix, iz, seed + 611) * 4)]
                    fb.set(px, py, col, depth - 0.1)
                    if r < 0.025 and px + 1 < fb.w:
                        fb.set(px + 1, py, col, depth - 0.1)
                else:
                    col = cols[4] if (ix + iz) & 1 else pack_rgb(88, 132, 58)
                    fb.set(px, py, col, depth - 0.1)
                    if depth < 13.0:
                        if py > 0:
                            fb.set(px, py - 1, pack_rgb(104, 150, 66),
                                   depth - 0.1)
                        if py > 1 and (ix * 7 + iz * 3) & 1:
                            fb.set(px, py - 2, pack_rgb(116, 164, 72),
                                   depth - 0.1)
            elif mat == M_DIRT:
                col = pack_rgb(142, 122, 96) if (ix + iz) & 1 else \
                    pack_rgb(120, 100, 78)
                fb.set(px, py, col, depth - 0.1)
                if px + 1 < fb.w and r < 0.16:
                    fb.set(px + 1, py, pack_rgb(164, 144, 112), depth - 0.1)
            elif mat == M_ROCK:
                fb.set(px, py, pack_rgb(164, 164, 158), depth - 0.1)
                if py > 0 and r < 0.20:
                    fb.set(px, py - 1, pack_rgb(186, 186, 178), depth - 0.1)
            elif mat == M_SAND:
                fb.set(px, py, pack_rgb(214, 198, 152), depth - 0.1)


def _cast_shadows(fb, world, cam, env):
    """Soft sun shadows stretched away from the sun, clipped to terrain."""
    if env.daylight < 0.25 or env.sun_el <= 0.04:
        return
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    sdx = -math.sin(2.35)
    sdz = -math.cos(2.35)
    strength = 0.12 + 0.10 * env.daylight
    candidates = list(world.entities)
    player = getattr(world, "player", None)
    if player is not None:
        candidates.append(player)
    water = world.terrain.water
    for ent in candidates:
        if ent.height < 0.35:
            continue
        dx = ent.x - cam.x
        dz = ent.z - cam.z
        depth = dx * sin_y + dz * cos_y
        if depth < 2.5 or depth > 30.0:
            continue
        length = min(8.0, ent.height * 0.60 / max(0.22, env.sun_el))
        if length < 0.3:
            continue
        for i in range(4):
            t = i / 3.0
            wx = ent.x + sdx * length * t
            wz = ent.z + sdz * length * t
            gy = world.terrain.height(wx, wz)
            if gy <= water + 0.08:
                continue
            ddx = wx - cam.x
            ddz = wz - cam.z
            sdepth = ddx * sin_y + ddz * cos_y
            if sdepth < 1.5:
                continue
            side = ddx * cos_y - ddz * sin_y
            px = int(cam.w * 0.5 + side / sdepth * cam.f)
            py = int(cam.horizon - (gy + 0.04 - cam.y) / sdepth * cam.fy)
            if not (0 <= px < fb.w and 0 <= py < fb.h):
                continue
            if abs(fb.sample_depth(px, py) - sdepth) > 2.5:
                continue
            radius = max(1, min(7, int(ent.radius * (0.8 + 0.2 * (1.0 - t))
                                    / sdepth * cam.f)))
            alpha = strength * (0.55 + 0.45 * (1.0 - t))
            for oy in range(-radius, radius + 1):
                yy = py + oy
                if yy < 0 or yy >= fb.h:
                    continue
                span = int(math.sqrt(max(0.0, radius * radius - oy * oy)))
                for ox in range(-span, span + 1):
                    xx = px + ox
                    if 0 <= xx < fb.w:
                        fb.blend(xx, yy, 0x05070B, alpha)


def _light_pools(fb, world, cam, env):
    if fb.w < 8 or fb.h < 8:
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
            radius = max(3, min(20, int(2.0 / depth * cam.f)))
        elif is_house:
            radius = max(2, min(14, int(1.5 / depth * cam.f)))
        else:
            radius = max(3, min(24, int(2.2 / depth * cam.f)))
        if col < -radius or col > fb.w + radius:
            continue
        col = int(col)
        row = int(row)
        strength = 0.82 if ent.model == "torch" else (
            0.48 if is_house else 0.62)
        for py in range(max(0, row - radius), min(fb.h, row + radius + 1)):
            for px in range(max(0, col - radius), min(fb.w, col + radius + 1)):
                d2 = ((px - col) / radius) ** 2 + \
                    ((py - row) / max(1.0, radius * 0.55)) ** 2
                if d2 >= 1.0:
                    continue
                gd = fb.sample_depth(px, py)
                if gd >= FAR or abs(gd - depth) > 6.0:
                    continue
                k = (1.0 - d2) ** 1.8 * night * 0.55
                if k <= 0.01:
                    continue
                fb.add(px, py, 0xFFBA60, min(strength, k))


def _entities(fb, world, cam, env, models=None):
    atlas = world.atlas
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
    near_clip = max(1.2, cam.dist * 0.5)
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
    model3d = set()
    if models is not None:
        near = [(d, e) for d, _side, e in vis
                if hasattr(e, "kind") and d <= MODEL3D_RANGE]
        near.sort(key=lambda pair: pair[0])
        chosen = []
        if player is not None:
            for depth_pair in near:
                if depth_pair[1] is player:
                    chosen.append(player)
                    break
        for _d, ent in near:
            if len(chosen) >= MAX_MODEL3D:
                break
            if ent not in chosen:
                chosen.append(ent)
        props = [(d, e) for d, _side, e in vis
                 if not hasattr(e, "kind") and e.model in PROP3D_MODELS
                 and d <= PROP3D_RANGE]
        props.sort(key=lambda pair: pair[0])
        for _d, ent in props[:MAX_PROP3D]:
            chosen.append(ent)
        model3d = {id(e) for e in chosen}
    for depth_z, side, ent in vis:
        sprite = _sprite_for(atlas, ent, cam)
        use3d = models is not None and id(ent) in model3d
        is_actor = hasattr(ent, "kind")
        if sprite is None and not use3d:
            continue
        rows = ent.height * ent.scale / depth_z * cam.f
        gy = ent.ground_y + ent.y_off
        bottom = cam.horizon - (gy - cam.y) / depth_z * cam.fy
        if bottom < -2 or bottom - rows > fb.h + 2:
            continue
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
        col = cam.w * 0.5 + side / depth_z * cam.f
        _contact_shadow(fb, cam, ent, col, bottom, depth_z, rows)
        if use3d and models.draw(fb, cam, ent, tr, tg, tb,
                                 ent.flash, ent.flash_color,
                                 outline=is_actor,
                                 depth_bias=PLAYER_DEPTH_BIAS
                                 if ent is player else 0.0):
            continue
        if sprite is None:
            continue
        if rows < 1.5:
            _dot(fb, col, bottom, sprite, tr, tg, tb, depth_z)
            continue
        _blit_sprite(fb, sprite, col, bottom, rows, tr, tg, tb, depth_z,
                     ent.flash, ent.flash_color)
        if sprite.glow is not None and env.night > 0.12:
            _blit_sprite(fb, sprite.glow, col, bottom, rows, 1.0, 1.0, 1.0,
                         depth_z, 0.0, None, additive=min(0.85, env.night))


def _sprite_for(atlas, ent, cam):
    try:
        steps = atlas.steps_for(ent.model, ent.pose)
        frame = atlas.yaw_frame(ent.yaw, cam.yaw, steps)
        return atlas.get(ent.model, ent.pose, frame)
    except AttributeError:
        return None


def _dot(fb, col, bottom, sprite, tr, tg, tb, depth_z):
    px = int(col)
    py = int(bottom)
    if not (0 <= px < fb.w and 0 <= py < fb.h):
        return
    o = 0
    while o + 3 < len(sprite.rgba) and sprite.rgba[o + 3] == 0:
        o += 4
    if o + 3 >= len(sprite.rgba):
        return
    color = pack_rgb(sprite.rgba[o] * tr, sprite.rgba[o + 1] * tg,
                     sprite.rgba[o + 2] * tb)
    fb.set(px, py, color, depth_z - 0.05)


def _contact_shadow(fb, cam, ent, col, bottom, depth_z, rows):
    radius = max(1.0, min(14.0, getattr(ent, "radius", 0.5) /
                          max(0.5, depth_z) * cam.f * 1.2))
    ry = max(1.0, radius * 0.35)
    cx = int(col)
    cy = int(bottom - 1)
    for dy in range(-int(ry), int(ry) + 1):
        py = cy + dy
        if not (0 <= py < fb.h):
            continue
        half = int(radius * math.sqrt(max(0.0, 1.0 - (dy / ry) ** 2)))
        for dx in range(-half, half + 1):
            px = cx + dx
            if not (0 <= px < fb.w):
                continue
            gd = fb.sample_depth(px, py)
            if gd >= FAR or abs(gd - depth_z) > 2.5:
                continue
            fb.blend(px, py, 0x06080C, 0.38)


def _blit_sprite(fb, sprite, col, bottom, rows, tr, tg, tb, depth_z,
                 flash=0.0, flash_color=None, additive=0.0):
    target_rows = int(rows)
    if target_rows < 1:
        return
    target_cols = int(target_rows * sprite.w / float(sprite.h))
    if target_cols < 1:
        return
    max_rows = min(fb.h, target_rows)
    max_cols = min(fb.w, target_cols)
    x0 = int(col - target_cols * 0.5)
    y0 = int(bottom - target_rows)
    lr = [min(255, int(v * tr + 0.5)) for v in range(256)]
    lg = [min(255, int(v * tg + 0.5)) for v in range(256)]
    lb = [min(255, int(v * tb + 0.5)) for v in range(256)]
    sx_map = [int(tx * sprite.w / target_cols) for tx in range(target_cols)]
    stride = fb.h * 3
    data = fb.data
    depth = fb.depth
    rgba = sprite.rgba
    sw4 = sprite.w * 4
    flash = max(0.0, min(1.0, flash))
    fr = fg_ = fb_ = 0
    if flash > 0.0 and flash_color is not None:
        fr = (flash_color >> 16) & 255
        fg_ = (flash_color >> 8) & 255
        fb_ = flash_color & 255
    for ty in range(max_rows):
        sy = int(ty * sprite.h / target_rows)
        py = y0 + ty
        if py < 0 or py >= fb.h:
            continue
        srow = sy * sw4
        for tx in range(max_cols):
            px = x0 + tx
            if px < 0 or px >= fb.w:
                continue
            o = (py + px * fb.h)
            if additive > 0.0:
                if depth[o] < depth_z - 0.2:
                    continue
            elif depth[o] <= depth_z:
                continue
            so = srow + sx_map[tx] * 4
            if rgba[so + 3] == 0:
                continue
            r = lr[rgba[so]]
            g = lg[rgba[so + 1]]
            b = lb[rgba[so + 2]]
            if flash > 0.0:
                r += (fr - r) * flash
                g += (fg_ - g) * flash
                b += (fb_ - b) * flash
            q = px * stride + py * 3
            if additive > 0.0:
                data[q] = min(255, data[q] + int(r * additive))
                data[q + 1] = min(255, data[q + 1] + int(g * additive))
                data[q + 2] = min(255, data[q + 2] + int(b * additive))
            else:
                data[q] = int(r)
                data[q + 1] = int(g)
                data[q + 2] = int(b)
                depth[o] = depth_z - 0.05


def _weather(fb, weather, env):
    if weather not in ("rain", "snow"):
        return
    w, h = fb.w, fb.h
    t = env.t
    if weather == "rain":
        color = pack_rgb(146, 176, 212)
        drops = max(14, (w * h) // 300)
        for i in range(drops):
            x = int(rand01(i, 7, 31) * w + t * 26.0 + i * 3) % w
            y = int(rand01(i, 11, 37) * h + t * 62.0 + i * 5) % h
            for k in range(3):
                py = y + k
                px = x + (k >> 1)
                if 0 <= px < w and 0 <= py < h:
                    fb.blend(px, py, color, 0.55 - k * 0.12)
    else:
        color = pack_rgb(226, 236, 248)
        flakes = max(16, (w * h) // 360)
        for i in range(flakes):
            x = int(rand01(i, 5, 41) * w +
                    math.sin(t * 0.8 + i) * 2.2 + i * 1.7) % w
            y = int(rand01(i, 9, 43) * h + t * 7.0 + i * 2.3) % h
            fb.blend(x, y, color, 0.85)
            if i % 9 == 0 and x + 1 < w:
                fb.blend(x + 1, y, color, 0.55)


def _fireflies(fb, world, cam, env):
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    t = env.t
    for i, (fx, fz, phase) in enumerate(world.fireflies):
        wx = fx + math.sin(t * 0.7 + phase) * 1.2
        wz = fz + math.cos(t * 0.5 + phase * 1.3) * 1.2
        wy = world.terrain.height(wx, wz) + 0.8 + \
            math.sin(t * 1.3 + phase) * 0.4
        dx = wx - cam.x
        dz = wz - cam.z
        depth = dx * sin_y + dz * cos_y
        if depth < 0.8 or depth > 60.0:
            continue
        side = dx * cos_y - dz * sin_y
        px = int(cam.w * 0.5 + side / depth * cam.f)
        py = int(cam.horizon - (wy - cam.y) / depth * cam.fy)
        if 0 <= px < fb.w and 0 <= py < fb.h:
            blink = math.sin(t * 3.0 + phase * 7.0)
            if blink > 0.1:
                fb.add(px, py, 0xC8FF82, 0.7 * blink)


def _hurt_vignette(fb, world):
    hurt = getattr(world.player, "hurt_t", 0.0)
    if hurt <= 0.0:
        return
    k = min(1.0, hurt / 0.4)
    edge = 3 + int(7 * k)
    w, h = fb.w, fb.h
    for y in range(h):
        for x in range(edge):
            for px in (x, w - 1 - x):
                if not (0 <= px < w):
                    continue
                a = 0.45 * k * (1.0 - x / float(edge))
                if a > 0.02:
                    fb.blend(px, y, 0xE03030, a)
