"""ALDERVALE command line entry point.

Exit codes follow the AIKit universal CLI contract: 0 success, 1 operational
failure (with a What/Why/Fix triad on stderr), 2 usage misuse.
"""

import argparse
import sys

from . import __version__


def _build_parser():
    ap = argparse.ArgumentParser(
        prog="aldervale",
        description="ALDERVALE - a 2.5D medieval RPG rendered in tiny ASCII "
                    "cells. Zoom your terminal font out for pixel detail.")
    ap.add_argument("--seed", type=int, default=7,
                    help="world seed (default 7)")
    ap.add_argument("--width", type=int, default=None,
                    help="render width in character cells")
    ap.add_argument("--height", type=int, default=None,
                    help="render height in character cells")
    ap.add_argument("--fps", type=int, default=30,
                    help="frame rate cap (default 30)")
    ap.add_argument("--demo", nargs="?", type=float, const=9.0, metavar="SECS",
                    help="run a non-interactive attract-mode demo and exit")
    ap.add_argument("--benchmark", action="store_true",
                    help="render 60 frames headless and report timing")
    ap.add_argument("--no-color", action="store_true",
                    help="render in monochrome ramp only")
    ap.add_argument("--screenshot", metavar="PATH",
                    help="render one vista frame to a text file and exit")
    ap.add_argument("--inspect", metavar="DIR",
                    help="write scene PNGs and a control-probe report to DIR "
                         "and exit")
    ap.add_argument("--inspect-scale", type=int, default=2, metavar="N",
                    help="pixels per glyph pixel in inspection PNGs "
                         "(default 2)")
    ap.add_argument("--web-shot", metavar="PATH",
                    help="screenshot the web studio with headless Edge/Chrome "
                         "and exit")
    ap.add_argument("--web-dir", default=".inspect", metavar="DIR",
                    help="studio directory containing index.html "
                         "(default .inspect)")
    ap.add_argument("--web-query", default="", metavar="QUERY",
                    help="studio query string, e.g. "
                         "\"tab=models&model=knight&pose=idle&yaw=0&scale=4&shot=1\"")
    ap.add_argument("--web-size", default="1600x1000", metavar="WxH",
                    help="headless browser window size (default 1600x1000)")
    ap.add_argument("--serve", nargs="?", const=8765, type=int, metavar="PORT",
                    help="serve the localhost web launcher and Studio "
                         "(default port 8765)")
    ap.add_argument("--open", action="store_true",
                    help="open the launcher page in the default browser")
    ap.add_argument("--autostart", action="store_true",
                    help="start the game as soon as the launcher page loads "
                         "(with --serve)")
    ap.add_argument("--open-play", action="store_true",
                    help="open the browser-play page directly (with --serve)")
    ap.add_argument("--save", default="saves/aldervale.json", metavar="PATH",
                    help="save slot path (default saves/aldervale.json)")
    ap.add_argument("--version", action="version",
                    version="ALDERVALE %s" % __version__)
    return ap


def _fail(what, why, fix):
    sys.stderr.write("What: %s\nWhy: %s\nFix: %s\n" % (what, why, fix))
    return 1


def run(argv=None):
    args = _build_parser().parse_args(argv)
    if args.fps < 4 or args.fps > 120:
        return _fail("--fps must be between 4 and 120.",
                     "The frame cap governs simulation stepping.",
                     "Retry with a value in range, e.g. --fps 30.")
    if args.demo is not None and args.demo <= 0:
        return _fail("--demo needs a positive number of seconds.",
                     "The demo mode exits when its timer expires.",
                     "Retry with e.g. --demo 9.")
    if args.width is not None and not 40 <= args.width <= 320:
        return _fail("--width must be between 40 and 320.",
                     "The renderer is sized in character cells.",
                     "Retry with a value in range, e.g. --width 200.")
    if args.height is not None and not 20 <= args.height <= 110:
        return _fail("--height must be between 20 and 110.",
                     "The renderer is sized in character cells.",
                     "Retry with a value in range, e.g. --height 90.")
    if not 1 <= args.inspect_scale <= 6:
        return _fail("--inspect-scale must be between 1 and 6.",
                     "Each glyph pixel is enlarged by this factor.",
                     "Retry with e.g. --inspect-scale 2.")
    if args.open and args.serve is None:
        return _fail("--open needs --serve.",
                     "The browser URL is only created by the launcher.",
                     "Retry with `python -m aldervale --serve --open`.")
    if args.autostart and args.serve is None:
        return _fail("--autostart needs --serve.",
                     "Autostart is a launcher-page behaviour.",
                     "Retry with `python -m aldervale --serve --open "
                     "--autostart`.")
    if args.open_play and args.serve is None:
        return _fail("--open-play needs --serve.",
                     "The browser game URL is only created by the launcher.",
                     "Retry with `python -m aldervale --serve --open-play`.")
    if args.open_play and args.autostart:
        return _fail("--open-play and --autostart are different targets.",
                     "One opens the browser game, the other starts the "
                     "terminal game from the launcher page.",
                     "Use --open-play for the browser, or --autostart alone "
                     "for the native launch page.")
    if args.serve is not None:
        if args.serve != 0 and not 1024 <= args.serve <= 65535:
            return _fail("--serve PORT must be 0 or 1024..65535.",
                         "Ports below 1024 are privileged and 65535 is the "
                         "maximum.",
                         "Retry with e.g. --serve 8765.")
        from .launcher import serve
        try:
            return serve(args.serve, args.open or args.open_play,
                         args.autostart, args.open_play)
        except OSError as exc:
            return _fail("Cannot start the web launcher: %s" % exc,
                         "The port is busy or the launcher could not bind "
                         "localhost.",
                         "Use another port, e.g. --serve 8766, or stop the "
                         "process using this one.")
    if args.web_shot:
        return _web_shot(args)
    if args.inspect:
        from .inspect import format_summary, run_inspection
        report = run_inspection(args.inspect, seed=args.seed,
                                width=args.width or 132,
                                height=args.height or 60,
                                scale=args.inspect_scale)
        print(format_summary(report))
        if report.get("studio"):
            import os
            print("studio: %s" % os.path.join(args.inspect,
                                              report["studio"]))
        return 1 if report["failed"] else 0
    from .game import Game
    game = Game(seed=args.seed, width=args.width, height=args.height,
                fps=args.fps, color=not args.no_color,
                demo_secs=args.demo, benchmark=args.benchmark,
                save_path=args.save)
    try:
        if args.screenshot:
            return _screenshot(game, args.screenshot)
        if args.benchmark:
            return _benchmark(game)
        if args.demo is not None and not sys.stdout.isatty():
            return _headless_demo(game, args.demo)
        return _play(game, demo=args.demo)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        return _fail("ALDERVALE stopped: %s" % exc,
                     "An unexpected error occurred inside the engine.",
                     "Report the message above with your terminal and "
                     "Python version.")


def _web_shot(args):
    from pathlib import Path

    from .studio import find_browser, screenshot_studio

    html = Path(args.web_dir) / "index.html"
    if not html.is_file():
        return _fail("Studio page not found at %s." % html,
                     "The web shot needs the page written by a prior "
                     "--inspect run.",
                     "Run `python -m aldervale --inspect %s` first."
                     % args.web_dir)
    text = args.web_size.lower().replace(",", "x")
    try:
        width, height = (int(v) for v in text.split("x", 1))
    except ValueError:
        return _fail("--web-size must look like WxH.",
                     "The headless browser needs a pixel viewport.",
                     "Retry with e.g. --web-size 1600x1000.")
    if not (320 <= width <= 4000 and 240 <= height <= 4000):
        return _fail("--web-size is outside 320x240..4000x4000.",
                     "Very small or huge captures are not useful.",
                     "Retry with e.g. --web-size 1600x1000.")
    if find_browser() is None:
        return _fail("No Edge/Chrome browser was found.",
                     "Headless screenshots need a Chromium-family browser.",
                     "Install Edge or Chrome, set ALDERVALE_BROWSER to its "
                     "path, or open %s manually." % html)
    ok, detail = screenshot_studio(html, args.web_shot, args.web_query,
                                   (width, height))
    if not ok:
        return _fail("Headless screenshot failed: %s" % detail,
                     "The browser did not produce a usable image.",
                     "Retry, or open %s in a browser and capture it manually."
                     % html)
    print("wrote %s" % detail)
    return 0


def _play(game, demo=None):
    from .term import Terminal

    def progress(model, frac):
        game.term.write("\x1b[2J\x1b[HForging the realm... %3d%%  %s"
                        % (int(frac * 100), model))
        game.term.flush()

    with Terminal(color=game.color) as term:
        term.set_title("ALDERVALE - an ASCII chronicle")
        game.boot(term, progress=progress)
        if demo is not None:
            game.state = "title"
        return game.run()


def _screenshot(game, path):
    """Render one scripted vista to a plain text file (no terminal)."""
    import math

    game.boot(None)
    game.state = "play"
    game._ensure_camera()
    w = game.world
    kx, kz = w.terrain.castle
    game.cam = None
    from .render import Camera, Env, render_scene
    from .buffer import Screen
    from . import hud
    scr = Screen(game.w, game.h, color=game.color)
    cam = Camera(game.w, game.h, kx, kz + 52,
                 w.terrain.height(kx, kz + 52) + 6.0, math.pi, pitch=0.26)
    env = Env(0.24, 12.0)
    render_scene(scr, w, cam, env)
    hud.draw_hud(scr, w, env, 60)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(scr.frame_text() + "\n")
    except OSError as exc:
        return _fail("Cannot write screenshot to %s." % path,
                     "The path is unwritable: %s." % exc,
                     "Choose a writable file path.")
    return 0


def _benchmark(game):
    import time

    t0 = time.monotonic()
    game.boot(None)
    boot_t = time.monotonic() - t0
    game.state = "play"
    game.w, game.h = 132, 60
    game.screen = None
    game.cam = None
    game._open_screen()
    game._ensure_camera()
    from .render import Env
    env = Env(game.world.day_t, 0.0)
    frames = 60
    t0 = time.monotonic()
    for i in range(frames):
        game.world.update(1.0 / 30.0, env)
        game._render(env)
    dt = time.monotonic() - t0
    per = dt / frames * 1000.0
    print("boot %.1fs | %d frames in %.2fs | %.1f ms/frame | ~%d fps cap %d"
          % (boot_t, frames, dt, per, int(1000.0 / per) if per > 0 else 0,
             game.fps_cap))
    return 0


def _headless_demo(game, secs):
    """Non-interactive demo parity for pipes and CI (PRINCIPLE-015)."""
    import time

    game.boot(None)
    game.state = "play"
    game.demo_secs = secs
    game.w, game.h = 100, 46
    game._open_screen()
    game._ensure_camera()
    t_end = time.monotonic() + secs
    from .render import Env
    last = time.monotonic()
    while time.monotonic() < t_end:
        now = time.monotonic()
        dt = min(0.05, now - last)
        last = now
        game.cam_yaw += dt * 0.2
        env = Env(game.world.day_t, game.world.time)
        game.world.update(dt, env)
        game._render(env)
    print("demo: %ds headless, %d entities, quest=%s" %
          (int(secs), len(game.world.entities), game.world.quest))
    return 0


if __name__ == "__main__":
    sys.exit(run())
