# aldervale

[![Built with AIKit](https://img.shields.io/badge/built%20with-AIKit-6f42c1)](https://github.com/AegeanWorks/AIKit)

ALDERVALE - a 2.5D medieval RPG rendered entirely in tiny ASCII cells. Low-poly
3D models (knights, wolves, a walled castle) are baked into shaded character
sprites, marched over a voxel heightfield with fog, day/night light, weather and
water, and composited with a full RPG on top: quests, combat, loot, shops,
saves.

It runs in the terminal **and in a browser** through a local canvas thin client
over the same Python engine. Standard library only; no dependencies, no assets,
no build step.

## 30-Second Cold-Start Quick Reference

- **Runtime Prerequisites**: Python 3.10 or newer (standard library only) and a
  dark-theme terminal that supports 24-bit colour (Windows Terminal, Terminal.app
  or any modern xterm). PLAY.bat opens a dedicated maximized Windows Terminal
  window, and the renderer scales with the window up to 260x110 cells - a bigger
  window or a smaller font (Ctrl+Minus) buys more detail, and at tiny glyphs the
  screen reads as pixel art.
- **Canonical Regression Shield Gate**:
  ```bash
  python -m unittest discover
  ```
- **Run something now** (under 10 seconds):
  ```bash
  PLAY.bat    # Windows: double-click it in Explorer - one click, no typing
  ./run.sh    # macOS and Linux
  python -m aldervale --demo 9      # hands-free attract mode
  python -m aldervale --screenshot vista.txt && type vista.txt
  PLAY_WEB.bat                     # one click: browser game
  python -m aldervale --serve --open-play # browser game (same engine)
  python -m aldervale --serve --open # launcher: terminal / browser / Studio
  python -m aldervale --inspect .inspect # 19 PNG images + 17 control checks
  python -m aldervale               # terminal play (WASD, SPACE, E, I, H)
  ```

  In VS Code, open the project folder and press F5 (or the Run button) -
  `ALDERVALE: Play` and `ALDERVALE: Demo` configurations are included.

### AIKit Commands (run from the AIKit folder)
| Role | Command |
|---|---|
| Status, task and gates | `python aikit.py status aldervale` |
| Phase 4: every gate | `python aikit.py check aldervale` |
| Repair memory and map, then check | `python aikit.py fix aldervale` |
| Resume an interrupted task | `python aikit.py resume aldervale` |

## The Tale

The Suncrest Amulet, hearth-stone of the vale, was stolen by the Bone Captain
and now squats in the old camp beyond the eastern woods. Elder Quill waits by
the village shrine; Bram hammers steel at his forge; wolves and worse patrol
the trees. Slay the Captain, bring the amulet home, and Aldervale will call
you hero. Full cycle: talk, accept, fight, loot, equip, buy, return, victory.

That is the tale the villagers tell. The true canon - the First Fire, the
eleven Keepers, the Captain's grief, the wyvern's vigil, and where the saga
goes next - is written in **LORE.md**, the Chronicle of the vale. Every story
change to the game builds on it, and **ADAPTATION.md** maps every canon
element to the exact file that owns it.

## Graphics

The renderer aims at dense ASCII art rather than flat silhouettes:

- a 19-level glyph ramp (space through `$`) shades every face;
- terrain has a per-cell material grid (sand, grass, forest, dirt, rock, snow)
  and a coherent two-octave texture grid; each material draws from a weighted
  16-slot glyph table, so grass shows tufts, roads show gravel, cliffs show
  broken stone instead of one repeated character;
- the sky has a warped 8x8 dither and three fogged ridges; water mixes
  ripples, foam, a faint sun/moon glitter path and calm troughs;
- near ground detail: grass tufts, tinted flowers, pebbles, broken rock,
  snow sparkle and shells on their own materials;
- every billboard casts a dithered contact shadow and a sun-direction shadow;
  campfires, gate torches, shrines and door lanterns light the ground;
- shorelines have wet sand and foam; chimneys smoke, birds cross the day sky,
  and a gold place-name plate (plus `N` on the minimap) names the area;
- sprite baking draws line art only on meaningful face boundaries (`|`, `-`,
  `+`), adds a metallic specular and a cool shadow tint, and the downsampler
  uses a smooth mean glyph with the highest-contrast cell colour so plate,
  cloth and blade edges survive;
- figures mix rounded primitives (ellipsoid helms and pauldrons, wolf body and
  head, skull and ribcage) with plate geometry, and internal line art is drawn
  only at strong material boundaries;
- cottages carry stone footings, timber braces, layered thatch, a capped
  chimney, flower boxes and a lit door lantern; wells have a pulley, rope and
  bucket; boulders are rounded ellipsoids;
- a deterministic clear/rain/snow cycle, persisted in saves, with in-world
  messages and a weather label on the location plate; rain cools the ground
  and leaves puddle glints, snow dusts it in pale sparkles, and both have own scenes;
- the default camera sits at 4.6 m with terrain line-of-sight pull-in, so a
  knight spans about 20 of 60 rows instead of 14; the sprite and portrait
  contact sheets make every model change directly reviewable;
- the inspect harness renders all of this at 132x60, 80x40 and 40x20 without a
  terminal.

## Controls

| Key | Action |
|---|---|
| Title: Up Down + Enter | choose a menu option (clicking it works too) |
| N C H Q | new game / continue / help / quit from the title |
| W S or Up Down | walk forward / back |
| A D | sidestep left / right |
| Left / Right | turn the camera |
| Right-drag mouse | orbit and tilt the camera (full 3D look) |
| Left-click | walk to a point; talk to what you reach; attack a foe in reach |
| Mouse wheel | zoom the camera |
| Hold Shift | sprint (drains stamina) |
| SPACE | swing your sword (backstabs deal +50% from behind a foe) |
| Hold B | guard: blocks most incoming damage, spends stamina on each hit |
| E or Enter | talk / open chest / pick up / pray at shrine |
| I | inventory (U use potion over a few seconds, E equip best) |
| M | toggle minimap |
| H or F1 | help |
| + / - | zoom the camera (keys) |
| ESC | pause (save & quit from there) |

## Command Line

```text
python -m aldervale [--seed N] [--width W] [--height H] [--fps N]
                    [--demo [SECS]] [--benchmark] [--no-color]
                    [--screenshot PATH] [--inspect DIR]
                    [--inspect-scale N] [--web-shot PATH]
                    [--web-dir DIR] [--web-query QUERY]
                    [--web-size WxH] [--serve [PORT]] [--open]
                    [--autostart] [--open-play] [--save PATH] [--version]
```

`--demo` runs a non-interactive attract mode (also works piped, for CI);
`--benchmark` renders 60 headless frames and reports timing (~23 ms/frame at
132x60 on a 2026 laptop); `--screenshot` writes one plain-text vista frame.
Exit codes: 0 success, 1 failure (What/Why/Fix on stderr), 2 misuse.

### Seeing the game without a terminal

`--inspect DIR` boots the real renderer headlessly and writes the views a
reviewer or an AI agent needs to debug graphics and controls:

- nineteen PNGs: seventeen scenes (world, castle day/night, camp night,
  cottage, rain, snow, combat and menus) plus `15_sprites.png` and
  `16_portraits.png` for figure review;
- a `.txt` mirror per scene: the exact glyph grid, a colour-class map and the
  dominant palette, readable in any editor or terminal;
- `report.json` with per-scene fill/colour statistics and the results of 17
  scripted checks (walk, strafe, turn, sprint, guard, attack, potion, menus,
  map, zoom, orbit, click-to-walk, key mapping, respawn, buy, sell); the
  command exits 1 if any check fails, so it doubles as a control gate.

Menus clamp to the viewport: help and inventory wrap, the shop drops its
description column, and the title uses a compact banner on small windows.
`--inspect-scale 2` sets PNG crispness; write under the project (`.inspect/`
is gitignored).

### Studio: the accurate browser lens

The PNG writer uses a small built-in bitmap font and tinted cell backgrounds,
which is handy but not pixel-faithful. Every `--inspect` run also writes
`index.html` + `studio-data.js`: a standalone Studio that renders the exact
character/colour grid with a real monospace font on black. It has three tabs:

- **Scenes** - all captured frames, zoom and fit;
- **Models** - 8 models/poses at 8 yaws, 1-8x, grid, spin and a 4x2
  all-yaws turnaround;
- **Checks** - the 17 probe results.

Open the page directly, or capture it with headless Edge/Chrome:

```text
python -m aldervale --web-shot shots/knight.png --web-dir .inspect \
  --web-query "tab=models&model=knight&pose=idle&yaw=0&scale=4&shot=1" \
  --web-size 1200x1200
python -m aldervale --web-shot shots/village.png --web-dir .inspect \
  --web-query "tab=scenes&scene=village&shot=1" --web-size 1600x1000
```

`--web-shot` drives installed Edge/Chrome (override with `ALDERVALE_BROWSER`)
with no Python dependency. Its DOM text matches the terminal grid exactly, so
this is the authoritative view; PNG/txt remain for browserless tooling.

### Browser edition (same engine, canvas view)

```text
PLAY_WEB.bat                          # Windows: one click, browser game
sh play_web.sh                        # POSIX: one command, browser game
python -m aldervale --serve --open-play
```

`/play` runs the **same Python World, Game, HUD and renderer** as the terminal;
the browser only sends keyboard/mouse state and draws the returned chars and
colours into a canvas. The forge takes about nine seconds, then the game runs at
20 fps with WASD/arrows, SPACE, SHIFT, B, E, I, M, H, ESC, click-to-walk,
right-drag look and wheel zoom. Browser saves use `saves/aldervale_web.json`, so
save-and-quit and continue work there too. Both builds run the same simulation
step, so menus freeze the world, death offers respawn and the victory banner
appears in the browser exactly as in the terminal. The terminal version is
unchanged: `PLAY.bat` or `python -m aldervale`.

The server binds `127.0.0.1` only and keeps one shared session. It pauses after
20 s without a browser poll and resumes on the next request. Opening a second
browser tab attaches to the same game. Expose the port deliberately if you want
LAN play; there is no account system.

### Launcher: terminal, browser and Studio in one page

```text
python -m aldervale --serve --open
```

**START GAME** opens the native terminal game in a new console (Windows);
**WATCH DEMO** runs the attract mode; **PLAY IN BROWSER** goes to `/play`;
**Open Studio** serves the inspection Studio at `/studio/`. `--open-play` opens
the browser game directly, while `--autostart` opens the launcher and starts the
native game immediately. If a launcher is already running, the same command only
reopens the page. Ports below 1024 are refused; use `--serve PORT` to pick
another. Only fixed launch commands are exposed and `/start` + `/api/input`
require the per-process token.

## What's Inside

```text
aldervale/
├── PLAY.bat            <- one-click launch on Windows (prefers Windows Terminal)
├── PLAY_WEB.bat        <- one-click browser game (starts the localhost server)
├── run.sh              <- one-command launch on macOS and Linux
├── play_web.sh         <- one-command browser game for POSIX
├── .vscode/
│   └── launch.json     <- F5 / Run button configurations for VS Code
├── aldervale/
│   ├── __init__.py       <- package marker and version
│   ├── __main__.py     <- CLI: play, demo, screenshot, inspect, triads
│   ├── term.py         <- VT100 terminal control, non-blocking key input
│   ├── buffer.py       <- char-cell screen: colour, depth, diff flush
│   ├── capture.py      <- Screen to truecolor PNG with a built-in 5x7 font
│   ├── inspect.py      <- scene PNGs, text mirrors and the control probe
│   ├── studio.py       <- exact browser studio, model viewer, headless shots
│   ├── webgame.py      <- browser play session, canvas client, frame transport
│   ├── launcher.py     <- localhost launcher: start page, token, /play and Studio
│   ├── math3d.py       <- vector/matrix helpers for the sprite baker
│   ├── noise.py        <- deterministic integer-hash value noise
│   ├── terrain.py      <- island heightfield, biomes, paths, light
│   ├── mesh.py         <- box/cone/cylinder/sphere builder + ASCII baker
│   ├── models.py       <- knight, wolf, skeleton, castle, trees, houses...
│   ├── atlas.py        <- bakes every (model, pose, yaw) into sprites
│   ├── render.py       <- sky, sun, clouds, voxel terrain, billboards
│   ├── entities.py     <- actors, props, pickups, AI state machines
│   ├── rules.py        <- items, damage, XP, inventory (pure functions)
│   ├── story.py        <- the Chronicle as data: cast, dialogue, quests
│   ├── world.py        <- generation, quests, dialogue, shops, saves
│   ├── hud.py          <- bars, minimap, menus, dialogue, title art
│   └── game.py         <- game states, camera, main loop, demo autopilot
├── tests/
│   ├── __init__.py          <- test package marker
│   ├── test_aldervale.py    <- unit tier: pure engine core (fast)
│   └── test_integration.py  <- world gen, quest chain, rendering, CLI
├── LORE.md             <- the canon: world, history, characters, open threads
├── ADAPTATION.md       <- canon to code: where story changes go and why
├── .aikit/             <- this project's memory: record, ledger, decisions
├── .gitignore
├── COMMERCIAL.md       <- Commercial licensing terms (ACL-1.0)
├── LICENSE             <- Aegean Game License 1.1 (AGL-1.1): DRM-free personal play
├── LICENSES/           <- REUSE license texts
├── REUSE.toml          <- Machine-readable SPDX metadata
├── ASSETS.md           <- Asset/data manifest: what the license covers
└── README.md
```

(`saves/` appears next to the executable once you save a game; it is
gitignored.)

## Technical Notes

- The renderer is a 2.5D composite: a per-column ray-march over the height
  grid (front-to-back with a hidden-row buffer) draws terrain, water and fog;
  entities are depth-tested billboards chosen from 20 yaw-baked frames per
  pose, baked at high cell density with silhouette outlines and flat-lit
  faces so they read as solid models rather than noise; emissive faces (fire,
  crystals, windows) bloom at night. The camera orbits and tilts freely, and
  clicking the world walks there by reading the depth buffer.
- Frames are emitted as foreground-only truecolor runs of changed cells, so
  HUD rows cost nothing and full-motion frames stay small.
- Everything is deterministic from `--seed`: terrain, village layout, spawns,
  and the rng behind combat rolls.

## 📜 License

Free for personal play under the Aegean Game License 1.1 (AGL-1.1); see [LICENSE](LICENSE). It is DRM-free: Licensor ships no DRM and a distributor may not add it. Streaming, modding and free mods are allowed. Commercial use, paid mods and AI training need the Aegean Commercial License 1.0 (ACL-1.0); see [COMMERCIAL.md](COMMERCIAL.md).
