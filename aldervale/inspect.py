"""Headless inspection harness: visible frames plus a scripted control probe.

``python -m aldervale --inspect OUTDIR`` writes one PNG per scene and a JSON
report of scripted input checks.  The images show the real char-cell output,
so a reviewer can see terrain, sprites, fog, HUD and menus without a terminal;
the checks exercise the same key and mouse path the player uses.
"""

import json
import math
import os
import time
from types import SimpleNamespace

from .atlas import SpriteAtlas
from .buffer import FAR, Screen, pack_rgb
from .capture import save_png
from .game import Game
from .render import Env
from .rules import ITEMS
from .studio import collect_models, encode_screen, write_studio
from .term import vk_token
from .world import QUEST_COLOR, World

DAY = 0.24
NIGHT = 0.80


class ScriptedTerm:
    """A terminal double that replays queued presses, holds and mouse events."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.held = set()
        self.pressed = []
        self.mouse = []
        self.out = []

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
        self.out.append(text)

    def flush(self):
        self.out.append("")


def build_game(seed=7, width=132, height=60, terrain_size=None,
               atlas_keys=None):
    """Create a booted, headless Game ready for rendering or probing."""
    game = Game(seed=seed, width=width, height=height, save_path=os.devnull)
    game.term = None
    game.atlas = SpriteAtlas().build(keys=atlas_keys)
    game.world = World(seed, game.atlas, terrain_size=terrain_size)
    game._open_screen()
    game._ensure_camera()
    game.state = "play"
    game.dt = 1.0 / 30.0
    return game


def _calm(game):
    for e in game.world.entities:
        if getattr(e, "ai_kind", "") in ("hostile", ""):
            if getattr(e, "kind", "") in ("wolf", "bandit", "skeleton",
                                          "captain"):
                e.aggro_r = 0.0
                e.state = "idle"
                e.windup_t = 0.0


def _reset(game, *, hp=None, stamina=None):
    p = game.world.player
    vx, vz = game.world.terrain.village
    p.x, p.z = vx, vz + 6
    p.ground_y = game.world.terrain.height(p.x, p.z)
    p.yaw = math.pi
    p.state = "idle"
    p.attack_t = -1.0
    p.attack_done = True
    p.guarding = False
    p.heal_remaining = 0.0
    p.hurt_t = 0.0
    p.hp = p.max_hp if hp is None else hp
    p.stamina = p.max_stamina if stamina is None else stamina
    game.cam_yaw = math.pi
    game.cam_pitch = 0.30
    game.cam_dist = 4.6
    game.reset_pointer_state()
    game.world.victory_shown = False
    game.world.set_weather("clear")
    game.world.quest = "active"
    game.state = "play"
    game.cam = None
    game._ensure_camera()


def _place(game, x, z, yaw, day_t=DAY):
    p = game.world.player
    p.x, p.z = x, z
    p.ground_y = game.world.terrain.height(x, z)
    p.yaw = yaw
    game.cam_yaw = yaw
    game.cam = None
    game._ensure_camera()
    game.world.time = 0.0
    return day_t


def _scene_title(game):
    game.state = "title"
    game.world.time = 0.0
    game.menu_sel = 0
    return DAY


def _scene_village(game):
    vx, vz = game.world.terrain.village
    return _place(game, vx, vz + 8, math.pi, DAY)


def _scene_road(game):
    vx, vz = game.world.terrain.village
    cx, cz = game.world.terrain.camp
    mx, mz = (vx + cx) * 0.5, (vz + cz) * 0.5
    return _place(game, mx, mz + 14, math.pi, DAY)


def _scene_castle(game):
    kx, kz = game.world.terrain.castle
    return _place(game, kx, kz + 30, math.pi, DAY)


def _scene_castle_night(game):
    kx, kz = game.world.terrain.castle
    return _place(game, kx, kz + 30, math.pi, NIGHT)


def _scene_camp_night(game):
    cx, cz = game.world.terrain.camp
    return _place(game, cx, cz - 18, 0.0, NIGHT)


def _scene_combat(game):
    ter = game.world.terrain
    vx, vz = ter.village
    cx, cz = ter.camp
    mx, mz = (vx + cx) * 0.5, (vz + cz) * 0.5
    yaw = math.atan2(cx - mx, cz - mz)
    _place(game, mx, mz, yaw, DAY)
    p = game.world.player
    foe = next(e for e in game.world.entities
               if getattr(e, "kind", "") == "wolf")
    foe.x, foe.z = p.x, p.z - 2.0
    foe.ground_y = game.world.terrain.height(foe.x, foe.z)
    foe.yaw = 0.0
    foe.state = "windup"
    foe.windup_t = 0.0
    foe.hp = max(1, foe.max_hp // 2)
    p.yaw = math.pi
    p.attack_t = 0.18
    p.attack_done = True
    game.state = "play"
    game.cam_yaw = math.pi
    game.cam = None
    game._ensure_camera()
    return DAY


def _scene_inventory(game):
    p = game.world.player
    for item_id in ("iron_sword", "leather_armor", "potion", "pelt"):
        p.inventory.add(item_id, 1)
    p.inventory.add("gold", 120)
    game.state = "inventory"
    game.inv_message = "U use a potion   E equip the best gear"
    vx, vz = game.world.terrain.village
    _place(game, vx, vz + 8, math.pi, DAY)
    game.state = "inventory"
    return DAY


def _scene_dialogue(game):
    p = game.world.player
    elder = next(e for e in game.world.entities
                 if getattr(e, "name", None) == "Elder Quill")
    p.x, p.z = elder.x, elder.z + 1.8
    p.ground_y = game.world.terrain.height(p.x, p.z)
    p.yaw = math.pi
    game.cam_yaw = math.pi
    game.cam = None
    game._ensure_camera()
    game.dialogue = game.world.npc_talk(elder)
    game.dialogue["_npc"] = elder.eid
    game.dlg_page = 0
    game.dlg_choice = 0
    game.state = "dialogue"
    return DAY


def _scene_shop(game):
    p = game.world.player
    smith = next(e for e in game.world.entities
                 if getattr(e, "name", None) == "Bram the Smith")
    p.x, p.z = smith.x - 1.8, smith.z
    p.ground_y = game.world.terrain.height(p.x, p.z)
    p.yaw = math.pi / 2
    game.cam_yaw = math.pi / 2
    game.cam = None
    game._ensure_camera()
    game.state = "shop"
    game.shop_mode = "buy"
    game.shop_sel = 0
    game.shop_message = "Bram eyes your purse."
    return DAY


def _scene_help(game):
    game.state = "help"
    game.help_from = "play"
    vx, vz = game.world.terrain.village
    _place(game, vx, vz + 8, math.pi, DAY)
    game.state = "help"
    return DAY


def _scene_rain(game):
    vx, vz = game.world.terrain.village
    day = _place(game, vx, vz + 8, math.pi, 0.66)
    game.world.set_weather("rain")
    return day


def _scene_snow(game):
    kx, kz = game.world.terrain.castle
    day = _place(game, kx, kz + 30, math.pi, NIGHT)
    game.world.set_weather("snow")
    return day


def _scene_cottage(game):
    house = next(e for e in game.world.entities
                 if e.model.startswith("house"))
    fx = math.sin(house.yaw)
    fz = math.cos(house.yaw)
    return _place(game, house.x + fx * 7.0, house.z + fz * 7.0,
                  house.yaw + math.pi, DAY)


def _scene_pause(game):
    vx, vz = game.world.terrain.village
    _place(game, vx, vz + 8, math.pi, DAY)
    game.state = "pause"
    game.menu_sel = 1
    return DAY


def _scene_death(game):
    vx, vz = game.world.terrain.village
    _place(game, vx, vz + 8, math.pi, NIGHT)
    p = game.world.player
    p.hp = 0
    p.state = "dead"
    p.hurt_t = 0.4
    game.state = "play"
    return NIGHT


def _scene_victory(game):
    vx, vz = game.world.terrain.village
    _place(game, vx, vz + 8, math.pi, DAY)
    game.world.quest = "done"
    game.world.victory_shown = True
    game.victory_t = 2.0
    game.state = "play"
    return DAY


SCENES = (
    ("title", "01_title.png", _scene_title),
    ("village", "02_village.png", _scene_village),
    ("road", "03_road.png", _scene_road),
    ("castle", "04_castle.png", _scene_castle),
    ("camp_night", "05_camp_night.png", _scene_camp_night),
    ("combat", "06_combat.png", _scene_combat),
    ("inventory", "07_inventory.png", _scene_inventory),
    ("dialogue", "08_dialogue.png", _scene_dialogue),
    ("shop", "09_shop.png", _scene_shop),
    ("help", "10_help.png", _scene_help),
    ("pause", "11_pause.png", _scene_pause),
    ("death", "12_death.png", _scene_death),
    ("victory", "13_victory.png", _scene_victory),
    ("castle_night", "14_castle_night.png", _scene_castle_night),
    ("cottage", "17_cottage.png", _scene_cottage),
    ("rain", "18_rain.png", _scene_rain),
    ("snow", "19_snow.png", _scene_snow),
)


SHEET_ACTORS = (
    ("knight", "idle", "Knight", 1.95),
    ("knight", "walk1", "Walk", 1.95),
    ("knight", "atk1", "Strike", 1.95),
    ("wolf", "idle", "Wolf", 1.0),
    ("skeleton", "idle", "Skeleton", 1.9),
    ("captain", "idle", "Captain", 2.6),
)
SHEET_NATIVE = (
    ("knight", "idle", "Knight"),
    ("wolf", "idle", "Wolf"),
    ("skeleton", "idle", "Skeleton"),
    ("captain", "idle", "Captain"),
    ("torch", "fire1", "Torch"),
    ("campfire", "fire0", "Fire"),
)


def draw_sprite_sheet(screen, atlas):
    """A labelled contact sheet at game scale plus near-native bake cells."""
    w, h = screen.w, screen.h
    bg = pack_rgb(10, 12, 18)
    for y in range(h):
        screen.fill_row(y, " ", bg, FAR)
    screen.text(2, 1, "SPRITE CONTACT SHEET", pack_rgb(232, 196, 90))
    screen.text(2, 2, "true scale at 4.6 m", pack_rgb(150, 158, 176))
    step = 21
    x0 = 3
    bottom = 26
    for i, (model, pose, label, height) in enumerate(SHEET_ACTORS):
        sprite = atlas.get(model, pose, 0)
        if sprite is None:
            continue
        rows = max(4, int(height / 4.6 * 47.5 + 0.5))
        cx = x0 + i * step + step * 0.5
        screen.blit(sprite, cx, bottom, rows, tint=(1.0, 1.0, 1.0),
                    depth=6.0)
        screen.text(int(cx) - len(label) // 2, 27, label,
                    pack_rgb(200, 206, 220))
    screen.text(2, 29, "BAKE SOURCE (near 1:1)", pack_rgb(232, 196, 90))
    screen.text(25, 29, " Knight   Wolf   Skeleton   Captain   Torch   Fire",
                pack_rgb(150, 158, 176))
    cx = 2.0
    for model, pose, label in SHEET_NATIVE:
        sprite = atlas.get(model, pose, 0)
        if sprite is None:
            continue
        rows = min(28, max(12, sprite.h))
        cols = max(1.0, rows * sprite.w / sprite.h)
        cx += cols * 0.5
        if cx + cols * 0.5 > w - 1:
            break
        screen.blit(sprite, cx, 59, rows, tint=(1.0, 1.0, 1.0), depth=6.0)
        cx += cols * 0.5 + 2.0


PORTRAITS = (
    ("knight", "idle", "Knight", 40),
    ("skeleton", "idle", "Skeleton", 40),
    ("captain", "idle", "Captain", 52),
    ("wolf", "idle", "Wolf", 20),
)


def draw_portrait_sheet(screen, atlas):
    """A large detail study so model geometry can be judged up close."""
    w, h = screen.w, screen.h
    bg = pack_rgb(10, 12, 18)
    for y in range(h):
        screen.fill_row(y, " ", bg, FAR)
    screen.text(2, 0, "MODEL DETAIL STUDY (2-4x game scale)",
                pack_rgb(232, 196, 90))
    step = max(28, w // len(PORTRAITS))
    for i, (model, pose, label, rows) in enumerate(PORTRAITS):
        sprite = atlas.get(model, pose, 0)
        if sprite is None:
            continue
        cx = step * i + step * 0.5
        screen.text(int(cx) - len(label) // 2, 2, label,
                    pack_rgb(200, 206, 220))
        screen.blit(sprite, cx, int(h) - 2, rows, tint=(1.0, 1.0, 1.0),
                    depth=6.0)


def _glyph_stats(screen):
    glyphs = {}
    colors = set()
    filled = 0
    for y in range(screen.h):
        chars = screen.chars[y]
        fg = screen.fg[y]
        for x in range(screen.w):
            ch = chars[x]
            glyphs[ch] = glyphs.get(ch, 0) + 1
            colors.add(fg[x])
            if ch != " ":
                filled += 1
    return {"filled": filled, "colors": len(colors),
            "glyphs": dict(sorted(glyphs.items(), key=lambda kv: -kv[1])[:8])}


CLASS_LEGEND = ("k dark  b blue  g green  y gold  r red  m violet  "
                "c cyan  w grey  o other  . empty")


def _color_class(color):
    r = (color >> 16) & 255
    g = (color >> 8) & 255
    b = color & 255
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if lum < 26:
        return "k"
    if r > 120 and g > 95 and b < g * 0.75:
        return "y"
    if b > r * 1.22 and b > g * 1.08:
        return "b"
    if g > r * 1.16 and g > b * 1.10:
        return "g"
    if r > g * 1.30 and r > b * 1.30:
        return "r"
    if r > g * 1.10 and b > g * 1.10:
        return "m"
    if g > 90 and b > 90 and r < g * 0.86:
        return "c"
    if max(r, g, b) - min(r, g, b) < 28:
        return "w" if lum > 90 else "o"
    return "o"


def _top_colors(screen, limit=12):
    counts = {}
    for y in range(screen.h):
        for color in screen.fg[y]:
            counts[color] = counts.get(color, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return ["#%06x %d" % (color, count) for color, count in ranked]


def write_text_view(path, screen, name, day_t):
    """Write a terminal-readable mirror: glyphs, colour classes, palette."""
    step_x = max(1, screen.w // 60)
    step_y = max(1, screen.h // 30)
    rows = []
    for y in range(0, screen.h, step_y):
        rows.append("".join(_color_class(screen.fg[y][x])
                            for x in range(0, screen.w, step_x)))
    lines = ["SCENE %s %dx%d day=%.2f" % (name, screen.w, screen.h, day_t),
             "--- glyphs ---", screen.frame_text(),
             "--- colour classes (%d steps) ---" % step_x,
             CLASS_LEGEND, "\n".join(rows),
             "--- top colours ---", "\n".join(_top_colors(screen)), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _add_tutorial(game, name):
    p = game.world.player
    if name == "title":
        return
    p.inventory.add("potion", 1)
    if name in ("village", "dialogue"):
        game.world.quest = "active"
    if name == "combat":
        the_foe = next(e for e in game.world.entities
                       if getattr(e, "kind", "") == "wolf")
        game.world.add_damage_number(
            the_foe.x, the_foe.z,
            the_foe.ground_y + the_foe.height * 0.8,
            "17", QUEST_COLOR)
        game.world.add_message("Backstab! The wolf reels.", QUEST_COLOR)


def _tick(game, frames=1):
    env = Env(game.world.day_t, game.world.time)
    for _ in range(frames):
        game._handle_keys()
        game.world.update(game.dt, env)


def _key(game, token, frames=1):
    term = game.term
    term.pressed = [token]
    _tick(game, frames)


def _hold(game, held, frames):
    game.term.held = set(held)
    _tick(game, frames)
    game.term.held = set()


def probe_controls(game):
    """Drive the real input path and return a list of named check results."""
    game.term = ScriptedTerm(game.w, game.h)
    game.save_path = os.devnull
    checks = []

    def record(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as exc:
            record(name, False, "%s: %s" % (type(exc).__name__, exc))
            return
        record(name, ok, detail)

    _calm(game)
    _reset(game)

    def walk_forward():
        p = game.world.player
        z0 = p.z
        _hold(game, {"w"}, 6)
        moved = z0 - p.z
        return moved > 0.3 and p.moving, "dz=%.2f" % moved

    def arrow_walk_turn():
        p = game.world.player
        z0 = p.z
        _hold(game, {"up"}, 6)
        moved = z0 - p.z
        yaw0 = game.cam_yaw
        _hold(game, {"left"}, 2)
        turned = game.cam_yaw - yaw0
        return (moved > 0.3 and turned < -0.05,
                "dz=%.2f dyaw=%.2f" % (moved, turned))

    def strafe():
        p = game.world.player
        x0, z0 = p.x, p.z
        _hold(game, {"d"}, 6)
        return (abs(p.x - x0) > 0.3 and abs(p.z - z0) < 0.2,
                "dx=%.2f dz=%.2f" % (p.x - x0, p.z - z0))

    def sprint():
        p = game.world.player
        z0 = p.z
        _hold(game, {"w"}, 8)
        walk = z0 - p.z
        _reset(game, stamina=p.max_stamina)
        z1 = p.z
        _hold(game, {"w", "shift"}, 8)
        run = z1 - p.z
        return (run > walk * 1.2 and p.stamina < p.max_stamina,
                "walk=%.2f sprint=%.2f stamina=%.0f" % (walk, run, p.stamina))

    def guard_hold():
        _reset(game)
        _hold(game, {"b"}, 1)
        held = game.world.player.guarding
        _hold(game, set(), 1)
        released = game.world.player.guarding
        return held and not released, "held=%s released=%s" % (held, released)

    def guard_damage():
        p = game.world.player
        _reset(game)
        p.hp = 100
        game.world.hit_player(20, SimpleNamespace(name="Probe"))
        open_loss = 100 - p.hp
        _reset(game)
        p.hp = 100
        _hold(game, {"b"}, 1)
        game.world.hit_player(20, SimpleNamespace(name="Probe"))
        guard_loss = 100 - p.hp
        return (guard_loss < open_loss * 0.7 and p.stamina < 100.0,
                "open=%d guarded=%d stamina=%.0f" %
                (open_loss, guard_loss, p.stamina))

    def attack():
        p = game.world.player
        _reset(game)
        _key(game, "space")
        return (p.attacking and p.stamina <= p.max_stamina - 12,
                "attacking=%s stamina=%.0f" % (p.attacking, p.stamina))

    def potion():
        p = game.world.player
        _reset(game)
        p.inventory.add("potion", 1)
        p.hp = 5
        game._use_potion()
        started = p.heal_remaining > 0.0
        _hold(game, set(), 30)
        healed = 5.0 < p.hp < p.max_hp and p.heal_remaining < 60.0
        return (started and healed,
                "started=%s hp=%.1f/%d remaining=%.0f" %
                (started, p.hp, p.max_hp, p.heal_remaining))

    def menus():
        _reset(game)
        _key(game, "i")
        in_inventory = game.state == "inventory"
        _key(game, "e")
        _key(game, "i")
        back = game.state == "play"
        _key(game, "h")
        in_help = game.state == "help"
        _key(game, "x")
        _key(game, "esc")
        in_pause = game.state == "pause"
        _key(game, "esc")
        return (in_inventory and back and in_help and in_pause
                and game.state == "play",
                "inventory=%s help=%s pause=%s now=%s" %
                (in_inventory, in_help, in_pause, game.state))

    def map_toggle():
        _reset(game)
        before = game.show_map
        _key(game, "m")
        return game.show_map != before, "before=%s after=%s" % (
            before, game.show_map)

    def wheel_zoom():
        _reset(game)
        before = game.cam_dist
        game.term.mouse = [("wheel", 40, 20, 0, 1)]
        game._handle_keys()
        return game.cam_dist < before, "dist %.1f -> %.1f" % (
            before, game.cam_dist)

    def orbit():
        _reset(game)
        yaw0 = game.cam_yaw
        pitch0 = game.cam_pitch
        game.term.mouse = [("rdown", 40, 20, 0, 0),
                           ("move", 48, 24, 2, 0),
                           ("up", 48, 24, 0, 0)]
        game._handle_keys()
        return (game.cam_yaw > yaw0 + 0.2 and game.cam_pitch > pitch0,
                "dyaw=%.2f dpitch=%.2f" % (game.cam_yaw - yaw0,
                                           game.cam_pitch - pitch0))

    def click_walk():
        _reset(game)
        game._render(Env(game.world.day_t, game.world.time))
        target = None
        for row in range(6, game.h - 8):
            for col in range(6, game.w - 6):
                if game.pick_world(col, row) is not None:
                    target = (col, row)
                    break
            if target:
                break
        if target is None:
            return False, "no pickable ground"
        game.term.mouse = [("ldown", target[0], target[1], 1, 0),
                           ("up", target[0], target[1], 0, 0)]
        game._handle_keys()
        return game.walk_target is not None, "target=%s" % (target,)

    def keymap():
        cases = ((0x57, "w"), (0x20, "space"), (0x25, "left"),
                 (0x10, "shift"), (0x42, "b"), (0x0D, "enter"))
        bad = [(vk, tok) for vk, tok in cases if vk_token(vk, "\x00") != tok]
        return not bad, "mismatches=%s" % (bad,)

    def respawn():
        _reset(game)
        skel = next(e for e in game.world.entities
                    if getattr(e, "kind", "") == "skeleton")
        game.world.kill_actor(skel)
        queued = any(r["kind"] == "skeleton" for r in game.world.respawn)
        return queued, "queued=%s" % queued

    def shop_buy():
        _reset(game)
        p = game.world.player
        p.inventory.add("gold", 200)
        swords0 = p.inventory.count("iron_sword")
        gold0 = p.inventory.count("gold")
        game.state = "shop"
        game.shop_mode = "buy"
        game.shop_sel = 0
        _key(game, "space")
        bought = p.inventory.count("iron_sword") == swords0 + 1
        spent = gold0 - p.inventory.count("gold")
        return (bought and spent > 0,
                "bought=%s spent=%d" % (bought, spent))

    def shop_sell():
        _reset(game)
        p = game.world.player
        p.inventory.add("pelt", 1)
        pelts0 = p.inventory.count("pelt")
        gold0 = p.inventory.count("gold")
        goods = [iid for iid, _n in game.world.sellables()]
        if "pelt" not in goods:
            return False, "pelt missing from %s" % (goods,)
        game.state = "shop"
        game.shop_mode = "sell"
        game.shop_sel = goods.index("pelt")
        _key(game, "space")
        sold = p.inventory.count("pelt") == pelts0 - 1
        return (sold and p.inventory.count("gold") > gold0,
                "sold=%s gold %d -> %d" %
                (sold, gold0, p.inventory.count("gold")))

    check("walk_forward", walk_forward)
    check("arrow_walk_turn", arrow_walk_turn)
    check("strafe", strafe)
    check("sprint", sprint)
    check("guard_hold", guard_hold)
    check("guard_damage", guard_damage)
    check("attack_space", attack)
    check("potion_over_time", potion)
    check("menu_states", menus)
    check("map_toggle", map_toggle)
    check("wheel_zoom", wheel_zoom)
    check("orbit_drag", orbit)
    check("click_to_walk", click_walk)
    check("key_token_map", keymap)
    check("kill_queues_respawn", respawn)
    check("shop_buy", shop_buy)
    check("shop_sell", shop_sell)
    game.term = None
    return checks


def run_inspection(outdir, seed=7, width=132, height=60, terrain_size=None,
                   scale=2, scenes=None, probe=True, atlas_keys=None,
                   studio=True):
    """Write scene PNGs, the web studio and a mechanics report."""
    os.makedirs(outdir, exist_ok=True)
    t0 = time.monotonic()
    game = build_game(seed=seed, width=width, height=height,
                      terrain_size=terrain_size, atlas_keys=atlas_keys)
    boot_s = time.monotonic() - t0
    wanted = None if scenes is None else set(scenes)
    studio_frames = []
    manifest = {"seed": seed, "viewport": [game.w, game.h], "scale": scale,
                "boot_s": round(boot_s, 3), "scenes": [], "checks": [],
                "failed": [], "elapsed_s": 0.0}
    for name, filename, build in SCENES:
        if wanted is not None and name not in wanted:
            continue
        game.world.messages = []
        game.world.damage_numbers = []
        game.world.victory_shown = False
        game.show_map = True
        _calm(game)
        _reset(game)
        day_t = build(game)
        _add_tutorial(game, name)
        game._render(Env(day_t, game.world.time))
        path = os.path.join(outdir, filename)
        iw, ih = save_png(path, game.screen, scale=scale)
        text_path = os.path.join(outdir,
                                 filename.rsplit(".", 1)[0] + ".txt")
        write_text_view(text_path, game.screen, name, day_t)
        stats = _glyph_stats(game.screen)
        stats.update({"name": name, "file": filename,
                      "text": os.path.basename(text_path),
                      "pixels": [iw, ih], "day_t": day_t,
                      "top_colors": _top_colors(game.screen, 6)})
        manifest["scenes"].append(stats)
        studio_frames.append({"name": name, "day_t": day_t,
                              "frame": encode_screen(game.screen)})
    if wanted is None or "sprites" in wanted:
        sheet = Screen(game.w, game.h, color=True)
        draw_sprite_sheet(sheet, game.atlas)
        sheet_file = "15_sprites.png"
        sheet_path = os.path.join(outdir, sheet_file)
        iw, ih = save_png(sheet_path, sheet, scale=scale)
        text_path = os.path.join(outdir, "15_sprites.txt")
        write_text_view(text_path, sheet, "sprites", DAY)
        stats = _glyph_stats(sheet)
        stats.update({"name": "sprites", "file": sheet_file,
                      "text": "15_sprites.txt", "pixels": [iw, ih],
                      "day_t": DAY,
                      "top_colors": _top_colors(sheet, 6)})
        manifest["scenes"].append(stats)
        studio_frames.append({"name": "sprites", "day_t": DAY,
                              "frame": encode_screen(sheet)})
        portrait = Screen(game.w, game.h, color=True)
        draw_portrait_sheet(portrait, game.atlas)
        portrait_path = os.path.join(outdir, "16_portraits.png")
        iw, ih = save_png(portrait_path, portrait, scale=scale)
        write_text_view(os.path.join(outdir, "16_portraits.txt"), portrait,
                        "portraits", DAY)
        stats = _glyph_stats(portrait)
        stats.update({"name": "portraits", "file": "16_portraits.png",
                      "text": "16_portraits.txt", "pixels": [iw, ih],
                      "day_t": DAY,
                      "top_colors": _top_colors(portrait, 6)})
        manifest["scenes"].append(stats)
        studio_frames.append({"name": "portraits", "day_t": DAY,
                              "frame": encode_screen(portrait)})
    if probe:
        manifest["checks"] = probe_controls(game)
        manifest["failed"] = [c["name"] for c in manifest["checks"]
                              if not c["ok"]]
    if studio and studio_frames:
        html_path, data_path = write_studio(
            outdir, seed, [game.w, game.h], studio_frames,
            collect_models(game.atlas), manifest["checks"])
        manifest["studio"] = os.path.relpath(html_path, outdir)
        manifest["studio_data"] = os.path.relpath(data_path, outdir)
    manifest["elapsed_s"] = round(time.monotonic() - t0, 3)
    report_path = os.path.join(outdir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    manifest["report_path"] = report_path
    return manifest


def format_summary(report):
    """One-line human summary for the CLI."""
    passed = sum(1 for c in report["checks"] if c["ok"])
    total = len(report["checks"])
    line = ("inspect: %d scene(s), %d/%d checks pass, %.1fs -> %s"
            % (len(report["scenes"]), passed, total,
               report["elapsed_s"], os.path.dirname(report["report_path"])))
    if report["failed"]:
        line += "\nfailed: " + ", ".join(report["failed"])
    return line
