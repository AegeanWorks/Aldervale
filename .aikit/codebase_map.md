# Codebase Map & Symbol Catalog 🗺️

> **AUTO-GENERATED & VERIFIED BY `scripts/update_knowledge_base.py`**
> This document provides an automated, up-to-date registry of all modules, classes, and exported functions across this repository.

---

## 📊 Codebase Metrics
- **Total Python Modules**: `25`
- **Total Classes**: `60`
- **Total Top-Level Functions**: `186`
- **Total Class Methods**: `375`
- **Total Source Lines**: `11166`

---

## 📦 Modules & Exported Symbols

### [`aldervale/__init__.py`](aldervale/__init__.py)
> *ALDERVALE: a 2.5D medieval RPG rendered entirely in tiny ASCII cells.*

**Size**: `3` lines (`99` bytes)

---

### [`aldervale/__main__.py`](aldervale/__main__.py)
> *ALDERVALE command line entry point.*

**Size**: `304` lines (`13034` bytes)

**Functions:**
- `def _build_parser()`
- `def _fail(what, why, fix)`
- `def run(argv)`
- `def _web_shot(args)`
- `def _play(game, demo)`
- `def _screenshot(game, path)` - *Render one scripted vista to a plain text file (no terminal).*
- `def _benchmark(game)`
- `def _headless_demo(game, secs)` - *Non-interactive demo parity for pipes and CI (PRINCIPLE-015).*

---

### [`aldervale/atlas.py`](aldervale/atlas.py)
> *Sprite atlas: bakes every (model, pose, yaw) combination at load time.*

**Size**: `201` lines (`9460` bytes)

**Classes:**
- `class SpriteAtlas` - *Baked sprite frames lookup: (model_key, pose_name) -> [yaw frames].*
  - Method `.__init__(yaw_steps)`
  - Method `.build(progress, keys)`
  - Method `.get(model, pose, frame)`
  - Method `.yaw_frame(ent_yaw, cam_yaw)`

**Functions:**
- `def _spec(builder, poses, size, height, cells, dist, kwargs)`

---

### [`aldervale/buffer.py`](aldervale/buffer.py)
> *Char-cell frame buffer: per-cell glyph, 24-bit colour and depth, diff flush.*

**Size**: `267` lines (`9166` bytes)

**Classes:**
- `class Screen` - *A w x h grid of characters with colour, depth and diff-based output.*
  - Method `.__init__(w, h, color)`
  - Method `.clear()`
  - Method `.invalidate()`
  - Method `.in_bounds(x, y)`
  - Method `.set(x, y, ch, color, depth)`
  - Method `.fill_row(y, ch, color, depth)`
  - Method `.text(x, y, s, color)`
  - Method `.text_centered(y, s, color)`
  - Method `.box(x, y, w, h, color, fill)`
  - Method `.blit(sprite, cx, bottom_row, target_rows, tint, depth, flash, alpha)` - *Draw a baked sprite anchored at (cx, bottom_row) scaled to target_rows.*
  - Method `.frame_text()`
  - Method `.flush(term)` - *Emit only changed cells; returns the number of bytes written.*
  - Method `.stats()`

**Functions:**
- `def pack_rgb(r, g, b)` - *Pack float channels into 0xRRGGBB, clamping overflow to 0..255.*
- `def unpack_rgb(c)`
- `def lerp_color(c1, c2, t)`
- `def scale_color(c, k)`

---

### [`aldervale/capture.py`](aldervale/capture.py)
> *Headless frame capture: turn a char-cell Screen into a truecolor PNG.*

**Size**: `198` lines (`6613` bytes)

**Functions:**
- `def _scaled(color, factor)`
- `def _blend(base, over, alpha)`
- `def _cell_bytes(ch, color, scale, cache)`
- `def screen_pixels(screen, scale)` - *Return (width, height, rgb_bytes) for a Screen at the given cell scale.*
- `def _chunk(tag, payload)`
- `def png_bytes(width, height, rgb_rows)` - *Encode raw RGB scanlines (no filter byte) as a PNG byte string.*
- `def save_png(path, screen, scale)` - *Write a Screen to a truecolor PNG; return (width, height).*

---

### [`aldervale/entities.py`](aldervale/entities.py)
> *World entities: props, pickups, ambient life and AI-driven actors.*

**Size**: `335` lines (`11910` bytes)

**Classes:**
- `class Entity` - *Anything the renderer draws as a billboard.*
  - Method `.__init__(eid, model, x, z, height, yaw, scale, y_off, pose, name, solid, radius)`
- `class Prop` - *Static scenery.*
- `class Pickup` - *Ground loot bobbing gently; gold is collected by walking over it.*
  - Method `.__init__(eid, item_id, amount, x, z, height, quest)`
- `class Chest` - *A loot chest; opening swaps the sprite and grants contents once.*
  - Method `.__init__(eid, x, z, loot)`
- `class Actor` - *A creature or person with stats and a simple state machine.*
  - Method `.__init__(eid, model, x, z, height, *, kind, hp, atk, dfn, speed, xp_reward, aggro_r, attack_range, attack_dmg, home_r, scale, drops, ai_kind, name, radius, windup_s, cd_base)`
  - Property `.dead`
- `class Player` - *The hero: an Actor plus inventory, stamina and quest-facing state.*
  - Method `.__init__(eid, x, z)`
  - Property `.attacking`

**Functions:**
- `def _pickup_model(item_id)`
- `def eid_hash(eid)`
- `def move_actor(actor, dx, dz, world, dt)` - *Move with terrain, water and solid-entity collision; updates ground.*
- `def face_towards(actor, tx, tz)`
- `def update_actor(actor, dt, world, env)` - *Run one actor's AI state machine for this frame.*
- `def _walk_to(actor, tx, tz, world, dt, speed_factor)`
- `def _update_chicken(actor, dt, world)`
- `def _update_villager(actor, dt, world)`

---

### [`aldervale/game.py`](aldervale/game.py)
> *Game shell: states, input, camera, main loop, demo autopilot.*

**Size**: `660` lines (`23515` bytes)

**Classes:**
- `class Game` - *Drives one play session from title screen to victory.*
  - Method `.__init__(seed, width, height, fps, color, demo_secs, benchmark, save_path, terrain_size)`
  - Method `.boot(term, progress)` - *Bake sprites and build the world; call before run().*
  - Method `._open_screen()`
  - Method `._ensure_camera()`
  - Method `._update_camera(force)`
  - Method `.run()` - *Main loop until the player quits or the demo expires.*
  - Method `.tick(dt)` - *Advance one simulation step and return the frame environment.*
  - Method `._sync_death()` - *Enter the dead game state once the player actor has fallen.*
  - Method `._tick_fps(now)`
  - Method `._poll_resize()`
  - Method `._demo_steer(dt)`
  - Method `._handle_keys()`
  - Method `.reset_pointer_state()` - *Drop any pending drag, click or walk target (used on scene changes).*
  - Method `._on_mouse(ev)`
  - Method `._on_title_mouse(kind, col, row)`
  - Method `._activate_title(index)`
  - Method `.pick_world(col, row)` - *Screen cell to a world point using the depth buffer.*
  - Method `._click_at(col, row)`
  - Method `._apply_movement_held(held)` - *Continuous movement, turning, guard and sprint from held keys.*
  - Method `._movement(fwd, side, sprint)`
  - Method `._try_attack()`
  - Method `._try_interact()`
  - Method `._use_potion()`
  - Method `._equip_best()`
  - Method `._key_play(key)`
  - Method `._key_title(key)`
  - Method `._key_dialogue(key)`
  - Method `._key_shop(key)`
  - Method `._key_inventory(key)`
  - Method `._key_help(key)`
  - Method `._key_pause(key)`
  - Method `._key_dead(key)`
  - Method `._render(env)`

---

### [`aldervale/hud.py`](aldervale/hud.py)
> *HUD and menu rendering: bars, minimap, dialogue, shop, inventory, titles.*

**Size**: `633` lines (`24012` bytes)

**Classes:**
- `class ItemStub`
  - Method `.__init__(item_id)`

**Functions:**
- `def wrap_text(text, width)`
- `def bar(screen, x, y, width, label, cur, mx, color, show_num)` - *An ASCII gauge: label, hashed fill and numeric readout.*
- `def draw_hud(screen, world, env, fps, show_map)`
- `def location_name(world)` - *The place the player is standing in, for the HUD banner.*
- `def draw_location(screen, world)` - *Small gold place-name plate in the top-left corner.*
- `def draw_minimap(screen, world)` - *Coarse terrain map with entity markers, top-right.*
- `def project_marker(screen, world, cam, wx, wy, wz)` - *World position to screen cell; returns (col, row) or None.*
- `def draw_world_overlays(screen, world, cam)` - *Damage numbers and the interaction prompt, anchored in the world.*
- `def fit_text(text, width)` - *Clip one line to the available width without splitting a border.*
- `def panel_bounds(screen, margin_x, margin_y)` - *A margin-clamped panel rectangle: (x, y, width, height).*
- `def centered_panel(screen, max_w, want_h, margin_x, margin_y)` - *A centred panel no wider than max_w and no taller than want_h.*
- `def panel_text(screen, bx, bw, y, text, color)` - *Draw one line centred inside a panel, clipped to its interior.*
- `def draw_dialogue(screen, world, dlg, page, choice_idx)` - *Bottom dialogue box with the current page and choices.*
- `def _shop_row(idx, item, sel, inner)` - *One ware line whose columns degrade as the panel narrows.*
- `def draw_shop(screen, world, mode, sel, message)`
- `def draw_inventory(screen, world, message)`
- `def draw_help(screen)`
- `def title_menu_top(screen)` - *First row of the title menu, shared by drawing and mouse hit-testing.*
- `def draw_title(screen, world, cam, env, menu_sel, has_save)`
- `def draw_death(screen, world)`
- `def draw_pause(screen, sel)`
- `def draw_victory(screen, world, t)`
- `def draw_hurt_vignette(screen, world)` - *A brief red edge vignette that never wipes HUD text.*

---

### [`aldervale/inspect.py`](aldervale/inspect.py)
> *Headless inspection harness: visible frames plus a scripted control probe.*

**Size**: `831` lines (`27425` bytes)

**Classes:**
- `class ScriptedTerm` - *A terminal double that replays queued presses, holds and mouse events.*
  - Method `.__init__(width, height)`
  - Method `.size()`
  - Method `.poll()`
  - Method `.take_mouse()`
  - Method `.write(text)`
  - Method `.flush()`

**Functions:**
- `def build_game(seed, width, height, terrain_size, atlas_keys)` - *Create a booted, headless Game ready for rendering or probing.*
- `def _calm(game)`
- `def _reset(game, *, hp, stamina)`
- `def _place(game, x, z, yaw, day_t)`
- `def _scene_title(game)`
- `def _scene_village(game)`
- `def _scene_road(game)`
- `def _scene_castle(game)`
- `def _scene_castle_night(game)`
- `def _scene_camp_night(game)`
- `def _scene_combat(game)`
- `def _scene_inventory(game)`
- `def _scene_dialogue(game)`
- `def _scene_shop(game)`
- `def _scene_help(game)`
- `def _scene_rain(game)`
- `def _scene_snow(game)`
- `def _scene_cottage(game)`
- `def _scene_pause(game)`
- `def _scene_death(game)`
- `def _scene_victory(game)`
- `def draw_sprite_sheet(screen, atlas)` - *A labelled contact sheet at game scale plus near-native bake cells.*
- `def draw_portrait_sheet(screen, atlas)` - *A large detail study so model geometry can be judged up close.*
- `def _glyph_stats(screen)`
- `def _color_class(color)`
- `def _top_colors(screen, limit)`
- `def write_text_view(path, screen, name, day_t)` - *Write a terminal-readable mirror: glyphs, colour classes, palette.*
- `def _add_tutorial(game, name)`
- `def _tick(game, frames)`
- `def _key(game, token, frames)`
- `def _hold(game, held, frames)`
- `def probe_controls(game)` - *Drive the real input path and return a list of named check results.*
- `def run_inspection(outdir, seed, width, height, terrain_size, scale, scenes, probe, atlas_keys, studio)` - *Write scene PNGs, the web studio and a mechanics report.*
- `def format_summary(report)` - *One-line human summary for the CLI.*

---

### [`aldervale/launcher.py`](aldervale/launcher.py)
> *Localhost web launcher for Aldervale.*

**Size**: `374` lines (`14133` bytes)

**Classes:**
- `class Handler`
  - Method `._send(code, body, ctype)`
  - Method `.do_GET()`
  - Method `.do_POST()`
  - Method `.log_message(*args)`

**Functions:**
- `def game_command(mode)` - *The fixed command line for a launch mode; never user supplied.*
- `def spawn_game(mode)` - *Open the real game in a new console window (Windows).*
- `def render_page(token)`
- `def ensure_web_session(server)` - *Start building the browser-play session once, in the background.*
- `def launcher_url(port, autostart)` - *The local URL, optionally asking the page to start the game on load.*
- `def play_url(port)`
- `def check_health(port)` - *True when an Aldervale launcher already owns the port.*
- `def _studio_file(name)`
- `def serve(port, open_browser, autostart, open_play)` - *Blocking launcher server; returns the exit code.*

---

### [`aldervale/math3d.py`](aldervale/math3d.py)
> *Pure tuple-based 3D math for the sprite baker (bake-time only, not per-frame).*

**Size**: `73` lines (`1505` bytes)

**Functions:**
- `def add(a, b)`
- `def sub(a, b)`
- `def scale(v, s)`
- `def dot(a, b)`
- `def cross(a, b)`
- `def length(v)`
- `def normalize(v)`
- `def rot_y_matrix(a)`
- `def rot_x_matrix(a)`
- `def rot_z_matrix(a)`
- `def mat_vec(m, v)`
- `def mat_mul(a, b)`
- `def face_normal(p0, p1, p2)`

---

### [`aldervale/mesh.py`](aldervale/mesh.py)
> *Low-poly mesh construction and the mesh-to-ASCII sprite baker.*

**Size**: `486` lines (`18090` bytes)

**Classes:**
- `class Sprite` - *A baked char-cell image with per-cell packed RGB colour.*
  - Method `.__init__(chars, colors, lev, glow)`
  - Method `.filled()`
- `class Mesh` - *Static geometry: vertices plus quad faces with colour and emissive flag.*
  - Method `.__init__(verts, faces)`
- `class MeshBuilder` - *Assembles transformed primitives into one Mesh.*
  - Method `.__init__()`
  - Method `.build()`
  - Method `._quad(p0, p1, p2, p3, color, emissive, smooth)`
  - Method `.quad(p0, p1, p2, p3, color, emissive)`
  - Method `._rot(ry, rx, rz, pivot)`
  - Method `.box(cx, cy, cz, sx, sy, sz, color, ry, rx, rz, pivot, emissive)` - *Axis-aligned box, optionally rotated about a pivot point.*
  - Method `.cone(cx, y0, cz, r, h, seg, color, ry, rx, rz, pivot, emissive)` - *Tapered tube from a base ring to a near-point apex ring.*
  - Method `.cylinder(cx, y0, cz, r, h, seg, color, axis, ry, rx, rz, pivot, emissive)`
  - Method `.sphere(cx, cy, cz, rx, ry, rz, seg, rings, color, emissive)`
  - Method `._tp(p, rp)`
  - Method `.merge(mesh, matrix, offset, pivot)` - *Append mesh, optionally transformed about pivot then translated.*

**Functions:**
- `def _raster_tri(chars, colors, zbuf, cw, ch, tri, color, ramp, n_ramp, ids, face_id, shades)` - *Scanline-fill one projected triangle: z-test plus Gouraud luminance.*
- `def bake_sprite(mesh, yaw, pitch, dist, f, aspect, canvas, light, ramp, crop)` - *Bake a mesh into a Sprite viewed from yaw/pitch at the given scale.*
- `def _smooth_normals(mesh)` - *Position-keyed vertex normals of smooth faces, for Gouraud shading.*
- `def _color_delta(c1, c2)`
- `def _inner_edges(chars, colors, fids, fshade, cw, ch)` - *Line art only on meaningful face boundaries, never on flat facets.*
- `def _outline(chars, colors, cw, ch)` - *Darken the silhouette edge so models read as shapes, not noise.*
- `def _crop_bounds(chars, cw, ch)` - *Bounding box (x0, y0, x1, y1) of non-space cells, or a 1x1 fallback.*
- `def _pack_grid(chars, colors, cw, ch, box)` - *Slice flat buffers into row-lists limited to the given crop box.*

---

### [`aldervale/models.py`](aldervale/models.py)
> *Every 3D model in the realm: actors, creatures, flora and architecture.*

**Size**: `871` lines (`38371` bytes)

**Functions:**
- `def C(r, g, b)`
- `def _dead_wrap(b, rx, dz)`
- `def knight(pose, palette)` - *An armoured warrior with sword and shield; pose drives limb angles.*
- `def _sword(pal, blade_len, blade_w, blade)`
- `def guard(pose)` - *A castle guard with spear and heraldic tabard.*
- `def wolf(pose)` - *A grey wolf; diagonal-gait legs and a lunge pose.*
- `def skeleton(pose, captain)` - *A rattling skeleton; the captain is larger, crowned and caped.*
- `def bandit(pose)` - *A hooded road-agent with a dagger.*
- `def villager(pose, variant, role)` - *Robed elder, smith or peasant; variant picks clothes and hair.*
- `def chicken(pose)` - *A village chicken with peck and walk poses.*
- `def wyvern(frame)` - *The wyvern circling the castle; two wing frames.*
- `def tree_oak(seed, sway)` - *A broad oak; seed varies canopy layout, sway animates it.*
- `def tree_pine(seed, sway)`
- `def tree_birch(seed, sway)`
- `def tree_dead(seed)`
- `def bush(seed)`
- `def rock(seed, big)`
- `def house(variant)` - *A timber-framed cottage; windows glow warm at night (emissive).*
- `def well()`
- `def fence()`
- `def cart()`
- `def anvil()`
- `def haystack()`
- `def campfire(frame)` - *A crackling fire; frame 0-3 wobbles the flame cones (emissive).*
- `def torch(frame)` - *A gate torch: iron post, waxed head and a four-frame flame.*
- `def chest(opened)`
- `def shrine()`
- `def banner(frame)` - *A tower banner; two wave frames.*
- `def castle()` - *The showpiece: curtain walls, merlons, corner towers, keep and gate.*
- `def pickup(kind)` - *Ground loot: gold, potion, pelt, bone or the quest amulet.*

---

### [`aldervale/noise.py`](aldervale/noise.py)
> *Deterministic integer-hash value noise and fractal sums (no random module).*

**Size**: `45` lines (`1081` bytes)

**Functions:**
- `def hash2i(ix, iy, seed)`
- `def rand01(ix, iy, seed)`
- `def _smooth(t)`
- `def value_noise(x, y, seed)`
- `def fbm(x, y, seed, octaves, lacunarity, gain)`

---

### [`aldervale/render.py`](aldervale/render.py)
> *Scene renderer: animated sky, voxel-marched terrain and billboard sprites.*

**Size**: `813` lines (`31684` bytes)

**Classes:**
- `class Camera` - *View parameters plus precomputed per-column ray angles.*
  - Method `.__init__(w, h, x, z, y, yaw, pitch, dist)`
- `class Env` - *Per-frame atmosphere derived from the world clock.*
  - Method `.__init__(day_t, t)`

**Functions:**
- `def _tile(text)`
- `def _ridges()`
- `def _clouds()`
- `def clear_camera_distance(terrain, px, pz, eye_y, fx, fz, cam_y, desired)` - *Pull the camera in when a hill would sit between it and the player.*
- `def _mix(c1, c2, t)`
- `def render_scene(screen, world, cam, env)` - *Draw sky, terrain, entities, smoke and weather into the screen buffer.*
- `def _weather(screen, weather, env)` - *Deterministic rain streaks or drifting snow, drawn above the world.*
- `def _sky(screen, cam, env)`
- `def _birds(screen, cam, env)` - *Three birds cross the day sky, flapping on a slow rhythm.*
- `def _mountains(screen, cam, env)` - *Three fogged ridge layers above the horizon, each with a broken edge.*
- `def _disc(screen, cam, az, el, radius, color, chars_pair)`
- `def _clouds_draw(screen, cam, env)`
- `def _terrain(screen, ter, cam, env, wet, snow)`
- `def _light_pools(screen, world, cam, env)` - *Warm stippled pools under campfires and shrines, strongest at night.*
- `def _entities(screen, world, cam, env)`
- `def _smoke(screen, world, cam, env)` - *Thin chimney smoke above village roofs, drifting with the wind.*
- `def _fireflies(screen, world, cam, env)`

---

### [`aldervale/rules.py`](aldervale/rules.py)
> *Pure RPG rules: items, stats, XP, damage and inventory (no side effects).*

**Size**: `102` lines (`3548` bytes)

**Classes:**
- `class ItemDef` - *An immutable item definition; instances live in ITEMS.*
- `class Inventory` - *Item counts plus the equipped weapon and armor ids.*
  - Method `.add(item_id, n)`
  - Method `.remove(item_id, n)`
  - Method `.count(item_id)`
  - Method `.weapon_atk()`
  - Method `.armor_dfn()`
  - Method `.total_atk(base_atk)`
  - Method `.total_dfn(base_dfn)`

**Functions:**
- `def _i(id_, name, kind, **kw)`
- `def xp_for_level(level)`
- `def damage_roll(atk, dfn, rng)` - *Attack power versus defence; never zero, mildly random.*

---

### [`aldervale/story.py`](aldervale/story.py)
> *Story data: the Chronicle's cast, dialogue and quest text as pure data.*

**Size**: `170` lines (`5755` bytes)

**Functions:**
- `def dialogue_for(name, quest_state)` - *Dialogue payload for a named speaker at the given quest state.*
- `def guard_dialogue(name)` - *Dialogue payload for a gate guard, carrying the twin's own name.*

---

### [`aldervale/studio.py`](aldervale/studio.py)
> *Browser studio: render the exact char-cell frame with a real terminal font.*

**Size**: `490` lines (`19083` bytes)

**Functions:**
- `def encode_screen(screen)` - *Raw cells and packed colours for one rendered frame.*
- `def encode_sprite(sprite)` - *Raw cells and packed colours for one baked sprite.*
- `def collect_models(atlas)` - *Sample every studio model/pose at evenly spaced yaw frames.*
- `def write_studio(outdir, seed, viewport, scenes, models, checks)` - *Write index.html + studio-data.js; return their paths.*
- `def find_browser()` - *First installed Chromium-family browser, or None.*
- `def screenshot_studio(html_path, out_path, query, size)` - *Screenshot a studio page with headless Edge/Chrome; return (ok, detail).*

---

### [`aldervale/term.py`](aldervale/term.py)
> *Terminal control: VT100 setup, polled key input and frame output.*

**Size**: `419` lines (`14941` bytes)

**Classes:**
- `class TerminalError` - *Raised when the terminal cannot render the game at all.*
- `class Terminal` - *Raw-mode ANSI terminal wrapper with polled held-key input.*
  - Method `.__init__(color, use_alt_screen)`
  - Method `.__enter__()`
  - Method `.__exit__(*exc)`
  - Method `.start()`
  - Method `._open_windows()`
  - Method `._init_win_input()`
  - Method `.close()`
  - Method `.size()`
  - Method `.take_mouse()` - *Drain queued mouse events: (kind, x, y, buttons, wheel).*
  - Method `.poll()` - *Return (pressed, held): new key tokens and currently held ones.*
  - Method `.write(text)`
  - Method `.flush()`
  - Method `.set_title(title)`
  - Method `.read_key()` - *Return one normalized key token or None; never blocks.*

**Functions:**
- `def _mouse_event(x, y, buttons, flags)` - *Normalize a Windows MOUSE_EVENT_RECORD into a game mouse token.*
- `def vk_token(vk, ch)` - *Map a Windows virtual-key code to a game key token, or None.*

---

### [`aldervale/terrain.py`](aldervale/terrain.py)
> *Procedural island heightfield with biome colours, baked light and water.*

**Size**: `321` lines (`11369` bytes)

**Classes:**
- `class Terrain` - *A square island world grid sampled at one unit per cell.*
  - Method `.__init__(seed, size, water, octaves, village, castle, camp)`
  - Method `._generate(octaves, half)`
  - Method `._stamp_disk(x, z, r)`
  - Method `._stamp_path(a, b)`
  - Method `._stamp_ring(cx, cz, r)`
  - Method `._paint(grass_mix, forest, gres)`
  - Method `._smooth_lights()` - *Blur the char-luminance grid so ground glyphs read as coherent shade.*
  - Method `.in_bounds(x, z)`
  - Method `.height(x, z)`
  - Method `.color(x, z)`
  - Method `.light(x, z)`
  - Method `.material(x, z)`
  - Method `.texture_at(x, z)`
  - Method `.is_path(x, z)`
  - Method `.walkable(x, z)`
  - Method `.forest_at(x, z)`

**Functions:**
- `def _smooth(t)`
- `def _lerp_packed(c1, c2, t)`

---

### [`aldervale/webgame.py`](aldervale/webgame.py)
> *Browser play client: a localhost thin client over the real Python engine.*

**Size**: `464` lines (`15409` bytes)

**Classes:**
- `class WebTerm` - *Terminal double used by Game; queues input and ignores output.*
  - Method `.__init__(width, height)`
  - Method `.size()`
  - Method `.poll()`
  - Method `.take_mouse()`
  - Method `.write(text)`
  - Method `.flush()`
- `class WebGame` - *One live session: Game + WebTerm + a 20 fps simulation thread.*
  - Method `.__init__(seed, width, height)`
  - Method `.set_input(pressed, held, mouse)`
  - Method `._player()`
  - Method `.snapshot()` - *Latest frame plus a small state header; marks the client alive.*
  - Method `.state()` - *Diagnostics for tests and the agent; does not count as a client poll.*
  - Method `.step()` - *One client frame: input, the shared simulation step, then render.*
  - Method `._loop()`
  - Method `.close()`

**Functions:**
- `def encode_frame(screen)` - *Rows of glyphs plus packed RGB colours for the canvas client.*
- `def _clean_mouse(events)`

---

### [`aldervale/world.py`](aldervale/world.py)
> *The world of Aldervale: generation, simulation, quests and persistence.*

**Size**: `817` lines (`34506` bytes)

**Classes:**
- `class World` - *Owns terrain, entities, the player, quests and the world clock.*
  - Method `.__init__(seed, atlas, day_length, terrain_size)`
  - Method `._next_eid()`
  - Method `._generate()`
  - Method `._walkable_near(x, z, radius)`
  - Method `._spawn_hostile(kind, x, z, yaw)` - *Spawn a hostile from its canon template at a walkable spot.*
  - Method `._add(entity)`
  - Method `._spawn_village(vx, vz)`
  - Method `._spawn_castle(kx, kz)`
  - Method `._spawn_forest()`
  - Method `._spawn_camp(cx, cz)`
  - Method `.set_weather(name)` - *Force a weather state for play, scenes or tests.*
  - Method `._advance_weather()` - *Deterministic clear/precipitation cycle, independent of gameplay RNG.*
  - Method `.update(dt, env)` - *Advance the world clock, weather, every actor and transient state.*
  - Method `._tick_respawns(dt)` - *Return killed hostiles to their camps once the player is far away.*
  - Method `.add_message(text, color)`
  - Method `.add_damage_number(x, z, y, text, color)`
  - Method `.resolve_player_swing()`
  - Method `.kill_actor(actor)`
  - Method `._add_drop(pickup)`
  - Method `._give_xp(amount)`
  - Method `.hit_player(dmg, attacker)`
  - Method `.shrine_pray()`
  - Method `.respawn_player()`
  - Method `.interact_target()` - *Nearest interactable entity in front of the player.*
  - Method `.npc_talk(npc)` - *Build the dialogue payload for an NPC based on quest state.*
  - Method `.npc_choice(action)`
  - Method `.pickup_item(pickup)`
  - Method `.open_chest(chest)`
  - Method `.buy(item_id)`
  - Method `.sellables()` - *Items Bram will buy, as (item_id, count) pairs.*
  - Method `.sell(item_id)`
  - Method `.quest_objective()`
  - Method `.save(path)` - *Persist world state atomically (temp file, fsync, replace).*
  - Method `.load(path, atlas, terrain_size)`

---

### [`tests/__init__.py`](tests/__init__.py)
**Size**: `0` lines (`0` bytes)

---

### [`tests/test_aldervale.py`](tests/test_aldervale.py)
> *Unit tier: fast in-process checks for the pure engine core.*

**Size**: `632` lines (`24145` bytes)

**Classes:**
- `class FakeTerm`
  - Method `.__init__()`
  - Method `.write(s)`
  - Method `.flush()`
- `class TestNoise`
  - Method `.test_deterministic_and_bounded()`
  - Method `.test_fbm_smooth()`
- `class TestMath3d`
  - Method `.test_rot_y_maps_front()`
  - Method `.test_identity()`
  - Method `.test_face_normal_unit_and_direction()`
- `class TestScreen`
  - Method `.test_set_respects_bounds_and_depth()`
  - Method `.test_text_overrides_with_nearest_depth()`
  - Method `.test_box_draws_frame()`
  - Method `.test_ramp_is_wide_and_unique()`
  - Method `.test_downsample_keeps_edge_colour_with_smooth_glyph()`
  - Method `.test_ground_tiles_are_rectangular()`
  - Method `.test_box_fill_clears_interior_and_none_keeps_it()`
  - Method `.test_blit_scales_and_occludes()`
  - Method `.test_flush_diff_second_frame_small()`
  - Method `.test_frame_text_rows()`
- `class TestCapture`
  - Method `.test_png_header_and_scanlines()`
  - Method `.test_glyph_pixels_use_cell_colour()`
  - Method `.test_save_png_writes_file()`
- `class TestMesh`
  - Method `.test_box_face_count()`
  - Method `.test_cone_and_sphere_face_counts()`
  - Method `.test_bake_sprite_chars_in_ramp()`
  - Method `.test_bake_yaw_frames_differ()`
  - Method `.test_emissive_glow_separate()`
  - Method `.test_house_carries_layered_architecture_detail()`
  - Method `.test_knight_cape_and_shield_reach_behind_and_outboard()`
  - Method `.test_boulders_are_rounded()`
- `class TestStudio`
  - Method `.test_encode_screen_keeps_cells_and_colours()`
  - Method `.test_collect_models_samples_yaws_and_skips_missing()`
  - Method `.test_knight_turnaround_frames_are_distinct()`
  - Method `.test_write_studio_roundtrip()`
  - Method `.test_find_browser_returns_none_or_a_real_path()`
  - Method `.test_screenshot_missing_page_fails_cleanly()`
- `class TestLauncherUnit`
  - Method `.test_fixed_launch_commands()`
  - Method `.test_page_injects_token()`
  - Method `.test_launcher_url_and_health_helpers()`
  - Method `.test_studio_file_rejects_traversal()`
- `class TestWebGameUnit`
  - Method `.test_encode_frame_returns_rows()`
  - Method `.test_web_term_queues_input_and_ignores_output()`
  - Method `.test_queued_mouse_events_stay_bounded()`
- `class TestAtlas`
  - Method `.test_yaw_frame_wraparound()`
  - Method `.test_heights_registered()`
- `class TestRules`
  - Method `.test_damage_roll_bounds()`
  - Method `.test_damage_roll_defence_reduces()`
  - Method `.test_xp_curve_monotonic()`
  - Method `.test_inventory_ops()`
  - Method `.test_item_ordering_sensible()`
- `class TestHudHelpers`
  - Method `.test_wrap_text()`
  - Method `.test_eid_hash_stable()`
- `class TestCliValidation`
  - Method `._run(argv)`
  - Method `.test_bad_fps_refused()`
  - Method `.test_bad_width_refused()`
  - Method `.test_bad_demo_seconds_refused()`
- `class TestReviewRegressions` - *Regressions for defects found in the aldervale code review.*
  - Method `.test_pack_rgb_clamps_channels()`
  - Method `.test_water_fog_reaches_fog_colour()`
  - Method `.test_terminal_min_width_clamped()`
  - Method `.test_terminal_uses_large_viewport()`
- `class TestStoryData` - *The story module is the single source of narrative truth.*
  - Method `.test_cast_entries_are_complete()`
  - Method `.test_gate_guards_are_the_twins()`
  - Method `.test_dialogue_for_every_villager()`
  - Method `.test_elder_dialogue_covers_quest_states()`
  - Method `.test_quest_objectives_cover_states()`
  - Method `.test_guard_dialogue_carries_twin_name()`
  - Method `.test_player_name_single_source()`
- `class TestMouseAndOutline` - *Mouse event normalization and sprite silhouette outlines.*
  - Method `.test_mouse_event_normalization()`
  - Method `.test_bake_sprite_has_silhouette_outline()`
  - Method `.test_bake_flat_face_is_one_glyph()`

---

### [`tests/test_integration.py`](tests/test_integration.py)
> *Integration tier: world generation, quest chain, rendering and the CLI.*

**Size**: `1657` lines (`63111` bytes)

**Classes:**
- `class TestTerrain`
  - Method `.test_deterministic()`
  - Method `.test_village_flattened_and_walkable()`
  - Method `.test_island_has_sea_at_corners()`
  - Method `.test_path_exists_between_village_and_castle()`
  - Method `.test_materials_match_their_terrain()`
  - Method `.test_texture_grid_is_coherent()`
- `class _FakeWorld`
- `class TestRenderScene`
  - Method `.setUpClass()`
  - Method `._world_with_entities()`
  - Method `.test_scene_fills_screen_with_sky_on_top()`
  - Method `.test_night_darkens_and_lights_fireflies()`
  - Method `.test_entities_occluded_behind_terrain_depth()`
  - Method `._billboard(z)`
  - Method `.test_ground_clutter_adds_tufts_and_flowers()`
  - Method `.test_castle_gate_has_two_animated_torches()`
  - Method `.test_hurt_vignette_does_not_wipe_a_row()`
  - Method `.test_location_names_follow_landmarks()`
  - Method `.test_weather_overlays_draw_rain_and_snow()`
  - Method `.test_wet_and_snowy_ground_change_the_palette()`
  - Method `.test_campfire_light_pool_warms_ground()`
  - Method `.test_water_glitter_marks_the_sun_path()`
  - Method `.test_near_billboards_are_clipped()`
- `class TestWorldSim`
  - Method `._world()`
  - Method `.test_deterministic_generation()`
  - Method `.test_spawns_present()`
  - Method `.test_full_quest_chain()`
  - Method `.test_save_load_roundtrip()`
  - Method `.test_weather_cycles_without_consuming_game_rng()`
  - Method `.test_location_plate_shows_weather()`
  - Method `.get_temp_dir()`
  - Method `.test_interact_and_shrine()`
  - Method `.test_chest_loot()`
- `class TestGameShell`
  - Method `.setUpClass()`
  - Method `._render_once()`
  - Method `.test_movement_changes_position()`
  - Method `.test_attack_kills_wounded_wolf()`
  - Method `.test_state_transitions()`
  - Method `.test_potion_use_heals()`
  - Method `.test_render_frame_smoke()`
  - Method `.test_save_and_load_via_game()`
- `class TestCliSubprocess`
  - Method `._run(*args)`
  - Method `.test_version()`
  - Method `.test_unknown_flag_is_misuse()`
  - Method `.test_headless_demo()`
  - Method `.test_screenshot_writes_frame()`
  - Method `.test_autostart_requires_serve()`
  - Method `.test_open_play_requires_serve()`
  - Method `.test_open_play_conflicts_with_autostart()`
  - Method `.test_serve_port_validation()`
  - Method `.test_open_requires_serve()`
  - Method `.test_web_shot_requires_a_studio_page()`
- `class FakeWebSession`
  - Method `.__init__()`
  - Method `.snapshot()`
  - Method `.state()`
  - Method `.set_input(pressed, held, mouse)`
- `class TestLauncherHTTP`
  - Method `.setUp()`
  - Method `._post(payload, token)`
  - Method `._post_api(payload, token)`
  - Method `.test_play_page_frame_and_state()`
  - Method `.test_input_api_forwards_and_requires_token()`
  - Method `.test_frame_reports_loading_before_session()`
  - Method `.test_page_and_token_protected_start()`
  - Method `.test_duplicate_start_is_coalesced()`
  - Method `.test_health_and_unknown_path()`
- `class TestCamera`
  - Method `.test_default_camera_is_close_enough_for_model_detail()`
  - Method `.test_camera_pulls_in_when_a_hill_blocks()`
  - Method `.test_camera_keeps_full_distance_on_flat_ground()`
- `class TestInspection` - *The headless lens: PNG scenes, text mirrors and the control probe.*
  - Method `.test_inspection_writes_png_text_and_report()`
  - Method `.test_probe_controls_all_pass()`
- `class TestResponsiveMenus` - *Every menu panel must stay inside its own box at any viewport size.*
  - Method `._screen(width, height)`
  - Method `._find_box(scr)`
  - Method `._assert_panel_contained(scr, label)`
  - Method `.test_help_fits_every_width()`
  - Method `.test_inventory_fits_every_width()`
  - Method `.test_shop_fits_every_width()`
  - Method `.test_shop_sell_fits_every_width()`
  - Method `.test_overlay_boxes_fit_every_width()`
  - Method `.test_title_fits_every_width()`
- `class TestReviewFixes` - *Regressions for defects found in the aldervale code review.*
  - Method `._world()`
  - Method `.test_gold_pickups_collected_same_frame()`
  - Method `.test_hud_bars_do_not_overlap()`
  - Method `.test_hud_adapts_to_narrow_viewports()`
  - Method `.test_death_transitions_to_dead_state()`
  - Method `.test_gate_guards_spawn_as_twins()`
  - Method `.test_npc_talk_delegates_to_story()`
- `class TestLaunchers` - *The one-click run buttons: PLAY.bat, run.sh and the VS Code config.*
  - Method `.test_play_bat_version_fastpath()`
  - Method `.test_web_launchers_are_one_click()`
  - Method `.test_web_launchers_detect_python_like_play_bat()`
  - Method `.test_play_web_version_fastpath()`
  - Method `.test_readme_lists_every_module_and_license_files()`
  - Method `.test_run_sh_targets_module()`
  - Method `.test_play_bat_wt_directory_has_no_trailing_backslash()`
  - Method `.test_vscode_launch_configs()`
- `class TestHeldControls` - *Movement must respond to held keys polled every frame.*
  - Method `.setUpClass()`
  - Method `._tick(held, n)`
  - Method `.test_w_moves_player_forward()`
  - Method `.test_arrow_up_moves_and_left_turns()`
  - Method `.test_a_d_strafe()`
  - Method `.test_shift_sprints()`
  - Method `.test_space_press_attacks()`
  - Method `.test_hold_b_guards_and_release_drops_it()`
  - Method `.test_guard_blocks_damage_through_held_key()`
- `class FakePollTerm`
  - Method `.__init__()`
  - Method `.queue_press(keys)`
  - Method `.queue_mouse(events)`
  - Method `.poll()`
  - Method `.take_mouse()`
  - Method `.write(text)`
  - Method `.flush()`
  - Method `.size()`
- `class TestMouse` - *Mouse orbit, zoom, pick, walk-to and click-to-attack.*
  - Method `._game()`
  - Method `.test_mouse_release_before_press_is_safe()`
  - Method `.test_right_drag_orbits_and_tilts()`
  - Method `.test_wheel_zooms()`
  - Method `.test_pick_rejects_sky()`
  - Method `.test_click_sets_walk_target()`
  - Method `.test_click_drag_does_not_walk()`
  - Method `.test_walk_target_carries_player()`
  - Method `.test_click_near_enemy_attacks()`
- `class TestTitleFlow` - *Starting a new game from the title screen through the poll path.*
  - Method `.test_new_game_starts_from_title()`
  - Method `.test_continue_without_save_starts_world()`
  - Method `.test_mouse_click_on_new_game_starts_world()`
  - Method `.test_title_arrows_and_enter_choose_continue()`
  - Method `.test_mouse_click_on_help_opens_help()`
- `class TestMechanics` - *Combat simulation mechanics: guard, facing, backstab, potions, respawn.*
  - Method `._world()`
  - Method `.test_returning_enemy_does_not_instant_heal()`
  - Method `.test_guard_reduces_damage_and_costs_stamina()`
  - Method `.test_guard_needs_stamina()`
  - Method `.test_enemy_strike_requires_facing()`
  - Method `.test_backstab_deals_bonus()`
  - Method `.test_potion_heals_over_time()`
  - Method `.test_sell_menu_ignores_currency()`
  - Method `.test_killed_enemy_respawns_far_away()`
- `class TestSharedSimulationStep` - *The browser session must step the world exactly like the terminal loop.*
  - Method `._game()`
  - Method `.test_a_menu_freezes_the_world()`
  - Method `.test_a_fallen_hero_enters_the_death_state()`
  - Method `.test_victory_arms_once_and_then_counts_up()`
  - Method `.test_the_web_session_steps_through_the_shared_tick()`

**Functions:**
- `def _tiny_atlas()`
- `def _rmtree(d)`

---
