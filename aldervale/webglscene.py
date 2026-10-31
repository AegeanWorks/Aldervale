"""World and model payloads for the WebGL client.

The GPU client does not need per-pixel frames.  It receives the heightfield and
material textures once, a triangle-soup bundle of every model pose, and a small
scene description each tick (camera, visible entities, HUD).  The Python
simulation stays authoritative.
"""

import base64
import inspect
import math
from array import array

from . import math3d as m3
from .atlas import MODEL_SPECS
from .buffer import pack_rgb
from .mesh import _smooth_normals
from .rules import ITEMS, xp_for_level

MAX_SCENE_DIST = 90.0


class MeshAtlas:
    """Minimal atlas for the GPU path: source meshes, no baked sprites."""

    def __init__(self):
        self.heights = {}
        self.meshes = {}
        for key, spec in MODEL_SPECS.items():
            self.heights[key] = spec["height"]

    def build(self, progress=None, keys=None):
        total = len(MODEL_SPECS) if keys is None else len(keys)
        done = 0
        for key, spec in MODEL_SPECS.items():
            if keys is not None and key not in keys:
                continue
            for pose_name, pose_kwargs in spec["poses"].items():
                kw = dict(spec["kwargs"])
                params = inspect.signature(spec["builder"]).parameters
                if "pose" in params:
                    mesh = spec["builder"](pose=dict(pose_kwargs), **kw)
                else:
                    kw.update(pose_kwargs)
                    mesh = spec["builder"](**kw)
                self.meshes[(key, pose_name)] = mesh
            done += 1
            if progress:
                progress(key, done / max(1, total))
        return self

    def mesh_for(self, model, pose):
        mesh = self.meshes.get((model, pose))
        if mesh is None:
            mesh = self.meshes.get((model, "idle"))
        return mesh

    def get(self, model, pose, frame=0):
        return None

    def steps_for(self, model, pose):
        return 1

    def yaw_frame(self, ent_yaw, cam_yaw, steps=None):
        return 0


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def world_bundle(world):
    """Heightfield floats and a lit RGBA colour map, row-major."""
    ter = world.terrain
    W = ter.W
    heights = array("f")
    for row in ter.heights:
        heights.extend(row)
    # Reuse the pixel palette so both renderers share the same ground colours.
    from .gfxrender import _ground_palette
    palette = _ground_palette(ter)
    colors = bytearray(W * W * 4)
    o = 0
    for iz in range(W):
        row = palette[iz]
        for ix in range(W):
            c = row[ix]
            colors[o] = (c >> 16) & 255
            colors[o + 1] = (c >> 8) & 255
            colors[o + 2] = c & 255
            colors[o + 3] = (ter.materials[iz][ix]
                              if ter.materials else 0)
            o += 4
    return {
        "meta": {"w": W, "water": ter.water, "seed": world.seed},
        "heights": _b64(heights.tobytes()),
        "colors": _b64(bytes(colors)),
    }


def model_bundle(atlas):
    """Triangle soup for every (model, pose), shared across all entities."""
    pos = array("f")
    norm = array("b")
    col = bytearray()
    meta = {}
    for key, spec in MODEL_SPECS.items():
        poses = {}
        for pose_name in spec["poses"]:
            mesh = atlas.mesh_for(key, pose_name)
            if mesh is None:
                poses[pose_name] = {"offset": 0, "count": 0}
                continue
            smooth_map = _smooth_normals(mesh)
            start = len(pos) // 3
            for face in mesh.faces:
                ia, ib, ic, idd, color, _em, smooth = face
                fn = m3.face_normal(mesh.verts[ia], mesh.verts[ib],
                                    mesh.verts[ic])
                for vi in (ia, ib, ic, ia, ic, idd):
                    vx, vy, vz = mesh.verts[vi]
                    pos.extend((vx, vy, vz))
                    vn = smooth_map.get(mesh.verts[vi]) if smooth else None
                    if vn is not None:
                        nx, ny, nz = m3.normalize(vn)
                    else:
                        nx, ny, nz = fn
                    norm.extend((max(-127, min(127, int(nx * 127))),
                                 max(-127, min(127, int(ny * 127))),
                                 max(-127, min(127, int(nz * 127)))))
                    col.extend(((color >> 16) & 255, (color >> 8) & 255,
                                color & 255))
            poses[pose_name] = {"offset": start,
                                "count": len(pos) // 3 - start}
        meta[key] = poses
    return {
        "meta": meta,
        "pos": _b64(pos.tobytes()),
        "norm": _b64(norm.tobytes()),
        "col": _b64(bytes(col)),
    }


def _hud_rows(screen):
    return {"chars": ["".join(row) for row in screen.chars],
            "colors": [[int(c) for c in row] for row in screen.fg]}


def scene(game, world, seq=0):
    """Small per-tick scene description for the WebGL client."""
    cam = game.cam
    if cam is None:
        game._ensure_camera()
        cam = game.cam
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    half_tan = math.tan(1.22 * 0.5)
    env = game._last_env
    ar, ag, ab = env.ambient
    fogc = env.fog
    fgr = ((fogc >> 16) & 255) / 255.0
    fgg = ((fogc >> 8) & 255) / 255.0
    fgb = (fogc & 255) / 255.0
    fog_end = 230.0 * 0.96
    inv_fog = 1.0 / (fog_end - 55.0)
    candidates = list(world.entities)
    player = getattr(world, "player", None)
    if player is not None:
        candidates.append(player)
    ents = []
    for ent in candidates:
        dx = ent.x - cam.x
        dz = ent.z - cam.z
        depth = dx * sin_y + dz * cos_y
        if depth < 0.8 or depth > MAX_SCENE_DIST:
            continue
        side = dx * cos_y - dz * sin_y
        if abs(side) > depth * half_tan * 1.4 + 10.0:
            continue
        fog = depth - 55.0
        fog = 0.0 if fog <= 0.0 else min(1.0, fog * inv_fog)
        tr = ar * (1.0 - fog) + fgr * fog
        tg = ag * (1.0 - fog) + fgg * fog
        tb = ab * (1.0 - fog) + fgb * fog
        ents.append({
            "model": ent.model,
            "pose": ent.pose,
            "x": round(ent.x, 3),
            "y": round(ent.ground_y + ent.y_off, 3),
            "z": round(ent.z, 3),
            "yaw": round(ent.yaw, 4),
            "scale": round(ent.scale, 3),
            "radius": round(getattr(ent, "radius", 0.5), 3),
            "tint": [round(tr, 3), round(tg, 3), round(tb, 3)],
            "flash": round(ent.flash, 3),
            "kind": getattr(ent, "kind", ""),
        })
    lights = []
    for ent in world.entities:
        if ent.model.startswith("house"):
            lx = ent.x + math.sin(ent.yaw) * 2.05
            lz = ent.z + math.cos(ent.yaw) * 2.05
            ly = world.terrain.height(lx, lz) + 1.55
            col = (1.0, 0.74, 0.42)
            radius = 6.0
            flicker = 0.25
        elif ent.model == "windmill":
            lx = ent.x + math.sin(ent.yaw) * 1.9
            lz = ent.z + math.cos(ent.yaw) * 1.9
            ly = ent.ground_y + 4.5
            col = (1.0, 0.72, 0.40)
            radius = 6.0
            flicker = 0.2
        elif ent.model == "campfire":
            lx, lz, ly = ent.x, ent.z, ent.ground_y + 0.55
            col = (1.0, 0.52, 0.20)
            radius = 6.0
            flicker = 1.0
        elif ent.model == "torch":
            lx, lz, ly = ent.x, ent.z, ent.ground_y + 2.0
            col = (1.0, 0.62, 0.28)
            radius = 5.5
            flicker = 0.9
        elif ent.model == "shrine":
            lx, lz, ly = ent.x, ent.z, ent.ground_y + 1.2
            col = (0.58, 0.76, 1.0)
            radius = 5.0
            flicker = 0.35
        else:
            continue
        ddx = lx - cam.x
        ddz = lz - cam.z
        depth = ddx * sin_y + ddz * cos_y
        if depth < 1.0 or depth > 45.0:
            continue
        lights.append((math.hypot(ddx, ddz), lx, ly, lz, col, radius,
                       flicker))
    lights.sort(key=lambda item: item[0])
    lights = [{"x": round(l[1], 2), "y": round(l[2], 2),
               "z": round(l[3], 2), "c": l[4],
               "r": l[5], "f": l[6]} for l in lights[:6]]
    smoke = []
    chimney = {"house0": (1.5, -0.7), "house1": (-1.5, -0.7),
               "house2": (1.275, -0.595)}
    for ent in world.entities:
        if not ent.model.startswith("house"):
            continue
        lx, lz = chimney.get(ent.model, (1.5, -0.7))
        c, s = math.cos(ent.yaw), math.sin(ent.yaw)
        smoke.append({
            "x": round(ent.x + c * lx + s * lz, 2),
            "y": round(ent.ground_y + 3.82, 2),
            "z": round(ent.z - s * lx + c * lz, 2),
            "phase": round((len(smoke) * 0.37) % 1.0, 3),
        })
    p = world.player
    inv = p.inventory
    status = None
    if game.state == "play" and not p.dead:
        weapon = ITEMS[inv.weapon]
        armor = ITEMS[inv.armor]
        status = {
            "name": p.name,
            "level": p.level,
            "gold": inv.count("gold"),
            "hp": round(p.hp, 1),
            "max_hp": p.max_hp,
            "stamina": round(p.stamina, 1),
            "max_stamina": p.max_stamina,
            "xp": p.xp,
            "xp_next": xp_for_level(p.level),
            "potions": inv.count("potion"),
            "weapon": weapon.name,
            "weapon_atk": weapon.atk,
            "armor": armor.name,
            "armor_def": armor.dfn,
            "quest": world.quest_objective(),
        }
    return {
        "status": "ready",
        "seq": seq,
        "camera": {
            "x": round(cam.x, 3), "y": round(cam.y, 3),
            "z": round(cam.z, 3), "yaw": round(cam.yaw, 4),
            "f": round(cam.f, 3), "fy": round(cam.fy, 3),
            "w": game.w, "h": game.h, "horizon": cam.horizon,
        },
        "env": {
            "daylight": round(env.daylight, 3),
            "sun_el": round(env.sun_el, 3),
            "fog": [((env.fog >> 16) & 255) / 255.0,
                    ((env.fog >> 8) & 255) / 255.0,
                    (env.fog & 255) / 255.0],
            "zenith": [((env.zenith >> 16) & 255) / 255.0,
                       ((env.zenith >> 8) & 255) / 255.0,
                       (env.zenith & 255) / 255.0],
            "horizon": [((env.horizon_col >> 16) & 255) / 255.0,
                        ((env.horizon_col >> 8) & 255) / 255.0,
                        (env.horizon_col & 255) / 255.0],
        },
        "entities": ents,
        "lights": lights,
        "smoke": smoke,
        "hud_status": status,
        "hud": _hud_rows(game.screen),
        "state": game.state,
        "weather": getattr(world, "weather", "clear"),
        "show_map": bool(game.show_map),
        "player": {"x": round(world.player.x, 2),
                   "z": round(world.player.z, 2),
                   "yaw": round(world.player.yaw, 3),
                   "hp": round(world.player.hp, 1),
                   "max_hp": world.player.max_hp,
                   "stamina": round(world.player.stamina, 1)},
    }
