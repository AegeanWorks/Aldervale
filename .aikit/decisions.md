# Decisions

Why this project is built the way it is, oldest first. One entry per decision that changes a
contract, a dependency, a data format or the architecture; IDs are consecutive and never reused.

Entry format: a `### ADR-NNN: <decision>` heading followed by Date, Status,
Context, Decision and Consequences lines.

### ADR-001: Pure-stdlib software 3D renderer instead of curses or external engines
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: The brief demands "almost real models" at ASCII density with zero setup friction; curses lacks 24-bit colour control and any pip dependency breaks portability.
- **Decision**: Low-poly meshes are baked at load into char-cell sprites (perspective projection, backface culling, Lambert shading onto a 12-glyph ramp, z-buffered scanlines with deterministic dither), then composited over a column-raymarched voxel heightfield with per-cell depth, all through VT100/truecolor escapes on a diff-flushing Screen buffer.
- **Consequences**: Boot pays ~3 s of baking and the hot loop is hand-tuned Python (~14 ms/frame at 132x60); in exchange the game runs on a bare Python 3.10+ install on Windows, macOS and Linux with no dependencies and pixel-like shaded output.

### ADR-002: Billboard sprites from 16 yaw frames (2.5D composition)
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: True per-frame 3D rasterisation of every entity is too slow in pure Python at playable frame rates.
- **Decision**: Every model is baked at 16 yaw steps per pose into sprite frames; the renderer picks the frame from (entity yaw - camera yaw) and scales it with depth-tested blits, far-to-near, with fog and day/night tinting; emissive faces are baked into separate glow sprites drawn at night.
- **Consequences**: Rotation snaps in 22.5-degree steps (imperceptible at game scale) and sprites upscale when very close; the whole scene stays within one depth-consistent painter's algorithm.

### ADR-003: Deterministic seeded world with entity-id save deltas
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Saves must survive version changes to the world generator and stay tiny, and tests need reproducible worlds.
- **Decision**: The world (terrain, village, castle, camp, spawns) is rebuilt from a single integer seed; the save file stores only player state, quest state, clock and the sets of killed/collected/opened entity ids, written atomically (temp + fsync + os.replace).
- **Consequences**: Save files stay under a few KB, but regenerating a save made with an older generator can shift unmodified entity positions; acceptable for a single-session RPG.

### ADR-004: Terminal colour model is foreground-only truecolor
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Background-colour SGR doubles escape traffic and breaks on light terminal themes; the pixel-art look needs dense glyphs rather than filled blocks.
- **Decision**: Every cell carries one 24-bit foreground colour and a ramp glyph chosen by luminance; the sky is a dithered gradient, never a background fill; `--no-color` degrades to the plain ramp.
- **Consequences**: The game reads best on dark terminal themes (documented in the README) and frame emission stays under ~60 KB in the worst case.

### ADR-005: Console-event mouse input, free-look camera, silhouetted high-density sprites
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Players asked for mouse control, a genuine 3D camera and models that read as solid shapes instead of dithered noise; the terminal already polls console input records for keys.
- **Decision**: Read MOUSE_EVENT records from the same console input queue (Quick Edit disabled) and expose `take_mouse()`; the camera gains a pitch axis (right-drag, clamped 0.12-0.62 rad) and click-to-walk uses the depth buffer for 3D picking; sprites bake at 56 cells/unit for actors across 20 yaw steps, flat-shaded (no dither) with a darkened silhouette outline pass.
- **Consequences**: Mouse works in Windows Terminal and conhost but not on POSIX terminals yet (keyboard fully covers every action); sprite baking costs ~3.4 s at boot; the glyph output reads as clean outlined models instead of speckle.


### ADR-006: Headless inspection harness with PNG scenes and a control probe
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: Graphics and control defects were only observable by launching a real terminal, which blocks automated review and leaves no artefact to compare before and after a fix.
- **Decision**: Add `--inspect DIR`, backed by `capture.py` (stdlib zlib/struct PNG writer plus a built-in 5x7 font) and `inspect.py` (ten scripted scenes, a `.txt` glyph/colour mirror per scene, and a 15-step probe that drives the same key and mouse path as the player). The probe exits 1 when any check fails.
- **Consequences**: Every change can be reviewed from images, text and JSON with no terminal; the probe becomes a control regression gate; PNG generation adds no dependency and never runs in the play loop.

### ADR-007: Billboard near clip and a clear village spawn camera
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: The inspection scenes exposed a house 1 m in front of the spawn camera whose billboard blanketed half the sky, and the camp/combat views could be staged from underwater or from the previous scene's position.
- **Decision**: Skip billboards closer than 60% of the camera distance (`render._entities`), move the fourth village house out of the spawn camera, add a 26 m hostile-spawn sanctuary around the player, and stage night/combat scenes from walkable ground.
- **Consequences**: Near props can no longer fill the frame, the opening village view reads as a village, and wandering hostiles cannot aggro before the player has moved; distant detail and the player sprite are unaffected.

### ADR-008: Held guard, facing-gated strikes and over-time potions
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: The HUD advertised "Hold B guard" but no input path set `guarding`; returning foes instantly healed two HP; potions healed instantly while the item text promised a few seconds; enemies could strike through their own backs.
- **Decision**: Set `guarding` from the held-key set while in play (and clear it in menus), block 70% of damage for 10 stamina, gate enemy strikes on a facing dot of 0.35, remove the return-state instant heal in favour of slow idle regen, and heal potions at 24 HP/s from `heal_remaining`.
- **Consequences**: Every advertised control and item behaves as documented, combat has readable facing and backstab counterplay, and the probe plus the mechanics tests pin the behaviour.

### ADR-009: Viewport-clamped menus and opaque panels
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: At 40-48 columns every menu overflowed its box and the screen edge: help lines ran past the frame, inventory and shop rows were cut mid-number, the title footer lost its first word, and `Screen.box` skipped its fill when asked for spaces, so the world and HUD showed through dialogue, shop and pause panels.
- **Decision**: All panel functions now size from the viewport (`centered_panel`/`panel_bounds`), wrap or shorten their copy to the panel interior, use `Screen.box(..., fill=" ")` which now fills when `fill` is not `None`, and the HUD is skipped while a modal screen (inventory, help, pause, shop, dialogue, the death overlay) is open. Help switches to a compact control list below 52 columns or 26 rows; the title drops its 51-column logo when it does not fit.
- **Consequences**: Every screen stays readable from 40x20 to 260x110, panels are opaque by construction, and the minimap must draw its box without a fill (it passes no fill argument); new panels must use the shared helpers or containment tests will fail.

### ADR-010: One sellable predicate for shop, world and HUD
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: The sell tab listed every inventory count, including gold, and both `World.sell` and the HUD priced rows through `ITEMS[...]`; selecting gold crashed with `AttributeError`/`KeyError` on the first sell tab the player opened.
- **Decision**: `World.sellables()` is the single predicate (item exists in `ITEMS`, is not the amulet, has a positive price and a positive count); the HUD and `Game._key_shop` consume it, and `World.sell` refuses anything it would not list.
- **Consequences**: Gold and quest items can never be sold, unknown ids fail closed, and the layout and mechanics tests both exercise the sell tab.

### ADR-011: Mouse-safe title menu with click and keyboard activation
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: Pressing New game from a real Windows Terminal crashed with `'Game' object has no attribute '_click_pending'` because the field was created only when a drag began; a stray mouse release left in the queue after the title transition read it. The title also drew a selection marker but ignored clicks, arrows and Enter.
- **Decision**: Initialize `_click_pending` in `Game.__init__`, drain mouse events on the title screen, hit-test menu rows through `hud.title_menu_top` (shared with drawing), activate the clicked row, and add Up/Down/W/S selection plus Space/Enter activation while keeping the N/C/H/Q shortcuts.
- **Consequences**: New game starts from keyboard or click with queued mouse events present, the selection marker has meaning, and the shared row helper keeps drawing and hit-testing aligned when the logo falls back to the compact banner.

### ADR-012: Detailed ASCII rendering pass
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: The user said the game barely read as ASCII and wanted far more detail. Visual review found a 10-level ramp, one glyph set for all ground, untextured sprites, 3-4x source downsampling, and a hash-dithered sky.
- **Decision**: Widen `RAMP` to 19 levels (space through `$`); add `Terrain.materials` and a coherent `Terrain.texture` grid; draw ground from per-material weighted 16-slot `GROUND_TILES` (dense/sparse selected by texture); add three fogged mountain ridge layers and an 8x8 warped ordered sky dither; add water sparkle/foam glyphs; draw internal sprite line art only on meaningful face boundaries and only in runs of 2+ cells; preserve the highest-contrast quartet when downsampling; and put a dark plate behind title options so menu text stays readable over the skyline.
- **Consequences**: Frames now carry material-specific ASCII texture at 132x60 and remain legible at 40x20; frame time is ~18 ms at 132x60, boot ~5.7 s, both within the 30 fps cap and demo budget. Terrain memory grows by one byte per cell for materials and one for texture; no save format changes.


### ADR-013: Depth cues and ground-scale detail
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The detailed ground still read as a painted surface: sprites floated, night light sources did not touch the ground, and near terrain had no small-scale incident.
- **Decision**: Add rare per-material ground clutter (tufts, tinted flowers, pebbles, broken rock, snow sparkle, shells) gated to under 46 m and chosen by a cell hash; draw a two-row dithered contact shadow under every billboard whose base is on visible ground within 4 m of its depth; draw stippled warm light pools under campfires and shrines (2.2 m world radius, night-weighted); and add a faint sun/moon glitter path on water at 1/64 cells with calmer space-filled troughs.
- **Consequences**: Sprites sit on the ground and night scenes have local warmth; the additions cost ~2-3 ms/frame (20.8 ms total at 132x60, still under the 30 fps cap) and are deterministic. Clutter is intentionally sparse so the material texture still dominates; shadows and pools are depth-checked against terrain so they cannot paint over walls.

### ADR-014: Castle gate light, atmosphere and place names
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The castle was a day-only silhouette with no gate light, shores had no wet edge, villages were silent, and the HUD never said where the player was. A screenshot pass also exposed a hurt "vignette" that painted three full-width stripes over sky, HUD and minimap, and leaked into later inspection scenes because `hurt_t` was not reset.
- **Decision**: Add a `torch` model and atlas poses with two gate torches wired into `World.update`, extend light pools to torches (larger, warmer), add a wet-sand band and phase-broken foam, chimney smoke, three day-sky birds, a nearest-landmark location plate (Aldervale / Suncrest Castle / The Bone Camp / The Old Road / Whispering Wood / The Vale), a minimap `N`, a 14th `castle_night` scene, and rewrite the hurt vignette as a sparse red edge tint. `inspect._reset` now clears `hurt_t`. Landmark naming picks the nearest zone so small maps do not mislabel the camp as the village.
- **Consequences**: Night keeps its warm focal points, shores read as shores, and the HUD has a sense of place. The vignette can no longer erase HUD text. Frame time is ~24 ms at 132x60 (30 fps cap) and inspection is 14 scenes at ~11 s.

### ADR-015: Model-like framing, shading and figure detail
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The user asked for "almost real model-like graphics". At the old 6 m camera a 1.95 m knight covered only ~14 of 60 rows, smooth shading was replaced by noisy highest-contrast glyphs, and feet, hands, shield edges, sword tips, cape folds, ribs and wolf legs read as blocks.
- **Decision**: Move the default camera to 4.6 m with terrain line-of-sight pull-in and smoothing (zoom floor 3.0); smooth interior glyph levels while keeping the highest-contrast cell colour; raise lighting contrast, add metallic specular and cool shadows; and refine the models: knight helmet brow/nose guard/cheek guards, shield face panel/boss/heraldic band/corner studs, sword fuller/edges/taper, gauntlets and steel toe caps; wolf shoulders, pale chest/belly, neck ruff, joints and paws; skeleton dark torso core, sternum, side ribs, spine, claws and feet; captain folded cape with creases, scalloped hem, mantle and gold trim. Add `15_sprites` and `16_portraits` inspection sheets.
- **Consequences**: The vision review rates model-likeness 8/10 at true game scale and says ship; no camera clipping or HUD overlap was observed. Frame time is ~21 ms at 132x60 (30 fps cap), boot ~6.3 s, and the two new sheets add ~2 s to a 16-image inspection run.


### ADR-016: Rounded figure volumes and directional sun shadows
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: After the model-fidelity pass, the delegated review still called the silhouettes boxy: heads, pauldrons, ribcages and the wolf read as stacked slabs, the internal facet lines looked like wireframes rather than surfaces, and characters had contact blobs but no sun-cast shadow.
- **Decision**: Build heads, pauldrons, skull/pelvis/ribcage and wolf body/chest/haunch/head from ellipsoids, use cylinders for wolf legs, drop the box pauldron caps, round the captain's mantle with shoulder ellipsoids, and reduce internal line art to strong material/colour boundaries at 0.80 darkening. Add a four-step directional sun shadow for every billboard, projected onto depth-checked ground and scaled by entity height and sun elevation.
- **Consequences**: The vision review now reports rounded shoulders and mantle, no gaps or floating parts, and rated the figures good enough for an ASCII game ("ship"). Frame time is ~24-31 ms at 132x60 (still under the 30 fps cap), boot ~7-9 s; the 130-test suite and 16-image inspection remain green. Facet definition is intentionally reduced: new model materials should use distinct colours if they need a visible edge.


### ADR-017: Detailed architecture, rounded boulders and door light
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: After the character pass, cottages, wells and boulders were the last large box-built objects in close screenshots; villages also went dark at night except for the shrine and campfire.
- **Decision**: Add alternating stone footing blocks, a timber rail and diagonal braces, three layered thatch strips per roof slope, a capped sooty chimney, window flower boxes with coloured blooms and an emissive door lantern to every cottage; add a spoked pulley wheel, rope and bucket to the well; build boulders from three ellipsoids; project a small (1.5 m, 0.48 strength) warm pool beneath each door lantern; add a `17_cottage` close-facade inspection scene.
- **Consequences**: The vision review confirms the cottage reads as architecture rather than a box, boulders read naturally, door light reads as lit doorways without square patches, and says ship. Frame time is ~22 ms at 132x60, boot ~6.7 s; inspection is 17 images and 17/17 checks at three viewport sizes.


### ADR-018: Browser Studio as the authoritative screenshot lens
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The PNG capture approximated the terminal with a hand-made 5x7 font and tinted cell backgrounds, so screenshots did not match what the game really shows; the user reported the screenshot method did not work properly. Edge and Node are installed, so a real browser is available without adding a Python dependency.
- **Decision**: Every `--inspect` run now also writes `index.html` + `studio-data.js` with raw chars/colours for all scenes, a sprite gallery (8 yaws x poses for 8 models), and the probe checks. The page renders with a real monospace font on black, supports scene/model tabs, zoom, fit, grid and yaw spin, and accepts query parameters for reproducible shots. `--web-shot` shells out to installed Edge/Chrome in headless mode; `ALDERVALE_BROWSER` overrides the executable. PNG/text output is retained for terminals and tools without a browser.
- **Consequences**: The browser view is pixel-faithful to the terminal grid (DOM text verified byte-identical for the village frame) and is now the authoritative review lens; a free Kilo vision review rated it 9/10 and said ship. The studio writes a ~2 MB data file per inspection and headless shots require a browser; the terminal game still has no new runtime dependency.


### ADR-019: Knight turnaround fixes and honest review limits
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The Studio's new all-yaws turnaround exposed three geometry defects. Code inspection confirmed them: the knight had no cape at all, the shield's inner face sat 4 cm inside the left pauldron's outer edge, and the sword grip was 15 cm above the gauntlet. The free Kilo Nemotron VL endpoint and qwen3-vl on evren3 both returned PNGs as binary and could not see them, so their earlier ratings and "ship" claims were discarded as unreliable.
- **Decision**: Add a two-panel dark-blue cape with three folds and a gold clasp; move the shield cluster 11 cm outboard, rotate it from 0.12 to 0.24 rad and add a leather arm strap to bridge the 4 cm gap; shorten the knight-only blade to 0.78 and move the grip offset from -0.44 to -0.59 so the hilt sits in the gauntlet; make the turnaround a 4x2 grid with evenly spaced yaw samples; and pin the cape/shield bounds plus distinct-yaw frames with tests.
- **Consequences**: The three fixes are verified by vertex bounds, geometry arithmetic and the Studio's exact grid, not by a vision model. The authoritative visual check stays the human-openable Studio page. No visual-review claim is made for this round; agents must ask a provider to read a known caption before trusting its ratings.


### ADR-020: Deterministic weather and wet ground
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Every scene was clear weather, which left rain, snow and wet ground unused as cheap atmosphere. The Studio now supports exact browser screenshots, but no available vision provider can read PNGs, so improvements must be structurally verifiable.
- **Decision**: Add a transient `world.weather` state ("clear", "rain", "snow"). `render._weather` draws deterministic rain streaks (`/`, `\`, `|`) or drifting snow (`*`, `"`) above the world and below the HUD; rain also cools and darkens land in `_terrain` through a `wet` factor. Add rain-at-dusk and snow-at-night inspection scenes, and reset weather plus quest state in `inspect._reset` so scenes do not leak state.
- **Consequences**: Inspection is now 19 images (17 scenes + 2 sheets) and 17/17 checks at three sizes; the rain scene has 100 overlay glyphs with the HUD and location plate intact. Frame time is ~24 ms at 132x60, boot ~7.6 s. The overlays are verified by glyph-count tests and Studio DOM checks; no aesthetic rating is claimed (G-003).


### ADR-021: In-game weather cycle, persistence and HUD
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Weather existed only when inspection scenes forced `world.weather`; normal play was always clear and saves could not preserve a storm. Weather also had no HUD indication, so rain/snow appeared without context.
- **Decision**: Give World a deterministic `weather`/`weather_left` cycle independent of gameplay RNG (clear -> rain or snow -> clear, every 45-190 s), with in-world messages; expose `set_weather`; persist both fields in the existing save schema (missing fields default to clear); show the active weather on the gold location plate; add rain puddle glints and a pale snow dusting with sparkles to terrain; and keep the dedicated rain/snow inspection scenes.
- **Consequences**: Play now gets its first weather change after roughly two minutes, saves resume the current weather, and the HUD names it. Weather is verified by deterministic cycle tests, save/load tests, HUD text checks, palette-change tests and Studio DOM checks (rain/snow label present, HUD intact). Frame time is ~23 ms at 132x60, boot ~7.4 s; no visual rating is claimed (G-003).


### ADR-022: Localhost web launcher with a Start button
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The user asked for a web-based start button. A browser cannot spawn a local game directly, and a full in-browser game server is a much larger change; a localhost launcher is the smallest honest way to start the real terminal game from the browser.
- **Decision**: Add `--serve [PORT]` backed by stdlib `ThreadingHTTPServer` on 127.0.0.1. The page offers START GAME (`python -m aldervale`) and WATCH DEMO (`--demo 9`), both token-protected and built from fixed commands, and serves the Studio under `/studio/` from `.inspect/` with path-traversal guards. On Windows the game opens in a new console; other platforms return the command to run. `--open` launches the default browser; ports must be 0 or 1024-65535.
- **Consequences**: The Start button was verified end-to-end: clicking it in Edge spawned a real `python -m aldervale` process, which was then stopped. The launcher adds no runtime dependency, exposes no arbitrary command or file, and binds localhost only. HTTP/unit/CLI tests cover page rendering, token rejection, launch dispatch, health, traversal rejection and port validation.


### ADR-023: True one-click start and idempotent launcher
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The web Start button still required running a terminal command first. The user asked for one-click start. Starting a second server on the same port also failed instead of just reopening the page.
- **Decision**: Add `--autostart` (valid only with `--serve`), which opens the launcher URL with `?autostart=1`; the page strips the query, sets a one-shot session guard and POSTs the token-protected play request automatically. Make `serve` health-check the port first and, when an Aldervale launcher already owns it, only reopen the browser. Add `PLAY_WEB.bat` (Windows double-click; starts launcher, browser and game) and `play_web.sh` for POSIX.
- **Consequences**: Double-clicking PLAY_WEB.bat is a genuine one-click start; reloads do not spawn duplicate games; a second launch just reopens the page. Security is unchanged: localhost bind, per-process token, fixed commands. Verified in Edge: `/?autostart=1` returned "Game launched in a new console window", the URL lost its query, and the one-shot flag was set. No visual rating is claimed (G-003).


### ADR-024: Browser edition over the same Python engine
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The user clarified they wanted the game itself available in both the browser and the current terminal, not only a launcher/Studio. Rewriting in JavaScript would duplicate the simulation and a Pyodide port would add a large external dependency; the existing Game/World/render pipeline can instead run behind a localhost thin client.
- **Decision**: Add `webgame.py` with `WebGame`, a `WebTerm` input queue, a 20 fps simulation thread, and chars/colour frame transport. The browser `/play` page sends key/mouse state to `/api/input` (token-protected) and draws frames to a canvas; the Python side runs the same Game, World, HUD, renderer, weather and saves. The session is built lazily in the background (the page shows a forge message), pauses after 20 s without polling, and uses `saves/aldervale_web.json`. Add `/play`, `/api/frame`, `/api/state`, a launcher button, and `--open-play`; `PLAY_WEB.bat` and `play_web.sh` now open the browser edition directly. The terminal build is unchanged. This supersedes the PLAY_WEB target described in ADR-023.
- **Consequences**: Live Edge verification: canvas 792x660, 3.5 ms render, 20 fps, WASD moved the player 2.28 m, inventory opened/closed, save-and-quit produced a save, and continue resumed play. Python remains the single source of truth, so no game logic is duplicated; no new dependency. The server binds localhost and keeps one shared session; remote hosting, authentication and multiplayer are out of scope. 162 tests and the full gate remain green.

### ADR-025: One Shared Simulation Step for the Terminal and Browser Builds
- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: Reviewing the browser edition found its session thread hand-rolled its own copy of the frame step instead of reusing the terminal loop's. It advanced the world in every state, so opening the inventory, help, a shop or the pause menu kept enemies acting while the terminal froze them; it never called `_sync_death`, so a browser player who died stayed in `play`, never saw the death screen and could not respawn; and it never armed `victory_shown`/`victory_t`, so finishing the quest never showed the victory banner there. Mouse events queued while a modal was open were also drained only in play/title, so the queue could grow without limit.
- **Decision**: Extract `Game.tick(dt)` as the single simulation step: build the frame environment, advance the world only in `play`/`title`/`dead`, sync the death state, arm the victory overlay once and count its clock, and tick the fps counter. `Game.run` and `WebGame` (through a new `WebGame.step`) both call it. Bound the browser mouse queue at 64 events, keeping the newest.
- **Consequences**: Both builds now pause, die and win identically, and the terminal loop keeps its behaviour. `Game.tick` is covered directly (menu freeze, death transition, victory clock) and `WebGame.step` is covered by a fake game, so the delegation cannot silently drift again. A live Edge run confirmed the world clock stops in the inventory and resumes on close, a forced death reaches the `dead` state and respawns on Enter, and the victory overlay arms with a moving clock. 169 tests and 4/4 gates.
- Cross-principle check: no principle section changed. Serves PRINCIPLE-001 (one code path), PRINCIPLE-014 (failing-first coverage of the divergence) and PRINCIPLE-015 (live dogfooding of the browser build).

## Licensing migration (agpl-final)

- New versions use the Aegean Game License 1.1 (AGL-1.1); versions up to and including `agpl-final` remain under GNU AGPL-3.0.
- Rights holder: AegeanWorks; commercial use under ACL-1.0.
- Counsel review of the 1.1 texts remains pending.

## License notice cleanup (2026-10-26)

- The license-history notes were removed from README.md and COMMERCIAL.md: the project is offered only under the Aegean Game License 1.1 (AGL-1.1), with commercial use under ACL-1.0.

### ADR-026: True pixel graphics for the browser build
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The user reported that the ASCII view is botched and asked for proper graphics. The glyph renderer is intentionally dense, but at the shipped cell sizes it reads as noise: sprites become `+`/`:` soup, terrain turns into dark bands and the scene is hard to parse. The engine already owns deterministic low-poly meshes and a heightfield, and the browser edition already has a canvas and a localhost frame transport, so the glyph layer is the part that should change.
- **Decision**: Add a truecolor pixel path beside the ASCII path: `gfx.py` (column-major RGB frame buffer, per-pixel depth, RGBA sprites), `gfxatlas.py` (bakes the existing meshes into 4-12 yaw RGBA billboards per pose with Gouraud shading, outlines and a glow layer) and `gfxrender.py` (sky gradient, sun/moon, stars, cloud wisps, ridge layers, column-marched terrain with merged colour runs, water, foam, ground detail, light pools, contact shadows, pixel billboards, weather, fireflies and hurt vignette). The browser `/play` session uses the pixel atlas and sends base64 column-major RGB plus the existing HUD text grid; the canvas upscales with nearest-neighbour and draws HUD glyphs on top. The default internal resolution is 288x162. The terminal build keeps the ASCII atlas and renderer. `--gfx-shot PATH --gfx-scene NAME --gfx-size WxH` writes one pixel frame headlessly; `--inspect` remains the ASCII lens.
- **Extended by**: ADR-027 adds runtime 3D meshes for nearby actors and props; the billboard atlas stays the distance LOD.
- **Consequences**: The browser one-click now shows a real pixel scene with readable figures, houses, water, weather and HUD instead of glyph noise. Both builds still run the same simulation, save format and controls. The pixel atlas costs about eight seconds at boot and about 25 MB, so the existing forge screen covers it; the frame costs about 38-46 ms at 288x162 in CPython, which the 20 fps browser loop absorbs. No dependency was added and the terminal contract is unchanged. Tests cover the buffer, baker, camera alignment, payload and a day/night render smoke test (181 tests). Per project guideline G-003 no provider demonstrated reliable image reading, so no visual rating is claimed; the browser canvas and `--gfx-shot` PNGs are the human visual check.
- Cross-principle check: PRINCIPLE-009 (separate buffer/atlas/renderer roles), PRINCIPLE-010 (bounded resolution, baked frames, measured budget), PRINCIPLE-011 (one-click browser path, no new dependency), PRINCIPLE-012 (column-major transport, one payload), PRINCIPLE-014 (failing-first unit/integration coverage), PRINCIPLE-015 (live Edge screenshot of `/play`), PRINCIPLE-016 (ADR and README updates).

### ADR-027: True 3D meshes for nearby actors and props
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The first pixel build used baked billboards for every entity. They are cheap, but they always face the camera and expose a flat 2D image when the player orbits or stands close. The user asked to continue into "proper graphics with models". The models are already low-poly meshes, so the flatness is a renderer choice, not missing content.
- **Decision**: Add `gfxmodels.py`, a runtime mesh rasteriser with perspective projection, backface culling, world-space directional lighting, a per-pixel silhouette outline and the shared terrain z-buffer. The nearest four actors within 12 m and the nearest two props within 16 m are drawn from their real meshes; the player is always included. Everything farther away uses the square-pixel billboard atlas as a distance LOD. `gfxatlas.py` keeps the source meshes beside the baked frames, `Game` owns one `ModelRenderer`, and `gfxrender._entities` selects the LOD set. Bakes switch to `ASPECT = 1.0` so a metre is a metre on both axes and billboard/mesh proportions match. The knight gets a gold sun-diamond on the cloak back so the default third-person view is readable. The player is drawn into a private frame buffer and composited with a small depth bias, so a foreground terrain crest cannot slice the legs while the model still self-occludes correctly; other actors respect terrain depth.
- **Consequences**: The browser now shows actual 3D characters, NPCs, monsters and nearby buildings from any camera angle, with the same simulation and HUD. Runtime cost is roughly 4-6 ms per actor and 2-5 ms per prop at 288x162; steady village frames measured about 40-55 ms (roughly 18-25 fps uncapped), and the atlas still bakes in about 8-9 s using about 16 MB. No dependency was added. The 3D path is browser-only; the terminal keeps the ASCII renderer and distant props keep the baked billboards. Tests cover the mesh rasteriser, yaw-sensitive coverage, mesh exposure and square-pixel baking. Per G-003 no visual rating is claimed; a live Edge capture and `--gfx-shot` PNGs are the human visual check.
- Cross-principle check: PRINCIPLE-009 (separate mesh renderer, atlas and scene roles), PRINCIPLE-010 (bounded LOD counts and measured frame cost), PRINCIPLE-012 (mesh cache, no per-frame rebuilding), PRINCIPLE-014 (unit coverage of projection/rasterisation), PRINCIPLE-015 (live browser verification).

### ADR-028: Grounded shadows, terrain grain and smooth model shading
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: After ADR-027 the models were real 3D, but the scene still read as models on a painted board: houses and figures had only contact blobs, large road/grass spans were flat colour, water was a solid blue plane and curved mesh parts stayed visibly faceted.
- **Decision**: Add a bounded fidelity pass. `gfxrender._cast_shadows` projects three soft shadow blobs away from the sun for actors, props and trees within 30 m, clipped by the terrain depth buffer and disabled at night. Large terrain runs use `FrameBuffer.fill_column_pattern` with a subtle 16-row, world-phase grain; water mixes in the horizon colour with a distance-based reflection factor. `gfxmodels` precomputes position-keyed vertex normals and uses a 16-entry Gouraud shade table for faces flagged smooth, while flat plates keep the existing faceted shading.
- **Consequences**: The scene gains grounding, surface texture, water depth and rounded helmets/pauldrons without changing controls, simulation or save data. The passes are bounded: shadows use three samples per entity, grain only touches runs of 30+ pixels, and smooth shading only applies to rounded faces. Steady village frames measured about 44-55 ms at 288x162; no dependency was added. Tests cover the pattern fill and the Gouraud rasteriser. Per G-003 no aesthetic rating is claimed; live Edge captures and `--gfx-shot` frames are the human visual check.
- Cross-principle check: PRINCIPLE-010 (bounded work per frame), PRINCIPLE-012 (cached vertex normals and shade tables), PRINCIPLE-014 (unit coverage of new primitives), PRINCIPLE-015 (live browser verification).

### ADR-029: WebGL2 GPU client with the Python engine as authority
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The CPU pixel build reached readable 3D models but is limited to a 288x162 internal buffer and about 18-25 fps in CPython. The user asked to continue into proper graphics; a GPU path can draw the existing heightfield and meshes at native resolution without duplicating the simulation. Headless Edge was verified to provide WebGL2 through SwiftShader, so the path is testable.
- **Decision**: Add a separate `/play3d` GPU client. `webglscene.py` uploads the 320x320 heightfield, a lit RGBA material map and a triangle-soup bundle of all 41 models/88 poses; `webglclient.py` renders a displaced terrain grid, sky, water plane and real model instances in WebGL2 with a transparent text HUD. Each 20 fps tick sends a compact scene JSON (camera, visible entities, tint, HUD); click-to-walk uses a server-side heightfield raycast. `/play` keeps the software pixel renderer as a fallback, each session has its own save slot, and `PLAY_WEB.bat` / `--open-play` target `/play3d`.
- **Consequences**: The browser now has a native-resolution, smooth 3D view with correct model perspective, sky, water and HUD; the Python World/Game/HUD remain the single source of truth and no dependency was added. The GPU forge is about a second and the scene payload is small, while the pixel and ASCII builds remain unchanged. Headless Edge verified the page, assets and rendered frame; tests cover the model/world bundles, scene encoder, raycast and launcher routes. Per G-003 no aesthetic rating is claimed; the live capture is the human visual check.
- Cross-principle check: PRINCIPLE-009 (separate bundle/client/render modules), PRINCIPLE-010 (GPU rendering, bounded scene payload), PRINCIPLE-011 (stdlib localhost, one-click), PRINCIPLE-012 (static asset bundles, small per-tick JSON), PRINCIPLE-014 (unit/HTTP coverage), PRINCIPLE-015 (live Edge dogfooding).

### ADR-030: GPU shadow map and atmospheric sky/weather
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The WebGL client (ADR-029) had smooth geometry but only flat contact discs, a clear day sky and no weather; the CPU build already had cast shadows and rain/snow. The GPU view needed matching atmosphere without changing simulation.
- **Decision**: Add a 1024x1024 directional shadow map around the camera. A light-space depth pass renders models and props with front-face culling, which keeps terrain self-shadowing from producing acne; the terrain and model shaders sample it with 4-tap PCF, a small bias and a normal offset. The sky shader adds hash-based star points and a moon at night; a full-screen weather shader draws thin rain streaks or snow dots from the world weather. `/play3d?weather=rain&day=0.8` seeds a preview session for inspection.
- **Consequences**: The GPU scene gains grounded shadows, a night sky and weather that match the CPU build's mood. The extra depth pass and PCF sampling cost GPU time but leave the 20 fps simulation untouched; headless SwiftShader is slower, while a real GPU stays smooth. Model night brightness uses the server tint without a second daylight multiplier so figures remain readable. The query preview is read-only and only applies when the session is first built. Tests cover the scene/bundle/route layer; live captures verify day, night and rain. No dependency was added.
- Cross-principle check: PRINCIPLE-010 (bounded shadow map and weather pass), PRINCIPLE-012 (single depth map, no per-frame rebuild), PRINCIPLE-014 (unchanged test gate), PRINCIPLE-015 (live Edge day/night/rain captures).

### ADR-031: GPU point lights, shoreline foam and clouds
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: After ADR-030 the GPU scene had shadows, stars and weather, but night fires and windows did not light the ground, water ended as a flat plane and the sky had no clouds.
- **Decision**: Send the six nearest warm/coloured point lights (campfire, torch, shrine, house window) in the scene JSON and add them to the terrain and model fragment shaders with quadratic falloff and a day/night power scale. The water shader samples the heightfield to fade into shoreline foam and adjust alpha by depth. The sky shader adds a three-octave drifting cloud layer that darkens with the night factor.
- **Consequences**: Night scenes gain local fire/window pools without a second light pass; shorelines and the sky read better. Uniform arrays are bounded at six, the point-light loop is fixed, and water sampling reuses the existing height texture. No simulation, controls or save format changed. Headless captures verify day/night/rain; the usual tests and gates remain green.
- Cross-principle check: PRINCIPLE-010 (fixed six-light loop, no per-frame asset rebuild), PRINCIPLE-012 (shared height texture, compact scene JSON), PRINCIPLE-015 (live day/night captures).

### ADR-032: GPU terrain materials and a graphical minimap
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The GPU terrain used one lit colour texture, so grass, forest, road, rock and snow shared a single flat response and rain/snow did not change the ground. The GPU HUD also still drew the ASCII minimap into the corner, which looked out of place beside the 3D view.
- **Decision**: Store the terrain material id in the colour texture alpha channel. The terrain shader branches on that id to add sand ripple, grass/forest grain, flower flecks, road stones, rock strata and snow brightening, and darkens or brightens with `uWet`/`uSnow` from the world weather. Build an offscreen terrain canvas from the height and colour data in the browser; when the map is toggled, the HUD draws that map with water, roads, entity dots and a gold player marker. The Python HUD suppresses only its ASCII minimap in `render_mode == "webgl"`.
- **Consequences**: The ground reads as distinct materials and responds to weather without extra textures or a second scene payload. The minimap is a true overhead view rather than glyphs and costs one small canvas built once per world bundle. The alpha channel was unused and now carries data, so any future colour texture consumer must mask alpha; the existing pixel path does not use this bundle. No simulation, controls or save format changed. Tests pin the alpha material channel, scene fields and minimap hooks; live captures verify the day map and terrain detail.
- Cross-principle check: PRINCIPLE-009 (terrain, scene and HUD roles stay separate), PRINCIPLE-010 (one offscreen canvas, no per-frame rebuild), PRINCIPLE-012 (material id reuses the existing texture, no extra payload), PRINCIPLE-015 (live day/night captures).

### ADR-033: Weather-aware models, water glints and flickering lights
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: After ADR-032 the ground responded to rain and snow, but buildings and characters stayed dry and bare, the lake surface was a flat colour with foam, and fire/window light was static. These mismatches broke the weather illusion.
- **Decision**: Add `uWet`, `uSnow` and a per-entity `uSnowCap` to the model shader. Rain darkens the base colour and adds a low specular sheen; snow mixes a daylight-scaled pale layer into up-facing normals with a smoothstep, excluding campfire, torch and wyvern models. The water shader derives wave normals from the existing sine field, mixes in the horizon by fresnel, adds a sun glint, and draws hash-based ripple rings when raining. Scene lights carry a flicker weight (`f`) by source; the browser computes the per-light multiplier once per frame and the shaders apply the array value, avoiding per-fragment sine work.
- **Consequences**: Snow settles on roofs and shoulders, wet scenes darken consistently, lakes gain depth and glints, and firelight pulses subtly. The extra model uniforms and water operations are bounded; the six-light loop remains fixed and flicker costs six sines per frame, not per fragment. The light JSON gains an `f` field, and per-entity snow caps require no new draw calls. No simulation, controls or save format changed. Tests pin the light field, uniforms and page hooks; live captures verify daylight snow caps and rain darkening.
- Cross-principle check: PRINCIPLE-010 (per-frame flicker instead of per-fragment sines), PRINCIPLE-012 (no extra draw calls or payloads beyond one light float), PRINCIPLE-015 (live weather captures).

### ADR-034: Weather-graded atmosphere, cloud shadows and water depth
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: Weather changed the ground, models and water, but snow and rain still fell from a bright blue sky with a hard sun and distant clear-weather fog. Water also read as one flat blue plane, and the ground had no moving shadow from the clouds drawn in the sky.
- **Decision**: Add a single browser-side `weatherEnv()` palette that blends the scene zenith, horizon and fog toward daylight-scaled overcast colours for rain and snow, shortens fog distances, dims the sun, flattens direct light with `uSunLight`, hides stars/moon and raises sky cloud cover. Terrain and model shaders apply a slow drifting `cloudShade()` term scaled by weather and daylight. The water shader mixes turquoise shallows into the deep colour by heightfield depth and uses the weather fog.
- **Consequences**: Overcast scenes now match their sky and lighting, cloud shadows drift across ground and buildings, and lakes read with depth near the shore. All grading is client-side and bounded; the palette is computed once per frame, the weather target colours scale with daylight so nights stay dark, and fog/cloud amounts are clamped constants. No simulation, controls or save format changed. Tests pin the page hooks; live captures verify day snow, night rain and lake water.
- Cross-principle check: PRINCIPLE-010 (one palette per frame, bounded shader terms), PRINCIPLE-012 (no additional textures or payloads), PRINCIPLE-015 (live clear/rain/snow and lake captures).

### ADR-035: Layered sky clouds and rain lightning
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The sky gradient, sun and stars worked, but clear weather still read as a mostly empty blue field, clouds were a single faint fbm layer, and rain had no storm flashes.
- **Decision**: Replace the single cloud mask with two drifting fbm layers plus a high wisp layer, add sun-side tinting to the cloud colour and widen the sun/moon halos. Rain draws a short full-screen lightning flash computed from a deterministic 11-second time slot, with a double-pulse envelope and a capped alpha; the weather shader returns the flash colour before drawing rain streaks.
- **Consequences**: Clear skies gain visible layered clouds, overcast weather keeps its heavier cover, and rain occasionally flashes without changing any simulation state. The sky shader runs three fbm evaluations instead of one; the flash is a single blended draw and only during rain. Cloud coverage remains bounded by the shared weather palette so cloud shadows stay subtle. No controls, save data or game rules changed. Tests pin the page hooks, and captures verify clear, rain and snow skies.
- Cross-principle check: PRINCIPLE-010 (bounded fbm layers and a single flash draw), PRINCIPLE-012 (procedural sky, no new textures), PRINCIPLE-015 (live clear/rain/snow captures).

### ADR-036: Graphical GPU status panel
- **Date**: 2026-10-30
- **Status**: Accepted
- **Context**: The 3D view was polished, but its main status block was still five rows of ASCII text on a scrim, which read as a terminal overlay. The data already existed in the Python HUD but was only sent as glyph rows.
- **Decision**: Add a `hud_status` object to the WebGL scene with name, level, gold, HP/stamina/XP, potions, weapon/armor and quest. The browser draws a graphical panel (bars, gear, quest, potions) in the existing five-row scrim area and suppresses exactly those five ASCII rows when the status is visible and the stage gives at least 11px per row. Messages above the panel, the location plate and the minimap stay unchanged; modal states and small stages keep the ASCII screen. The page header now shows weather and fps only.
- **Consequences**: The GPU HUD is readable and visually consistent with the 3D scene, while the terminal and pixel builds keep their ASCII HUDs. `hud_status` is separate from the existing `status: ready` field to avoid a key collision. Panel layout is compact below 80px and full above it; text is clipped with an ellipsis when narrow. No game rules, controls or save data changed. Tests pin the scene fields and page hooks, and captures verify the panel and small-stage fallback.
- Cross-principle check: PRINCIPLE-005 (README documents the GPU HUD), PRINCIPLE-009 (scene encoding and browser drawing stay separate), PRINCIPLE-014 (payload and page tests), PRINCIPLE-015 (live HUD captures).
