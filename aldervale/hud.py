"""HUD and menu rendering: bars, minimap, dialogue, shop, inventory, titles."""

import math

from .buffer import pack_rgb
from .rules import ITEMS, SHOP_STOCK, WEAPON_ORDER, ARMOR_ORDER, xp_for_level

WHITE = pack_rgb(216, 220, 228)
GOLD = pack_rgb(232, 196, 90)
RED = pack_rgb(226, 84, 74)
GREEN = pack_rgb(120, 220, 130)
BLUE = pack_rgb(120, 160, 230)
GREY = pack_rgb(140, 144, 156)
DIM = pack_rgb(96, 100, 112)
ORANGE = pack_rgb(240, 160, 90)
PURPLE = pack_rgb(190, 150, 230)

TITLE_LOGO = [
    r"  AAA  L   DDDD  EEEE  RRRR  VVVV  AAA  L   EEEE ",
    r" A   A L   D   D E    R   R V  V A   A L   E    ",
    r" AAAAA L   D   D EEE  RRRR  V  V AAAAA L   EEE  ",
    r" A   A L   D   D E    R  R  V  V A   A L   E    ",
    r" A   A LLL DDDD  EEEE R   R  V   A   A LLL EEEE ",
]

CONTROLS = [
    "W S or Up Down   walk          A D   sidestep",
    "Left / Right     turn the camera",
    "Right-drag       orbit and tilt the camera",
    "Left-click       walk / talk / attack",
    "Wheel            zoom the camera",
    "Hold Shift       sprint        SPACE  swing your sword",
    "Hold B           guard         (blocks most damage, spends stamina)",
    "E or Enter       talk / open / take / pray",
    "I  inventory     M  map        + -    zoom (keys)",
    "F1 or H  help    ESC  pause menu",
]

CONTROLS_COMPACT = [
    "WASD or Arrows  walk",
    "A D  sidestep    Left/Right  turn",
    "Right-drag  look    Wheel  zoom",
    "Click  walk / talk / attack",
    "SPACE attack    Hold B guard",
    "Shift sprint    E talk / take",
    "I bag    M map    H help",
    "ESC pause menu",
]


def wrap_text(text, width):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines


def bar(screen, x, y, width, label, cur, mx, color, show_num=True):
    """An ASCII gauge: label, hashed fill and numeric readout."""
    cur = max(0, cur)
    filled = 0 if mx <= 0 else int(width * min(1.0, cur / mx) + 0.5)
    text = "%-9s|%s|%s" % (label, "#" * filled, "-" * (width - filled))
    if show_num:
        text += " %d/%d" % (cur, mx)
    screen.text(x, y, text, color)


def draw_hud(screen, world, env, fps, show_map=True):
    p = world.player
    w, h = screen.w, screen.h
    inv = p.inventory
    screen.text(1, h - 5, "%s  Lv%d" % (p.name, p.level), WHITE)
    screen.text(20, h - 5, "Gold %d" % inv.count("gold"), GOLD)
    if w >= 60:
        weapon = ITEMS[inv.weapon]
        label = ("%s (atk %d)" % (weapon.name, weapon.atk) if w >= 92
                 else weapon.name)
        screen.text(32, h - 5, label, GREY)
    if w >= 92:
        armor = ITEMS[inv.armor]
        screen.text(58, h - 5, "%s (def %d)" % (armor.name, armor.dfn), GREY)
    if w >= 110:
        phase = "Dawn" if env.warm > 0.4 and env.daylight > 0.3 else (
            "Day" if env.daylight > 0.5 else ("Dusk" if env.warm > 0.3
                                              else "Night"))
        screen.text(w - 22, h - 5, "%-6s %2d fps" % (phase, fps), DIM)
    if w >= 80:
        bar(screen, 1, h - 4, 12, "HP", p.hp, p.max_hp,
            GREEN if p.hp > p.max_hp * 0.35 else RED)
        bar(screen, 32, h - 4, 10, "Stam", p.stamina, p.max_stamina, BLUE,
            show_num=False)
        bar(screen, 55, h - 4, 14, "XP", p.xp,
            xp_for_level(p.level), PURPLE, show_num=False)
        if w >= 92:
            bar(screen, 82, h - 4, 6, "Pot", inv.count("potion"), 9, ORANGE,
                show_num=True)
        else:
            screen.text(w - 7, h - 5, "Pot %d" % inv.count("potion"), ORANGE)
        quest_y = h - 3
    elif w >= 64:
        bar(screen, 1, h - 4, 12, "HP", p.hp, p.max_hp,
            GREEN if p.hp > p.max_hp * 0.35 else RED)
        bar(screen, 32, h - 4, 10, "Stam", p.stamina, p.max_stamina, BLUE,
            show_num=False)
        screen.text(w - 7, h - 5, "Pot %d" % inv.count("potion"), ORANGE)
        quest_y = h - 3
    else:
        bar(screen, 1, h - 4, 12, "HP", p.hp, p.max_hp,
            GREEN if p.hp > p.max_hp * 0.35 else RED)
        bar(screen, 1, h - 3, 10, "Stam", p.stamina, p.max_stamina, BLUE,
            show_num=False)
        screen.text(w - 7, h - 4, "Pot %d" % inv.count("potion"), ORANGE)
        quest_y = h - 2
    screen.text(1, quest_y, "Quest: " + world.quest_objective(),
                pack_rgb(222, 200, 140))
    draw_location(screen, world)
    if getattr(p, "guarding", False):
        screen.text(w - 10, h - 6, "GUARDING", BLUE)
    if show_map and w >= 96 and h >= 30:
        draw_minimap(screen, world)
    y = h - 7
    for text, color, age in world.messages[-4:]:
        fade = max(0.25, 1.0 - age / 8.0)
        screen.text(1, y, text[:w - 30], color if fade > 0.5 else DIM)
        y -= 1


LOCATION_RADIUS = 30.0


def location_name(world):
    """The place the player is standing in, for the HUD banner."""
    p = world.player
    ter = world.terrain
    places = (("Aldervale", ter.village, 26.0),
              ("Suncrest Castle", ter.castle, 32.0),
              ("The Bone Camp", ter.camp, 24.0))
    best = None
    for name, (x, z), radius in places:
        d2 = (p.x - x) ** 2 + (p.z - z) ** 2
        if d2 <= radius * radius and (best is None or d2 < best[0]):
            best = (d2, name)
    if best is not None:
        return best[1]
    if ter.is_path(p.x, p.z):
        return "The Old Road"
    if ter.forest_at(p.x, p.z):
        return "Whispering Wood"
    return "The Vale"


def draw_location(screen, world):
    """Small gold place-name plate in the top-left corner."""
    if screen.w < 64 or screen.h < 24:
        return
    base = location_name(world)
    weather = getattr(world, "weather", "clear")
    extra = "" if weather == "clear" else "  " + weather
    label = base + extra
    if len(label) > screen.w - 6:
        label, extra = base, ""
    plate = pack_rgb(8, 11, 18)
    for x in range(1, min(screen.w - 1, len(label) + 4)):
        screen.set(x, 1, " ", plate, 0.5)
    screen.text(2, 1, base, GOLD)
    if extra:
        screen.text(2 + len(base), 1, extra, pack_rgb(154, 184, 218))
    screen.set(1, 2, "~", GREY, 0.5)
    for x in range(2, min(screen.w - 1, len(label) + 2)):
        screen.set(x, 2, "~" if (x & 1) else "-", GREY, 0.5)


def draw_minimap(screen, world):
    """Coarse terrain map with entity markers, top-right."""
    p = world.player
    mw, mh = 26, 12
    x0 = screen.w - mw - 2
    y0 = 1
    ter = world.terrain
    step = 4.6
    half_w = mw * step * 0.5
    half_h = mh * step * 0.5
    for my in range(mh):
        for mx in range(mw):
            wx = p.x - half_w + mx * step
            wz = p.z - half_h + my * step * 2.0
            if not ter.in_bounds(wx, wz):
                c = pack_rgb(18, 30, 48)
            else:
                gh = ter.height(wx, wz)
                c = ter.color(wx, wz)
                if gh <= ter.water:
                    c = pack_rgb(30, 60, 96)
                c = pack_rgb(((c >> 16) & 255) * 0.75,
                             ((c >> 8) & 255) * 0.75, (c & 255) * 0.75)
            screen.set(x0 + mx, y0 + my, ".", c, -2.0)
    kx, kz = ter.castle
    cx, cz = ter.camp
    vx, vz = ter.village
    for ex, ez, ch, col in ((kx, kz, "C", BLUE), (cx, cz, "X", RED),
                            (vx, vz, "V", GOLD)):
        mx = int((ex - p.x + half_w) / step)
        my = int((ez - p.z + half_h) / (step * 2.0))
        if 0 <= mx < mw and 0 <= my < mh:
            screen.set(x0 + mx, y0 + my, ch, col, -3.0)
    for e in world.entities:
        kind = getattr(e, "kind", None)
        if kind in ("wolf", "bandit", "skeleton", "captain"):
            ch = "x"
            col = RED
        elif kind == "villager":
            ch = "o"
            col = GOLD
        else:
            continue
        if math.hypot(e.x - p.x, e.z - p.z) > 80.0:
            continue
        mx = int((e.x - p.x + half_w) / step)
        my = int((e.z - p.z + half_h) / (step * 2.0))
        if 0 <= mx < mw and 0 <= my < mh:
            screen.set(x0 + mx, y0 + my, ch, col, -3.0)
    mx = int(half_w / step)
    my = int(half_h / (step * 2.0))
    screen.set(x0 + mx, y0 + my, "@", WHITE, -4.0)
    screen.box(x0 - 1, y0 - 1, mw + 2, mh + 2, GREY)
    screen.set(x0 + mw // 2, y0 - 1, "N", GOLD, -5.0)


def project_marker(screen, world, cam, wx, wy, wz):
    """World position to screen cell; returns (col, row) or None."""
    dx = wx - cam.x
    dz = wz - cam.z
    sin_y = math.sin(cam.yaw)
    cos_y = math.cos(cam.yaw)
    depth = dx * sin_y + dz * cos_y
    if depth < 0.7:
        return None
    side = dx * cos_y - dz * sin_y
    col = int(cam.w * 0.5 + side / depth * cam.f)
    row = int(cam.horizon - (wy - cam.y) / depth * cam.fy)
    if 0 <= col < screen.w and 0 <= row < screen.h:
        return col, row
    return None


def draw_world_overlays(screen, world, cam):
    """Damage numbers and the interaction prompt, anchored in the world."""
    for d in world.damage_numbers:
        pos = project_marker(screen, world, cam, d["x"], d["y"] + d["t"] * 0.4,
                             d["z"])
        if pos:
            alpha = 1.0 - d["t"]
            x = min(max(0, pos[0] - len(d["text"]) // 2),
                    max(0, screen.w - len(d["text"])))
            screen.text(x, pos[1], d["text"],
                        d["color"] if alpha > 0.4 else DIM)
    target = world.interact_target()
    if target is not None and not world.player.dead:
        if target.model == "shrine":
            label = "[E] Pray at the shrine"
        elif hasattr(target, "item_id"):
            item = ITEMS.get(target.item_id, ItemStub(target.item_id))
            label = "[E] Take " + item.name
        elif getattr(target, "ai_kind", "") in ("villager", "guard"):
            label = "[E] Talk to " + (target.name or "villager")
        elif hasattr(target, "opened"):
            label = "[E] Open the chest"
        else:
            label = "[E] Interact"
        wy = target.ground_y + target.height * target.scale + 0.5
        pos = project_marker(screen, world, cam, target.x, wy, target.z)
        if pos:
            label = fit_text(label, screen.w - 2)
            x = min(max(0, pos[0] - len(label) // 2),
                    max(0, screen.w - len(label)))
            screen.text(x, max(0, pos[1] - 1), label, WHITE)


class ItemStub:
    def __init__(self, item_id):
        self.name = item_id.replace("_", " ").title()


def fit_text(text, width):
    """Clip one line to the available width without splitting a border."""
    if width <= 0:
        return ""
    return text if len(text) <= width else text[:width]


def panel_bounds(screen, margin_x=2, margin_y=1):
    """A margin-clamped panel rectangle: (x, y, width, height)."""
    w, h = screen.w, screen.h
    bw = max(10, w - margin_x * 2)
    bh = max(6, h - margin_y * 2)
    return margin_x, margin_y, bw, bh


def centered_panel(screen, max_w, want_h, margin_x=2, margin_y=1):
    """A centred panel no wider than max_w and no taller than want_h."""
    w, h = screen.w, screen.h
    bw = max(10, min(max_w, w - margin_x * 2))
    bh = max(6, min(want_h, h - margin_y * 2))
    bx = (w - bw) // 2
    by = max(margin_y, (h - bh) // 2)
    return bx, by, bw, bh


def panel_text(screen, bx, bw, y, text, color):
    """Draw one line centred inside a panel, clipped to its interior."""
    line = fit_text(text, max(0, bw - 4))
    screen.text(bx + (bw - len(line)) // 2, y, line, color)


def draw_dialogue(screen, world, dlg, page, choice_idx):
    """Bottom dialogue box with the current page and choices."""
    w, h = screen.w, screen.h
    bw = min(74, w - 4)
    bx = (w - bw) // 2
    bh = min(h - 2, 9 + len(dlg["choices"]))
    by = max(1, h - bh - 1)
    screen.box(bx, by, bw, bh, GREY, fill=" ")
    screen.text(bx + 2, by + 1, fit_text(dlg["name"] + " says:", bw - 4), GOLD)
    text = dlg["pages"][page]
    for i, line in enumerate(wrap_text(text, bw - 5)[:3]):
        screen.text(bx + 2, by + 3 + i, line, WHITE)
    if page < len(dlg["pages"]) - 1:
        screen.text(bx + bw - 14, by + bh - 2, "[SPACE] more", DIM)
    else:
        cy = by + 7
        for i, (label, _action) in enumerate(dlg["choices"]):
            if cy + i >= by + bh - 1:
                break
            marker = ">" if i == choice_idx else " "
            screen.text(bx + 3, cy + i,
                        fit_text("%s[%d] %s" % (marker, i + 1, label),
                                 bw - 5),
                        WHITE if i == choice_idx else GREY)


def _shop_row(idx, item, sel, inner):
    """One ware line whose columns degrade as the panel narrows."""
    mark = ">" if idx == sel else " "
    stat = ""
    if item.kind == "weapon":
        stat = "atk %d" % item.atk
    elif item.kind == "armor":
        stat = "def %d" % item.dfn
    elif item.kind == "potion":
        stat = "heals %d" % item.heal
    if inner >= 62:
        head = "%s[%d] %-16s %-10s %4d gold  " % (
            mark, idx + 1, item.name, stat, item.price)
        return fit_text(head + item.desc, inner)
    if inner >= 34:
        return fit_text("%s[%d] %-14s %-8s %4d gold" %
                        (mark, idx + 1, item.name, stat, item.price), inner)
    return fit_text("%s[%d] %-13s %4d" %
                    (mark, idx + 1, item.name, item.price), inner)


def draw_shop(screen, world, mode, sel, message):
    sellables = world.sellables()
    rows_needed = (len(SHOP_STOCK) if mode == "buy"
                   else max(1, min(12, len(sellables))))
    want_h = 11 + rows_needed
    bx, by, bw, bh = centered_panel(screen, 96, want_h)
    inner = bw - 4
    cx = bx + 2
    screen.box(bx, by, bw, bh, GREY, fill=" ")
    panel_text(screen, bx, bw, by + 1, "BRAM'S FORGE", GOLD)
    y = by + 3
    screen.text(cx, y, fit_text("Your gold: %d" %
                                world.player.inventory.count("gold"), inner),
                GOLD)
    y += 1
    for line in wrap_text("[TAB] buy/sell   [SPACE] confirm   [ESC] leave",
                          inner)[:2]:
        screen.text(cx, y, line, DIM)
        y += 1
    if message:
        for line in wrap_text(message, inner)[:2]:
            screen.text(cx, y, line, WHITE)
            y += 1
    y += 1
    limit = by + bh - 1
    if mode == "buy":
        screen.text(cx, y, fit_text("-- Wares for sale --", inner), WHITE)
        y += 1
        rows = max(1, limit - y)
        start = 0
        if len(SHOP_STOCK) > rows:
            start = max(0, min(sel - rows + 1, len(SHOP_STOCK) - rows))
        for i, item_id in enumerate(SHOP_STOCK[start:start + rows]):
            idx = start + i
            screen.text(cx, y + i,
                        _shop_row(idx, ITEMS[item_id], sel, inner),
                        WHITE if idx == sel else GREY)
    else:
        screen.text(cx, y, fit_text("-- Your goods (half price) --", inner),
                    WHITE)
        y += 1
        if not sellables:
            screen.text(cx + 2, y, "Nothing to sell.", GREY)
            return
        rows = max(1, limit - y)
        start = 0
        if len(sellables) > rows:
            start = max(0, min(sel - rows + 1, len(sellables) - rows))
        for i, (iid, n) in enumerate(sellables[start:start + rows]):
            idx = start + i
            item = ITEMS.get(iid, ItemStub(iid))
            mark = ">" if idx == sel else " "
            line = fit_text("%s[%d] %-16s x%d  -> %d gold" %
                            (mark, idx + 1, item.name, n,
                             max(1, item.price // 2)), inner)
            screen.text(cx, y + i, line, WHITE if idx == sel else GREY)


def draw_inventory(screen, world, message):
    p = world.player
    inv = p.inventory
    status = []
    if screen.w >= 62:
        status.append(("Level %d   HP %d/%d   Atk %d (+%d)   Def %d (+%d)" % (
            p.level, p.hp, p.max_hp, p.atk, inv.weapon_atk(), p.dfn,
            inv.armor_dfn()), WHITE))
    else:
        status.append(("Level %d   HP %d/%d" % (p.level, p.hp, p.max_hp),
                       WHITE))
        status.append(("Atk %d (+%d)   Def %d (+%d)" % (
            p.atk, inv.weapon_atk(), p.dfn, inv.armor_dfn()), WHITE))
    status.append(("Gold %d" % inv.count("gold"), GOLD))
    status.append(("Weapon: %s" % ITEMS[inv.weapon].name, WHITE))
    status.append(("Armor : %s" % ITEMS[inv.armor].name, WHITE))
    inner_guess = min(84, screen.w - 4) - 4
    if message:
        for line in wrap_text(message, inner_guess)[:2]:
            status.append((line, GREEN))
    items = sorted(inv.counts.items())
    want_h = len(status) + max(1, len(items)) + 9
    bx, by, bw, bh = centered_panel(screen, 84, want_h)
    inner = bw - 4
    cx = bx + 2
    screen.box(bx, by, bw, bh, GREY, fill=" ")
    panel_text(screen, bx, bw, by + 1, "SATCHEL OF SER ALARIC", GOLD)
    y = by + 3
    limit = by + bh - 4
    for text, color in status:
        if y >= limit:
            break
        screen.text(cx, y, fit_text(text, inner), color)
        y += 1
    y += 1
    if y < limit:
        screen.text(cx, y, "-- Satchel --", WHITE)
        y += 1
    if not items and y < limit:
        screen.text(cx + 2, y, "Empty but for crumbs.", GREY)
        y += 1
    rows_left = max(0, limit - y)
    hidden = 0
    if len(items) > rows_left and rows_left > 0:
        hidden = len(items) - (rows_left - 1)
        items = items[:rows_left - 1]
    for iid, n in items:
        item = ITEMS.get(iid, ItemStub(iid))
        hint = "[U] use" if getattr(item, "kind", "") == "potion" else ""
        screen.text(cx, y, fit_text("%s x%d  %s" % (item.name, n, hint),
                                    inner), GREY)
        y += 1
    if hidden and y < limit:
        screen.text(cx, y, "... and %d more" % hidden, DIM)
    known_w = [wid for wid in WEAPON_ORDER if inv.count(wid)]
    known_a = [aid for aid in ARMOR_ORDER if inv.count(aid)]
    footer = ("[U] drink potion   [E] equip best gear (%d wpn, %d arm)" %
              (len(known_w), len(known_a)))
    if len(footer) > inner:
        footer = "[U] potion   [E] equip best"
    screen.text(cx, by + bh - 3, fit_text(footer, inner), DIM)
    screen.text(cx, by + bh - 2, "[I] or [ESC] close", DIM)


def draw_help(screen):
    w, h = screen.w, screen.h
    bw = min(62, w - 4)
    bx = (w - bw) // 2
    inner = bw - 4
    source = (CONTROLS_COMPACT if (w < 52 or h < 26) else CONTROLS)
    body = []
    for line in source:
        body.extend(wrap_text(line, inner))
    body.append("")
    body.extend(wrap_text("Talk to Elder Quill by the shrine to begin.", inner))
    bh = min(h - 2, len(body) + 5)
    by = max(1, (h - bh) // 2)
    screen.box(bx, by, bw, bh, GREY, fill=" ")
    panel_text(screen, bx, bw, by + 1, "HOW TO BE A HERO", GOLD)
    for i, line in enumerate(body[:bh - 5]):
        screen.text(bx + 2, by + 3 + i, fit_text(line, inner), WHITE)
    screen.text(bx + 2, by + bh - 2, fit_text("[H] or [ESC] close", inner),
                DIM)


def title_menu_top(screen):
    """First row of the title menu, shared by drawing and mouse hit-testing."""
    w, h = screen.w, screen.h
    logo_w = max(len(line) for line in TITLE_LOGO)
    if w >= logo_w + 2 and h >= 26:
        return 14
    return max(5, h // 2 - 4)


def draw_title(screen, world, cam, env, menu_sel, has_save):
    w, h = screen.w, screen.h
    render_note = "maximize the window and shrink the font (Ctrl+Minus) for finer detail"
    logo_w = max(len(line) for line in TITLE_LOGO)
    if w >= logo_w + 2 and h >= 26:
        for i, line in enumerate(TITLE_LOGO):
            screen.text_centered(5 + i, line, GOLD if i < 3 else ORANGE)
        screen.text_centered(11, "A tale of steel and starlight, told in ASCII",
                             WHITE)
    else:
        screen.text_centered(max(2, h // 2 - 8), "ALDERVALE", GOLD)
        screen.text_centered(max(3, h // 2 - 6),
                             fit_text("A tale of steel and starlight", w - 2),
                             WHITE)
    y = title_menu_top(screen)
    opts = ["[N]ew game",
            "[C]ontinue" if has_save else "[C]ontinue (no save)",
            "[H]elp", "[Q]uit"]
    for i, opt in enumerate(opts):
        row = y + i
        if row >= h - 2:
            break
        marker = "> " if i == menu_sel else "  "
        label = fit_text(marker + opt, w - 2)
        start = max(0, (w - len(label)) // 2)
        for px in range(max(0, start - 2), min(w, start + len(label) + 2)):
            screen.set(px, row, " ", pack_rgb(8, 11, 18))
        screen.text_centered(row, label, WHITE if i == menu_sel else GREY)
    screen.text_centered(h - 2, fit_text("ALDERVALE v1.0 - an AIKit project",
                                         w - 2), DIM)
    controls = wrap_text("WASD walk . SPACE attack . E talk . I bag . H help",
                         w - 4)[:2]
    note = wrap_text(render_note, w - 4)[:2]
    row = h - 3
    for line in reversed(note):
        screen.text_centered(row, line, DIM)
        row -= 1
    for line in reversed(controls):
        screen.text_centered(row, line, DIM)
        row -= 1


def draw_death(screen, world):
    w, h = screen.w, screen.h
    bw = min(44, w - 4)
    bh = 8
    bx = (w - bw) // 2
    by = max(1, min(h - bh - 1, h // 2 - 4))
    screen.box(bx, by, bw, bh, RED, fill=" ")
    panel_text(screen, bx, bw, by + 2, "YOU HAVE FALLEN", RED)
    message = ("The shrine light carries you home." if bw >= 40
               else "The shrine carries you home.")
    panel_text(screen, bx, bw, by + 4, message, WHITE)
    panel_text(screen, bx, bw, by + 5, "press any key", GREY)


def draw_pause(screen, sel):
    w, h = screen.w, screen.h
    opts = ["[C]ontinue", "[S]ave and quit to title", "[H]elp",
            "[Q]uit without saving"]
    bw = min(40, w - 4)
    bh = 4 + len(opts)
    bx = (w - bw) // 2
    by = max(1, min(h - bh - 1, h // 2 - 5))
    screen.box(bx, by, bw, bh, GREY, fill=" ")
    panel_text(screen, bx, bw, by + 1, "- PAUSED -", WHITE)
    for i, opt in enumerate(opts):
        marker = "> " if i == sel else "  "
        panel_text(screen, bx, bw, by + 3 + i, marker + opt,
                   WHITE if i == sel else GREY)


def draw_victory(screen, world, t):
    if t > 9.0:
        return
    alpha = max(0.0, min(1.0, (9.0 - t) / 2.0))
    col = GOLD if alpha > 0.5 else DIM
    w, h = screen.w, screen.h
    bw = min(56, w - 4)
    bh = 9
    bx = (w - bw) // 2
    by = max(1, min(h - bh - 1, 5))
    screen.box(bx, by, bw, bh, col, fill=" ")
    panel_text(screen, bx, bw, by + 2, "THE SUNCREST IS HOME", col)
    panel_text(screen, bx, bw, by + 4, "Aldervale shines warm again.", WHITE)
    panel_text(screen, bx, bw, by + 5, "Ser Alaric, hero of the vale!", WHITE)
    panel_text(screen, bx, bw, by + 7, "The realm is yours to roam.", GREY)


def draw_hurt_vignette(screen, world):
    """A brief red edge vignette that never wipes HUD text."""
    if world.player.hurt_t <= 0.0:
        return
    k = min(1.0, world.player.hurt_t / 0.4)
    col = pack_rgb(200 * k + 30, 40, 40)
    w, h = screen.w, screen.h
    edge = 2 + int(5 * k)
    for y in range(h):
        for x in range(edge):
            for px in (x, w - 1 - x):
                if ((px * 11 + y * 7) & 7) > 2 + 4 * k:
                    continue
                if px < 0 or px >= w:
                    continue
                base = screen.fg[y][px]
                screen.fg[y][px] = pack_rgb(
                    (((base >> 16) & 255) + (((col >> 16) & 255) -
                                             ((base >> 16) & 255)) * 0.6),
                    (((base >> 8) & 255) + (((col >> 8) & 255) -
                                            ((base >> 8) & 255)) * 0.6),
                    ((base & 255) + ((col & 255) - (base & 255)) * 0.6))
                if x == 0:
                    screen.chars[y][px] = ":" if y & 1 else "."
