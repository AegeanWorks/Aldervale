"""Runtime 3D model renderer for nearby actors.

Billboards are cheap but always face the camera in fixed yaw steps.  This
module draws the actual low-poly mesh for the player and nearby characters:
perspective projection, backface culling, world-space directional lighting and
a shared z-buffer with the terrain.  Distant actors still use the baked atlas.
"""

import math

from . import math3d as m3
from .buffer import pack_rgb
from .gfx import FrameBuffer
from .mesh import SHADOW_TINT, _smooth_normals

WORLD_LIGHT = m3.normalize((0.42, 0.78, 0.46))


class ModelRenderer:
    """Draws cached meshes for (model, pose) pairs into a pixel frame."""

    def __init__(self, atlas):
        self.atlas = atlas
        self._cache = {}
        self._temp = None

    def _prepare(self, model, pose):
        key = (model, pose)
        data = self._cache.get(key)
        if data is not None:
            return data
        mesh = self.atlas.mesh_for(model, pose)
        if mesh is None:
            self._cache[key] = None
            return None
        normals = []
        for face in mesh.faces:
            ia, ib, ic = face[0], face[1], face[2]
            normals.append(m3.face_normal(mesh.verts[ia], mesh.verts[ib],
                                          mesh.verts[ic]))
        smooth_map = _smooth_normals(mesh)
        vnormals = []
        for vert in mesh.verts:
            n = smooth_map.get(vert)
            vnormals.append(m3.normalize(n) if n is not None else None)
        data = (mesh, normals, vnormals)
        self._cache[key] = data
        return data

    def draw(self, fb, cam, ent, tr, tg, tb, flash=0.0, flash_color=None,
             outline=True, depth_bias=0.0):
        """Rasterise one actor; return the number of pixels written.

        A positive ``depth_bias`` draws the model into a private buffer first
        and composites it over the scene with the bias.  That keeps the model's
        own faces correctly z-ordered while letting the player stay visible
        over a foreground terrain crest.
        """
        if depth_bias <= 0.0:
            return self._draw_into(fb, cam, ent, tr, tg, tb, flash,
                                   flash_color, outline)[0]
        if (self._temp is None or self._temp.w != fb.w
                or self._temp.h != fb.h):
            self._temp = FrameBuffer(fb.w, fb.h)
        tmp = self._temp
        tmp.clear()
        total, mask, box = self._draw_into(tmp, cam, ent, tr, tg, tb,
                                           flash, flash_color, True)
        if total and mask is not None:
            self._composite(fb, tmp, mask, box, depth_bias)
        return total

    def _composite(self, fb, tmp, mask, box, bias):
        w, h = fb.w, fb.h
        x0, y0, x1, y1 = box
        for y in range(y0, y1):
            for x in range(x0, x1):
                o = x * h + y
                if not mask[o]:
                    continue
                d = tmp.depth[o]
                if d - bias < fb.depth[o]:
                    fb.depth[o] = d
                    q = o * 3
                    fb.data[q:q + 3] = tmp.data[q:q + 3]

    def _draw_into(self, fb, cam, ent, tr, tg, tb, flash, flash_color,
                   outline):
        prepared = self._prepare(ent.model, ent.pose)
        if prepared is None:
            return 0, None, (0, 0, 0, 0)
        mesh, normals, vnormals = prepared
        w, h = fb.w, fb.h
        sin_y = math.sin(cam.yaw)
        cos_y = math.cos(cam.yaw)
        cy = math.cos(ent.yaw)
        sy = math.sin(ent.yaw)
        scale = ent.scale
        ground = ent.ground_y + ent.y_off
        camx, camy, camz = cam.x, cam.y, cam.z
        f = cam.f
        half_w = w * 0.5
        horizon = cam.horizon
        proj = []
        for vx, vy, vz in mesh.verts:
            vx *= scale
            vy *= scale
            vz *= scale
            wx = vx * cy + vz * sy + ent.x
            wz = -vx * sy + vz * cy + ent.z
            dx = wx - camx
            dz = wz - camz
            d = dx * sin_y + dz * cos_y
            behind = d < 0.25
            if behind:
                d = 0.25
            side = dx * cos_y - dz * sin_y
            proj.append((half_w + side / d * f,
                         horizon - (ground + vy - camy) / d * f,
                         d, behind))
        img = fb.data
        zbuf = fb.depth
        mask = bytearray(w * h) if outline else None
        lx, ly, lz = WORLD_LIGHT
        sr, sg, sb = SHADOW_TINT
        flash = max(0.0, min(1.0, flash))
        fr = fg = fb_ = 0
        if flash > 0.0 and flash_color is not None:
            fr = (flash_color >> 16) & 255
            fg = (flash_color >> 8) & 255
            fb_ = flash_color & 255
        total = 0
        shade_cache = {}
        for face, n in zip(mesh.faces, normals):
            ia, ib, ic, idd, col, em, smooth = face
            nx = n[0] * cy + n[2] * sy
            ny = n[1]
            nz = -n[0] * sy + n[2] * cy
            nd = nx * sin_y + nz * cos_y
            if nd > -0.02:
                continue
            p0, p1, p2, p3 = proj[ia], proj[ib], proj[ic], proj[idd]
            if p0[3] or p1[3] or p2[3] or p3[3]:
                continue
            x0 = min(p0[0], p1[0], p2[0], p3[0])
            x1 = max(p0[0], p1[0], p2[0], p3[0])
            y0 = min(p0[1], p1[1], p2[1], p3[1])
            y1 = max(p0[1], p1[1], p2[1], p3[1])
            if x1 < 0 or x0 > w or y1 < 0 or y0 > h:
                continue
            lit = nx * lx + ny * ly + nz * lz
            if lit < 0.0:
                lit = 0.0
            rim = -nd if nd < 0.0 else 0.0
            if rim > 1.0:
                rim = 1.0
            k = 0.40 + 0.50 * lit + 0.10 * rim
            if em:
                k = max(k, 0.92)
            shade = (1.0 - lit) * 0.20
            r = (((col >> 16) & 255) * k + sr * shade) * tr
            g = (((col >> 8) & 255) * k + sg * shade) * tg
            b = ((col & 255) * k + sb * shade) * tb
            if flash > 0.0:
                r += (fr - r) * flash
                g += (fg - g) * flash
                b += (fb_ - b) * flash
            packed = pack_rgb(r, g, b)
            use_smooth = smooth and all(vnormals[i] is not None
                                        for i in (ia, ib, ic, idd))
            if use_smooth:
                table = shade_cache.get((col, em))
                if table is None:
                    table = []
                    for i in range(16):
                        kv = 0.35 + 0.65 * i / 15.0
                        if em:
                            kv = max(kv, 0.92)
                        sh = (1.0 - kv) * 0.20
                        rr = (((col >> 16) & 255) * kv + sr * sh) * tr
                        gg = (((col >> 8) & 255) * kv + sg * sh) * tg
                        bb = ((col & 255) * kv + sb * sh) * tb
                        if flash > 0.0:
                            rr += (fr - rr) * flash
                            gg += (fg - gg) * flash
                            bb += (fb_ - bb) * flash
                        table.append(pack_rgb(rr, gg, bb))
                    shade_cache[(col, em)] = table
                ks = []
                for vi in (ia, ib, ic, idd):
                    vn = vnormals[vi]
                    vx = vn[0] * cy + vn[2] * sy
                    vy = vn[1]
                    vz = -vn[0] * sy + vn[2] * cy
                    lv = vx * lx + vy * ly + vz * lz
                    if lv < 0.0:
                        lv = 0.0
                    ndv = vx * sin_y + vz * cos_y
                    rv = -ndv if ndv < 0.0 else 0.0
                    if rv > 1.0:
                        rv = 1.0
                    kv = 0.40 + 0.50 * lv + 0.10 * rv
                    if em:
                        kv = max(kv, 0.92)
                    ks.append(kv)
                t0 = (p0[0], p0[1], p0[2], ks[0])
                t1 = (p1[0], p1[1], p1[2], ks[1])
                t2 = (p2[0], p2[1], p2[2], ks[2])
                t3 = (p3[0], p3[1], p3[2], ks[3])
                total += _raster_tri_smooth(img, zbuf, w, h,
                                            (t0, t1, t2), table, mask)
                total += _raster_tri_smooth(img, zbuf, w, h,
                                            (t0, t2, t3), table, mask)
            else:
                total += _raster_tri(img, zbuf, w, h,
                                     (p0, p1, p2), packed, mask)
                total += _raster_tri(img, zbuf, w, h,
                                     (p0, p2, p3), packed, mask)
        xs = [p[0] for p in proj]
        ys = [p[1] for p in proj]
        box = (max(0, int(min(xs)) - 1),
               max(0, int(min(ys)) - 1),
               min(w, int(max(xs)) + 2),
               min(h, int(max(ys)) + 2))
        if mask is not None and total:
            _outline_model(img, mask, w, h, box[0], box[1], box[2], box[3])
        return total, mask, box


def _outline_model(img, mask, w, h, x0, y0, x1, y1):
    """Darken silhouette pixels of one model by 45% for contrast."""
    for y in range(y0, y1):
        for x in range(x0, x1):
            o = x * h + y
            if not mask[o]:
                continue
            edge = ((x == 0 or not mask[o - h])
                    or (x == w - 1 or not mask[o + h])
                    or (y == 0 or not mask[o - 1])
                    or (y == h - 1 or not mask[o + 1]))
            if not edge:
                continue
            q = o * 3
            img[q] = int(img[q] * 0.55)
            img[q + 1] = int(img[q + 1] * 0.55)
            img[q + 2] = int(img[q + 2] * 0.55)


def _raster_tri_smooth(img, zbuf, w, h, tri, table, mask=None):
    """Gouraud scanline fill: interpolates a 0.35..1.0 shade index."""
    (ax, ay, ad, ak), (bx, by, bd, bk), (cx, cy2, cd, ck) = tri
    if ay > by:
        ax, ay, ad, ak, bx, by, bd, bk = bx, by, bd, bk, ax, ay, ad, ak
    if by > cy2:
        bx, by, bd, bk, cx, cy2, cd, ck = cx, cy2, cd, ck, bx, by, bd, bk
    if ay > by:
        ax, ay, ad, ak, bx, by, bd, bk = bx, by, bd, bk, ax, ay, ad, ak
    if cy2 - ay < 1e-7:
        return 0
    ys = max(0, int(math.ceil(ay - 0.5)))
    ye = min(h - 1, int(math.floor(cy2 - 0.5)))
    if ye < ys:
        return 0
    y01 = by - ay if by - ay else 1e-7
    y12 = cy2 - by if cy2 - by else 1e-7
    y02 = cy2 - ay
    written = 0
    for y in range(ys, ye + 1):
        py = y + 0.5
        ta = (py - ay) / y02
        if ta < 0.0:
            ta = 0.0
        elif ta > 1.0:
            ta = 1.0
        xa = ax + (cx - ax) * ta
        da = ad + (cd - ad) * ta
        ka = ak + (ck - ak) * ta
        if py < by:
            tb = (py - ay) / y01
            if tb < 0.0:
                tb = 0.0
            elif tb > 1.0:
                tb = 1.0
            xb = ax + (bx - ax) * tb
            db = ad + (bd - ad) * tb
            kb = ak + (bk - ak) * tb
        else:
            tb = (py - by) / y12
            if tb < 0.0:
                tb = 0.0
            elif tb > 1.0:
                tb = 1.0
            xb = bx + (cx - bx) * tb
            db = bd + (cd - bd) * tb
            kb = bk + (ck - bk) * tb
        if xb < xa:
            xa, xb, da, db, ka, kb = xb, xa, db, da, kb, ka
        xs = max(0, int(math.ceil(xa - 0.5)))
        xe = min(w - 1, int(xb + 0.5))
        if xe < xs:
            continue
        span = (xb - xa) if (xb - xa) > 1e-7 else 1e-7
        for x in range(xs, xe + 1):
            t = (x + 0.5 - xa) / span
            d = da + (db - da) * t
            o = x * h + y
            if d < zbuf[o]:
                zbuf[o] = d
                if mask is not None:
                    mask[o] = 1
                k = ka + (kb - ka) * t
                idx = int((k - 0.35) / 0.65 * 15.0 + 0.5)
                if idx < 0:
                    idx = 0
                elif idx > 15:
                    idx = 15
                c = table[idx]
                q = o * 3
                img[q] = (c >> 16) & 255
                img[q + 1] = (c >> 8) & 255
                img[q + 2] = c & 255
                written += 1
    return written


def _raster_tri(img, zbuf, w, h, tri, color, mask=None):
    """Scanline-fill one triangle with a shared column-major z-buffer."""
    (ax, ay, ad, _), (bx, by, bd, _), (cx, cy2, cd, _) = tri
    if ay > by:
        ax, ay, ad, bx, by, bd = bx, by, bd, ax, ay, ad
    if by > cy2:
        bx, by, bd, cx, cy2, cd = cx, cy2, cd, bx, by, bd
    if ay > by:
        ax, ay, ad, bx, by, bd = bx, by, bd, ax, ay, ad
    if cy2 - ay < 1e-7:
        return 0
    ys = max(0, int(math.ceil(ay - 0.5)))
    ye = min(h - 1, int(math.floor(cy2 - 0.5)))
    if ye < ys:
        return 0
    y01 = by - ay if by - ay else 1e-7
    y12 = cy2 - by if cy2 - by else 1e-7
    y02 = cy2 - ay
    written = 0
    r = (color >> 16) & 255
    g = (color >> 8) & 255
    b = color & 255
    for y in range(ys, ye + 1):
        py = y + 0.5
        ta = (py - ay) / y02
        if ta < 0.0:
            ta = 0.0
        elif ta > 1.0:
            ta = 1.0
        xa = ax + (cx - ax) * ta
        da = ad + (cd - ad) * ta
        if py < by:
            tb = (py - ay) / y01
            if tb < 0.0:
                tb = 0.0
            elif tb > 1.0:
                tb = 1.0
            xb = ax + (bx - ax) * tb
            db = ad + (bd - ad) * tb
        else:
            tb = (py - by) / y12
            if tb < 0.0:
                tb = 0.0
            elif tb > 1.0:
                tb = 1.0
            xb = bx + (cx - bx) * tb
            db = bd + (cd - bd) * tb
        if xb < xa:
            xa, xb, da, db = xb, xa, db, da
        xs = max(0, int(math.ceil(xa - 0.5)))
        xe = min(w - 1, int(xb + 0.5))
        if xe < xs:
            continue
        span = (xb - xa) if (xb - xa) > 1e-7 else 1e-7
        for x in range(xs, xe + 1):
            t = (x + 0.5 - xa) / span
            d = da + (db - da) * t
            o = x * h + y
            if d < zbuf[o]:
                zbuf[o] = d
                if mask is not None:
                    mask[o] = 1
                q = o * 3
                img[q] = r
                img[q + 1] = g
                img[q + 2] = b
                written += 1
    return written
