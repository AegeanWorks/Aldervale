"""Pixel sprite atlas and source-mesh cache.

The terminal atlas bakes glyph cells; this atlas bakes square-pixel RGBA
billboards for the graphics build and keeps the meshes beside them so the
runtime 3D renderer can draw the nearest actors and props as real geometry.
"""

import inspect
import math

from . import math3d as m3
from .atlas import MODEL_SPECS
from .buffer import pack_rgb
from .gfx import PixelSprite
from .mesh import (AMBIENT, HALF_VEC, LIGHT_DIR, SHADOW_TINT,
                   _smooth_normals)

# Square-pixel bake: one world metre is one metre on both axes.  Billboards
# and runtime 3D models therefore share the same proportions.
ASPECT = 1.0
YAW_STEPS = 16
INF = float("inf")

# Desired source height in pixels.  Near figures need enough pixels to survive
# the upscale from the 288x162 internal canvas.
_TARGET_HEIGHT = {
    "knight": 88, "guard": 90, "wolf": 50, "skeleton": 88, "captain": 112,
    "bandit": 86, "elder": 84, "smith": 82,
    "peasant0": 80, "peasant1": 80, "peasant2": 80,
    "chicken": 26, "wyvern": 76,
    "tree_oak": 96, "tree_pine": 90, "tree_birch": 82, "tree_dead": 66,
    "bush": 36, "rock_s": 26, "rock_b": 44,
    "house0": 84, "house1": 84, "house2": 78,
    "well": 58, "fence": 36, "cart": 42, "anvil": 28, "haystack": 48,
    "campfire": 26, "torch": 62,
    "chest_c": 32, "chest_o": 32, "shrine": 54,
    "banner0": 58, "banner1": 58,
    "gold": 16, "potion": 20, "pelt": 14, "bone": 16, "amulet": 22,
    "castle": 120,
}

# Static props rotate less finely; a house or castle is viewed from afar.
_YAW_STEPS = {
    "castle": 4, "house0": 8, "house1": 8, "house2": 8,
    "tree_oak": 8, "tree_pine": 8, "tree_birch": 8, "tree_dead": 8,
    "well": 8, "fence": 8, "cart": 8, "haystack": 8, "bush": 8,
    "rock_s": 8, "rock_b": 8, "shrine": 8, "banner0": 8, "banner1": 8,
    "campfire": 8, "torch": 8, "gold": 8, "potion": 8, "pelt": 8,
    "bone": 8, "amulet": 8, "chest_c": 8, "chest_o": 8,
}


def _yaw_steps(key):
    return _YAW_STEPS.get(key, 12)



class PixelAtlas:
    """Baked pixel frames: (model_key, pose_name) -> [PixelSprite]."""

    def __init__(self, yaw_steps=YAW_STEPS):
        self.yaw_steps = yaw_steps
        self.frames = {}
        self.meshes = {}
        self.heights = {}
        for key, spec in MODEL_SPECS.items():
            self.heights[key] = spec["height"]

    def build(self, progress=None, keys=None):
        total = len(MODEL_SPECS) if keys is None else len(keys)
        done = 0
        for key, spec in MODEL_SPECS.items():
            if keys is not None and key not in keys:
                continue
            target = _TARGET_HEIGHT.get(key, 72)
            ppm = target / max(0.1, spec["height"] * ASPECT)
            f = ppm * spec["dist"]
            cw = int(spec["size"][0] * ppm * 1.9) + 18
            chh = int(spec["size"][1] * ppm * ASPECT * 1.9) + 18
            steps = _yaw_steps(key)
            for pose_name, pose_kwargs in spec["poses"].items():
                kw = dict(spec["kwargs"])
                params = inspect.signature(spec["builder"]).parameters
                if "pose" in params:
                    mesh = spec["builder"](pose=dict(pose_kwargs), **kw)
                else:
                    kw.update(pose_kwargs)
                    mesh = spec["builder"](**kw)
                smooth = _smooth_normals(mesh)
                baked = []
                for i in range(steps):
                    yaw = i * 2.0 * math.pi / steps
                    baked.append(bake_pixel_sprite(
                        mesh, yaw=yaw, pitch=0.10, dist=spec["dist"], f=f,
                        aspect=ASPECT, canvas=(cw, chh),
                        smooth_normals=smooth))
                self.frames[(key, pose_name)] = baked
                self.meshes[(key, pose_name)] = mesh
            done += 1
            if progress:
                progress(key, done / max(1, total))
        return self

    def get(self, model, pose, frame):
        row = self.frames.get((model, pose))
        if row is None:
            row = self.frames.get((model, "idle"))
        if not row:
            return None
        return row[frame % len(row)]

    def yaw_frame(self, ent_yaw, cam_yaw, steps=None):
        steps = steps or self.yaw_steps
        rel = ent_yaw - cam_yaw - math.pi
        frame = math.floor(rel / (2.0 * math.pi) * steps + 0.5)
        return int(frame) % steps

    def steps_for(self, model, pose):
        row = self.frames.get((model, pose))
        if row is None:
            row = self.frames.get((model, "idle"))
        return len(row) if row else self.yaw_steps

    def mesh_for(self, model, pose):
        mesh = self.meshes.get((model, pose))
        if mesh is None:
            mesh = self.meshes.get((model, "idle"))
        return mesh


def _face_color(col, face_lum, normal):
    cr = (col >> 16) & 255
    cg = (col >> 8) & 255
    cb = col & 255
    exposed = (face_lum - AMBIENT) / (1.0 - AMBIENT)
    k = 0.30 + 0.70 * exposed
    shade = max(0.0, 1.0 - exposed)
    lum_c = (cr * 299 + cg * 587 + cb * 114) // 1000
    metal = ((max(cr, cg, cb) - min(cr, cg, cb)) < 60 and lum_c > 110) \
        or (cr > 150 and cg > 110 and cb < cg * 0.8)
    spec = 0.0
    if metal:
        ndoth = m3.dot(normal, HALF_VEC)
        if ndoth > 0.0:
            spec = (ndoth ** 14) * (0.55 if exposed > 0.35 else 0.25)
    return pack_rgb(
        min(255, cr * k + shade * SHADOW_TINT[0] * 0.28 + spec * 250.0),
        min(255, cg * k + shade * SHADOW_TINT[1] * 0.28 + spec * 250.0),
        min(255, cb * k + shade * SHADOW_TINT[2] * 0.28 + spec * 250.0),
    )


def _shade_table(color):
    """31 pre-shaded variants for Gouraud interpolation, 0.70..1.30."""
    table = []
    for i in range(31):
        k = 0.70 + i * 0.02
        table.append(pack_rgb(((color >> 16) & 255) * k,
                              ((color >> 8) & 255) * k,
                              (color & 255) * k))
    return table


def _raster_tri(img, zbuf, cw, ch, tri, shades, face_lum, box=None):
    tri = sorted(tri, key=lambda p: p[1])
    (x0, y0, d0, l0), (x1, y1, d1, l1), (x2, y2, d2, l2) = tri
    if y2 - y0 < 1e-7:
        return
    ys = max(0, int(math.ceil(y0 - 0.5)))
    ye = min(ch - 1, int(y2 + 0.5))
    if box is not None and ys < box[1]:
        box[1] = ys
    if box is not None and ye > box[3]:
        box[3] = ye
    y01 = y1 - y0 if y1 - y0 else 1e-7
    y12 = y2 - y1 if y2 - y1 else 1e-7
    y02 = y2 - y0
    inv_lum = 1.0 / max(0.05, face_lum)
    for y in range(ys, ye + 1):
        py = y + 0.5
        if py < y0 or py > y2:
            continue
        ta = (py - y0) / y02
        xa = x0 + (x2 - x0) * ta
        da = d0 + (d2 - d0) * ta
        la = l0 + (l2 - l0) * ta
        if py < y1:
            tb = (py - y0) / y01
            xb = x0 + (x1 - x0) * tb
            db = d0 + (d1 - d0) * tb
            lb = l0 + (l1 - l0) * tb
        else:
            tb = (py - y1) / y12
            xb = x1 + (x2 - x1) * tb
            db = d1 + (d2 - d1) * tb
            lb = l1 + (l2 - l1) * tb
        if xb < xa:
            xa, xb, da, db, la, lb = xb, xa, db, da, lb, la
        xs = max(0, int(math.ceil(xa - 0.5)))
        xe = min(cw - 1, int(xb + 0.5))
        if xe < xs:
            continue
        if box is not None:
            if xs < box[0]:
                box[0] = xs
            if xe > box[2]:
                box[2] = xe
        span = (xb - xa) if (xb - xa) > 1e-7 else 1e-7
        row = y * cw
        for x in range(xs, xe + 1):
            t = (x + 0.5 - xa) / span
            d = da + (db - da) * t
            o = row + x
            if d < zbuf[o]:
                zbuf[o] = d
                if len(shades) == 1:
                    img[o] = shades[0]
                    continue
                k = int((la + (lb - la) * t) * inv_lum * 50.0 - 34.5)
                if k < 0:
                    k = 0
                elif k > 30:
                    k = 30
                img[o] = shades[k]


def _outline(img, alpha, cw, ch, box):
    """Darken silhouette pixels by 45% so figures read against terrain."""
    x0, y0, x1, y1 = box
    marks = []
    for y in range(max(1, y0), min(ch - 1, y1 + 1)):
        row = y * cw
        up = row - cw
        down = row + cw
        for x in range(max(1, x0), min(cw - 1, x1 + 1)):
            o = row + x
            if alpha[o] == 0:
                continue
            if ((alpha[o - 1] == 0)
                    or (alpha[o + 1] == 0)
                    or (alpha[up + x] == 0)
                    or (alpha[down + x] == 0)):
                marks.append(o)
    for o in marks:
        c = img[o]
        img[o] = pack_rgb(((c >> 16) & 255) * 0.55,
                          ((c >> 8) & 255) * 0.55,
                          (c & 255) * 0.55)


def _pack(img, alpha, cw, box):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    rgba = bytearray(w * h * 4)
    for y in range(h):
        src = (y0 + y) * cw
        dst = y * w
        for x in range(w):
            o = src + x0 + x
            if alpha[o]:
                q = (dst + x) * 4
                c = img[o]
                rgba[q] = (c >> 16) & 255
                rgba[q + 1] = (c >> 8) & 255
                rgba[q + 2] = c & 255
                rgba[q + 3] = 255
    return w, h, rgba


def bake_pixel_sprite(mesh, yaw=0.0, pitch=0.30, dist=9.0, f=140.0,
                      aspect=ASPECT, canvas=(120, 120), light=None,
                      smooth_normals=None):
    """Bake a mesh into a cropped RGBA PixelSprite viewed from yaw/pitch."""
    cw, ch = canvas
    cx, cy = cw * 0.5, ch * 0.5
    L = light or LIGHT_DIR
    matrix = m3.mat_mul(m3.rot_x_matrix(pitch), m3.rot_y_matrix(yaw))
    rotated = [m3.mat_vec(matrix, v) for v in mesh.verts]
    proj = []
    for tv in rotated:
        d = dist - tv[2]
        if d < 0.5:
            d = 0.5
        proj.append((cx + tv[0] / d * f, cy - tv[1] / d * f * aspect, d))
    img = [-1] * (cw * ch)
    alpha = bytearray(cw * ch)
    zbuf = [INF] * (cw * ch)
    if smooth_normals is None:
        smooth_normals = _smooth_normals(mesh)
    has_em = any(face[5] for face in mesh.faces)
    glow_img = glow_alpha = glow_zbuf = None
    if has_em:
        glow_img = [-1] * (cw * ch)
        glow_alpha = bytearray(cw * ch)
        glow_zbuf = [INF] * (cw * ch)
    box = [cw, ch, -1, -1]
    for face in mesh.faces:
        ia, ib, ic, idd, col, em, smooth = face
        n = m3.face_normal(rotated[ia], rotated[ib], rotated[ic])
        if n[2] <= 0.02:
            continue
        face_lum = AMBIENT + (1.0 - AMBIENT) * max(0.0, m3.dot(n, L))
        if smooth:
            lums = []
            for vi in (ia, ib, ic, idd):
                vn = smooth_normals.get(mesh.verts[vi])
                if vn is None:
                    vl = face_lum
                else:
                    rn = m3.mat_vec(matrix, m3.normalize(vn))
                    vl = AMBIENT + (1.0 - AMBIENT) * max(0.0, m3.dot(rn, L))
                lums.append(vl)
        else:
            lums = [face_lum] * 4
        if em:
            lums = [max(v, 0.88) for v in lums]
        base = _face_color(col, face_lum, n)
        shades = _shade_table(base)
        p0, p1, p2, p3 = proj[ia], proj[ib], proj[ic], proj[idd]
        tri0 = ((p0[0], p0[1], p0[2], lums[0]),
                (p1[0], p1[1], p1[2], lums[1]),
                (p2[0], p2[1], p2[2], lums[2]))
        tri1 = ((p0[0], p0[1], p0[2], lums[0]),
                (p2[0], p2[1], p2[2], lums[2]),
                (p3[0], p3[1], p3[2], lums[3]))
        _raster_tri(img, zbuf, cw, ch, tri0, shades, face_lum, box)
        _raster_tri(img, zbuf, cw, ch, tri1, shades, face_lum, box)
        if glow_img is not None:
            _raster_tri(glow_img, glow_zbuf, cw, ch, tri0, [col], 1.0, box)
            _raster_tri(glow_img, glow_zbuf, cw, ch, tri1, [col], 1.0, box)
    if box[2] < box[0]:
        return PixelSprite(1, 1, bytearray(4))
    box[0] = max(0, box[0] - 1)
    box[1] = max(0, box[1] - 1)
    box[2] = min(cw - 1, box[2] + 1)
    box[3] = min(ch - 1, box[3] + 1)
    # Derive coverage from the depth buffer: every rasterised pixel is opaque.
    for y in range(box[1], box[3] + 1):
        row = y * cw
        for x in range(box[0], box[2] + 1):
            if zbuf[row + x] < INF:
                alpha[row + x] = 1
    _outline(img, alpha, cw, ch, box)
    if glow_img is not None:
        for y in range(box[1], box[3] + 1):
            row = y * cw
            for x in range(box[0], box[2] + 1):
                if glow_zbuf[row + x] < INF:
                    glow_alpha[row + x] = 1
    crop = (box[0], box[1], box[2] + 1, box[3] + 1)
    w, h, rgba = _pack(img, alpha, cw, crop)
    glow = None
    if glow_img is not None:
        gw, gh, grgba = _pack(glow_img, glow_alpha, cw, crop)
        if gw == w and gh == h:
            glow = PixelSprite(gw, gh, grgba)
    return PixelSprite(w, h, rgba, glow)
