"""Unit tier: fast in-process checks for the pure engine core."""

import io
import base64
import math
import os
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr
from types import SimpleNamespace

sys.path.insert(0, ".")

from aldervale import math3d as m3
from aldervale import models
from aldervale.atlas import SpriteAtlas
from aldervale.buffer import FAR, NEAREST, Screen, pack_rgb
from aldervale.capture import png_bytes, save_png, screen_pixels
from aldervale.gfx import FrameBuffer
from aldervale.gfxatlas import PixelAtlas, bake_pixel_sprite
from aldervale.gfxmodels import ModelRenderer
from aldervale.gfxmodels import _raster_tri_smooth
from aldervale.gfxrender import GfxCamera
from aldervale.inspect import build_game
from aldervale.webglclient import PLAY3D_HTML
from aldervale.webglscene import (MeshAtlas as GLMeshAtlas,
                                  model_bundle as gl_model_bundle,
                                  scene as gl_scene,
                                  world_bundle as gl_world_bundle)
from aldervale.mesh import EDGE_CHARS, RAMP, MeshBuilder, bake_sprite
from aldervale.noise import fbm, value_noise
from aldervale.render import Camera
from aldervale.rules import (ARMOR_ORDER, ITEMS, WEAPON_ORDER, Inventory,
                             damage_roll, xp_for_level)
from aldervale import launcher
from aldervale.studio import (collect_models, encode_screen, find_browser,
                              screenshot_studio, write_studio)
from aldervale.webgame import WebTerm, encode_frame
from aldervale.entities import eid_hash
from aldervale.hud import wrap_text

import random


class FakeTerm:
    def __init__(self):
        self.written = []
        self.flushes = 0

    def write(self, s):
        self.written.append(s)

    def flush(self):
        self.flushes += 1


class TestNoise(unittest.TestCase):
    def test_deterministic_and_bounded(self):
        a = [value_noise(x * 0.3, y * 0.3, 5) for x in range(8)
             for y in range(8)]
        b = [value_noise(x * 0.3, y * 0.3, 5) for x in range(8)
             for y in range(8)]
        self.assertEqual(a, b)
        for v in a:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_fbm_smooth(self):
        v1 = fbm(1.0, 1.0, 9, 3)
        v2 = fbm(1.05, 1.0, 9, 3)
        self.assertLess(abs(v1 - v2), 0.1)
        self.assertGreaterEqual(v1, 0.0)
        self.assertLessEqual(v1, 1.0)


class TestMath3d(unittest.TestCase):
    def test_rot_y_maps_front(self):
        v = m3.mat_vec(m3.rot_y_matrix(0.5), (0.0, 0.0, 1.0))
        self.assertAlmostEqual(v[0], 0.479426, places=5)
        self.assertAlmostEqual(v[1], 0.0, places=5)
        self.assertAlmostEqual(v[2], 0.877582, places=5)

    def test_identity(self):
        m = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        self.assertEqual(m3.mat_vec(m, (1, 2, 3)), (1.0, 2.0, 3.0))

    def test_face_normal_unit_and_direction(self):
        n = m3.face_normal((0, 0, 0), (1, 0, 0), (0, 1, 0))
        self.assertAlmostEqual(n[2], 1.0, places=5)
        self.assertAlmostEqual(m3.length(n), 1.0, places=5)


class TestScreen(unittest.TestCase):
    def test_set_respects_bounds_and_depth(self):
        s = Screen(10, 6, color=False)
        s.set(2, 2, "#", 1, depth=5.0)
        s.set(2, 2, "o", 1, depth=6.0)
        self.assertEqual(s.chars[2][2], "#")
        s.set(2, 2, "o", 1, depth=4.0)
        self.assertEqual(s.chars[2][2], "o")
        s.set(-1, 0, "x", 1)
        s.set(0, 99, "x", 1)
        self.assertEqual(s.stats(), 1)

    def test_text_overrides_with_nearest_depth(self):
        s = Screen(20, 5, color=False)
        s.set(3, 1, "#", 1, depth=2.0)
        s.text(0, 1, "hello", 1)
        self.assertEqual("".join(s.chars[1][:5]), "hello")
        self.assertEqual(s.depth[1][3], NEAREST)

    def test_box_draws_frame(self):
        s = Screen(20, 8, color=False)
        s.box(2, 2, 8, 4, 1)
        self.assertEqual(s.chars[2][2], "+")
        self.assertEqual(s.chars[2][9], "+")
        self.assertEqual(s.chars[5][2], "+")
        self.assertEqual(s.chars[3][2], "|")

    def test_ramp_is_wide_and_unique(self):
        from aldervale.buffer import RAMP
        self.assertGreaterEqual(len(RAMP), 16)
        self.assertEqual(len(set(RAMP)), len(RAMP))

    def test_downsample_keeps_edge_colour_with_smooth_glyph(self):
        from aldervale.mesh import Sprite
        sp = Sprite(["#.", ".."], [[0xFFFFFF, 0x101010],
                                   [0x101010, 0x101010]])
        s = Screen(4, 2, color=True)
        s.blit(sp, 2.0, 2.0, 1.0)
        self.assertNotEqual(s.chars[1][1], " ")
        self.assertEqual(s.fg[1][1], 0xFFFFFF)

    def test_ground_tiles_are_rectangular(self):
        from aldervale.render import GROUND_TILES
        for row in GROUND_TILES:
            for text in row:
                self.assertEqual(len(text), 16)

    def test_box_fill_clears_interior_and_none_keeps_it(self):
        s = Screen(12, 6, color=False)
        s.text(2, 2, "XXXXXXXX", 1)
        s.box(1, 1, 10, 4, 1, fill=" ")
        self.assertEqual("".join(s.chars[2][1:11]), "|        |")
        s2 = Screen(12, 6, color=False)
        s2.text(2, 2, "XXXXXXXX", 1)
        s2.box(1, 1, 10, 4, 1)
        self.assertIn("XXXX", "".join(s2.chars[2]))

    def test_blit_scales_and_occludes(self):
        mesh = models.rock(seed=1)
        sp = bake_sprite(mesh, yaw=0.0, dist=9.0, f=120.0, aspect=0.5,
                         canvas=(30, 20))
        self.assertGreater(sp.filled(), 4)
        s = Screen(40, 24, color=False)
        s.fill_row(20, "#", 1, depth=1.0)
        s.blit(sp, 20.0, 22.0, 8.0, depth=2.0)
        filled = sum(1 for row in s.chars for ch in row if ch not in " #")
        self.assertGreater(filled, 4)

    def test_flush_diff_second_frame_small(self):
        s = Screen(30, 10, color=True)
        term = FakeTerm()
        s.text(0, 0, "alpha", 1)
        s.text(0, 5, "beta", 2)
        n1 = s.flush(term)
        n2 = s.flush(term)
        self.assertEqual(n2, 0)
        s.text(0, 0, "zzzzz", 1)
        n3 = s.flush(term)
        self.assertLess(n3, n1)
        self.assertTrue(any("zzzzz" in w for w in term.written))

    def test_frame_text_rows(self):
        s = Screen(5, 2, color=False)
        s.text(0, 0, "abcde", 1)
        self.assertEqual(s.frame_text(), "abcde\n     ")


class TestCapture(unittest.TestCase):
    def test_png_header_and_scanlines(self):
        s = Screen(4, 3, color=True)
        s.text(0, 0, "ABCD", pack_rgb(255, 0, 0))
        s.text(0, 1, "    ", pack_rgb(8, 10, 16))
        s.text(0, 2, "1234", pack_rgb(0, 255, 0))
        w, h, rows = screen_pixels(s, scale=1)
        blob = png_bytes(w, h, rows)
        self.assertEqual(blob[:8], b"\x89PNG\r\n\x1a\n")
        iw, ih = struct.unpack(">II", blob[16:24])
        self.assertEqual((iw, ih), (w, h))
        self.assertGreater(len(rows), w * h)
        idat_start = blob.index(b"IDAT") + 4
        size = struct.unpack(">I", blob[idat_start - 8:idat_start - 4])[0]
        raw = zlib.decompress(blob[idat_start:idat_start + size])
        self.assertEqual(len(raw), h * (w * 3 + 1))

    def test_glyph_pixels_use_cell_colour(self):
        s = Screen(1, 1, color=True)
        s.text(0, 0, "#", pack_rgb(255, 0, 0))
        w, h, rows = screen_pixels(s, scale=1)
        self.assertEqual(len(rows), w * h * 3)
        self.assertTrue(any(rows[i:i + 3] == b"\xff\x00\x00"
                            for i in range(0, len(rows), 3)))

    def test_save_png_writes_file(self):
        s = Screen(2, 1, color=True)
        s.text(0, 0, "OK", pack_rgb(10, 200, 20))
        d = tempfile.mkdtemp(prefix="aldervale_capture_")
        path = os.path.join(d, "frame.png")
        self.addCleanup(os.rmdir, d)
        self.addCleanup(os.remove, path)
        iw, ih = save_png(path, s, scale=1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertGreater(iw, 0)
        self.assertGreater(ih, 0)


class TestMesh(unittest.TestCase):
    def test_box_face_count(self):
        b = MeshBuilder()
        b.box(0, 0, 0, 1, 1, 1, 0x808080)
        mesh = b.build()
        self.assertEqual(len(mesh.verts), 24)
        self.assertEqual(len(mesh.faces), 6)

    def test_cone_and_sphere_face_counts(self):
        b = MeshBuilder()
        b.cone(0, 0, 0, 1.0, 1.0, seg=6)
        b.sphere(2, 0, 0, 1, 1, 1, seg=5, rings=3)
        mesh = b.build()
        self.assertEqual(len(mesh.faces), 6 + 5 * 3)

    def test_bake_sprite_chars_in_ramp(self):
        sp = bake_sprite(models.rock(seed=2), yaw=1.0, dist=9.0, f=100.0,
                         aspect=0.5, canvas=(26, 18))
        for row in sp.chars:
            for ch in row:
                self.assertIn(ch, RAMP + EDGE_CHARS)
        self.assertGreater(sp.filled(), 3)

    def test_bake_yaw_frames_differ(self):
        mesh = models.tree_pine(seed=1)
        a = bake_sprite(mesh, yaw=0.0, dist=9.0, f=60.0, aspect=0.5,
                        canvas=(40, 26))
        b = bake_sprite(mesh, yaw=2.0, dist=9.0, f=60.0, aspect=0.5,
                        canvas=(40, 26))
        self.assertNotEqual(a.chars, b.chars)

    def test_emissive_glow_separate(self):
        sp = bake_sprite(models.campfire(frame=1), yaw=0.0, dist=9.0,
                         f=140.0, aspect=0.5, canvas=(30, 22))
        self.assertIsNotNone(sp.glow)
        self.assertGreater(sp.glow.filled(), 0)
        plain = bake_sprite(models.rock(seed=3), yaw=0.0, dist=9.0,
                            f=100.0, aspect=0.5, canvas=(24, 16))
        self.assertIsNone(plain.glow)

    def test_house_carries_layered_architecture_detail(self):
        house = models.house()
        self.assertGreaterEqual(len(house.faces), 400)
        self.assertGreater(max(v[1] for v in house.verts), 3.70)
        smooth = sum(1 for f in house.faces if len(f) > 6 and f[6])
        self.assertGreaterEqual(smooth, 24)

    def test_knight_cape_and_shield_reach_behind_and_outboard(self):
        mesh = models.knight()
        xs = [v[0] for v in mesh.verts]
        zs = [v[2] for v in mesh.verts]
        self.assertLess(min(xs), -0.60, "shield no longer clears the body")
        self.assertLess(min(zs), -0.25, "cape is missing from the back")

    def test_boulders_are_rounded(self):
        rock = models.rock()
        smooth = sum(1 for f in rock.faces if len(f) > 6 and f[6])
        self.assertGreaterEqual(smooth, 40)

    def test_campfire_has_a_stone_ring_logs_and_layered_flames(self):
        fire = models.campfire(frame=1)
        emissive = sum(1 for f in fire.faces if f[5])
        self.assertGreaterEqual(len(fire.faces), 120)
        self.assertGreaterEqual(emissive, 40)
        ys = [v[1] for v in fire.verts]
        xs = [v[0] for v in fire.verts]
        self.assertLess(max(ys), 0.95)
        self.assertLessEqual(max(xs) - min(xs), 1.5)
        shapes = {tuple(sorted({round(v[1], 2) for v in
                                models.campfire(f).verts}))
                  for f in range(4)}
        self.assertEqual(len(shapes), 4, "the four fire frames must differ")

    def test_torch_flame_is_compact_and_basketed(self):
        torch = models.torch(frame=1)
        ys = [v[1] for v in torch.verts]
        self.assertLess(max(ys), 2.12)
        self.assertGreaterEqual(len(torch.faces), 48)
        emissive = sum(1 for f in torch.faces if f[5])
        self.assertGreaterEqual(emissive, 20)

    def test_well_has_a_stone_rim_thatch_and_crank(self):
        well = models.well()
        ys = [v[1] for v in well.verts]
        self.assertGreaterEqual(len(well.faces), 180)
        self.assertGreater(max(ys), 2.10)
        self.assertLess(max(ys), 2.40)

    def test_windmill_has_a_tower_and_eight_blade_frames(self):
        mill = models.windmill(frame=0)
        ys = [v[1] for v in mill.verts]
        xs = [v[0] for v in mill.verts]
        self.assertGreaterEqual(len(mill.faces), 100)
        self.assertGreater(max(ys), 9.5)
        self.assertLess(max(ys), 10.6)
        self.assertGreaterEqual(max(xs) - min(xs), 8.5)
        shapes = {tuple(sorted({(round(v[0], 1), round(v[1], 1))
                                for v in models.windmill(f).verts}))
                  for f in range(8)}
        self.assertEqual(len(shapes), 8, "eight distinct blade frames")


class TestStudio(unittest.TestCase):
    def test_encode_screen_keeps_cells_and_colours(self):
        s = Screen(4, 2, color=True)
        s.text(0, 0, "AB", 0x112233)
        frame = encode_screen(s)
        self.assertEqual((frame["w"], frame["h"]), (4, 2))
        self.assertTrue(frame["chars"][0].startswith("AB"))
        self.assertEqual(frame["colors"][0][0], 0x112233)
        self.assertEqual(len(frame["colors"]), 2)

    def test_collect_models_samples_yaws_and_skips_missing(self):
        atlas = SpriteAtlas().build(keys=["knight"])
        data = collect_models(atlas)
        self.assertEqual(len(data["yaw_indices"]), 8)
        self.assertIn("knight", data["entries"])
        self.assertNotIn("captain", data["entries"])
        frames = data["entries"]["knight"]["idle"]
        self.assertEqual(len(frames), 8)
        self.assertGreater(frames[0]["w"], 0)

    def test_knight_turnaround_frames_are_distinct(self):
        atlas = SpriteAtlas().build(keys=["knight"])
        data = collect_models(atlas)
        frames = data["entries"]["knight"]["idle"]
        rows = {"".join(f["chars"]) for f in frames}
        self.assertEqual(len(rows), len(data["yaw_indices"]))

    def test_write_studio_roundtrip(self):
        import json
        s = Screen(3, 2, color=True)
        s.text(0, 0, "AB", 0x224466)
        with tempfile.TemporaryDirectory() as d:
            html, data = write_studio(d, 7, [3, 2],
                                      [{"name": "tiny", "day_t": 0.2,
                                        "frame": encode_screen(s)}],
                                      {"entries": {}}, [])
            with open(html, encoding="utf-8") as f:
                page = f.read()
            with open(data, encoding="utf-8") as f:
                blob = f.read()
        self.assertIn("Aldervale Studio", page)
        self.assertTrue(blob.startswith("window.STUDIO = "))
        parsed = json.loads(blob[len("window.STUDIO = "):].rstrip(";\n"))
        self.assertEqual(parsed["scenes"][0]["name"], "tiny")

    def test_find_browser_returns_none_or_a_real_path(self):
        found = find_browser()
        if found is not None:
            self.assertTrue(os.path.isfile(found), found)

    def test_screenshot_missing_page_fails_cleanly(self):
        ok, detail = screenshot_studio("no/such/index.html", "shot.png")
        self.assertFalse(ok)
        self.assertTrue(detail)


class TestLauncherUnit(unittest.TestCase):
    def test_fixed_launch_commands(self):
        self.assertEqual(launcher.game_command("play"),
                         [sys.executable, "-m", "aldervale"])
        self.assertEqual(launcher.game_command("demo"),
                         [sys.executable, "-m", "aldervale",
                          "--demo", "9"])

    def test_page_injects_token(self):
        page = launcher.render_page("token-123")
        self.assertIn("token-123", page)
        self.assertNotIn("__TOKEN__", page)
        self.assertIn("START GAME", page)
        self.assertIn("/studio/", page)
        self.assertIn("autostart", page)

    def test_launcher_url_and_health_helpers(self):
        self.assertEqual(launcher.launcher_url(8765),
                         "http://127.0.0.1:8765/")
        self.assertEqual(launcher.launcher_url(8765, True),
                         "http://127.0.0.1:8765/?autostart=1")
        self.assertFalse(launcher.check_health(0))

    def test_studio_file_rejects_traversal(self):
        self.assertIsNone(launcher._studio_file("../secrets.txt"))
        self.assertIsNone(launcher._studio_file("/etc/passwd"))
        self.assertIsNone(launcher._studio_file(".hidden"))


class TestWebGameUnit(unittest.TestCase):
    def test_encode_frame_returns_rows(self):
        s = Screen(4, 2, color=True)
        s.text(0, 0, "AB", 0x123456)
        frame = encode_frame(s)
        self.assertEqual(frame["chars"][0][:2], "AB")
        self.assertEqual(frame["colors"][0][0], 0x123456)
        self.assertEqual(len(frame["colors"]), 2)
        self.assertNotIn("gfx", frame)

    def test_encode_frame_carries_column_major_pixels(self):
        s = Screen(2, 1, color=True)
        fb = FrameBuffer(2, 1)
        fb.fill_column(0, 0, 1, 0x010203)
        fb.fill_column(1, 0, 1, 0x040506)
        frame = encode_frame(s, fb)
        self.assertEqual(frame["gfx"]["w"], 2)
        self.assertEqual(frame["gfx"]["h"], 1)
        raw = base64.b64decode(frame["gfx"]["rgb"])
        self.assertEqual(raw, bytes((1, 2, 3, 4, 5, 6)))

    def test_web_term_queues_input_and_ignores_output(self):
        term = WebTerm(80, 40)
        term.pressed.extend(["w", "space"])
        term.held = {"w", "shift"}
        term.mouse = [("ldown", 4, 5, 1, 0)]
        pressed, held = term.poll()
        self.assertEqual(pressed, ["w", "space"])
        self.assertEqual(held, {"w", "shift"})
        self.assertEqual(term.poll(), ([], {"w", "shift"}))
        self.assertEqual(term.take_mouse(), [("ldown", 4, 5, 1, 0)])
        self.assertEqual(term.take_mouse(), [])
        self.assertEqual(term.size(), (80, 40))
        self.assertIsNone(term.flush())

    def test_queued_mouse_events_stay_bounded(self):
        import threading

        from aldervale.webgame import MAX_QUEUED_MOUSE, WebGame

        session = object.__new__(WebGame)
        session.lock = threading.RLock()
        session.term = WebTerm(80, 40)
        burst = [["move", 10, 10, 2, 0] for _ in range(8)]
        for _ in range(40):
            session.set_input(pressed=[], held=[], mouse=burst)
        self.assertEqual(len(session.term.mouse), MAX_QUEUED_MOUSE)
        self.assertEqual(session.term.mouse[-1], ("move", 10, 10, 2, 0),
                         "the newest events survive the cap")


class TestAtlas(unittest.TestCase):
    def test_yaw_frame_wraparound(self):
        atlas = SpriteAtlas()
        self.assertEqual(atlas.yaw_frame(0.0, 0.0),
                         atlas.yaw_frame(6.28318, 0.0))
        self.assertEqual(len(set(atlas.yaw_frame(a, 0.0)
                                 for a in (0, 1, 2, 3, 4, 5))), 6)

    def test_heights_registered(self):
        atlas = SpriteAtlas()
        self.assertGreater(atlas.heights["castle"], 10)
        self.assertLess(atlas.heights["chicken"], 1)


class TestGfx(unittest.TestCase):
    def test_framebuffer_column_fill_and_depth(self):
        fb = FrameBuffer(4, 3)
        fb.fill_column(1, 0, 3, 0x112233, 2.5)
        self.assertEqual(fb.sample_depth(1, 0), 2.5)
        self.assertEqual(fb.sample_depth(1, 2), 2.5)
        self.assertEqual(fb.sample_depth(0, 0), FAR)
        self.assertEqual(tuple(fb.data[1 * 3 * 3:1 * 3 * 3 + 3]),
                         (0x11, 0x22, 0x33))

    def test_framebuffer_blend_and_row_major_scale(self):
        fb = FrameBuffer(2, 2)
        fb.set(0, 0, 0x000000)
        fb.blend(0, 0, 0xFFFFFF, 0.5)
        self.assertEqual(tuple(fb.data[:3]), (127, 127, 127))
        w, h, rgb = fb.to_row_major(scale=2)
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(rgb[:3], bytes((127, 127, 127)))
        self.assertEqual(rgb[3:6], bytes((127, 127, 127)))

    def test_bake_pixel_sprite_crops_and_sets_alpha(self):
        mesh = MeshBuilder()
        mesh.box(0, 0.5, 0, 1, 1, 1, 0x808080)
        sprite = bake_pixel_sprite(mesh.build(), yaw=0.0, dist=5.0, f=40.0,
                                   aspect=1.0, canvas=(60, 60))
        self.assertGreater(sprite.w, 0)
        self.assertLess(sprite.w, 60)
        self.assertGreater(sprite.h, 0)
        self.assertLess(sprite.h, 60)
        self.assertGreater(sprite.filled(), 100)
        self.assertEqual(len(sprite.rgba), sprite.w * sprite.h * 4)
        self.assertTrue(any(sprite.rgba[i] == 255
                            for i in range(3, len(sprite.rgba), 4)))

    def test_bake_pixel_sprite_keeps_emissive_glow(self):
        sprite = bake_pixel_sprite(models.campfire(frame=0), yaw=0.0,
                                   dist=5.0, f=40.0, aspect=1.0,
                                   canvas=(60, 60))
        self.assertIsNotNone(sprite.glow)
        self.assertGreater(sprite.glow.filled(), 0)

    def test_pixel_atlas_builds_a_model_and_reports_steps(self):
        atlas = PixelAtlas()
        self.assertGreater(atlas.heights["castle"], 10)
        atlas.build(keys=["chicken"])
        row = atlas.frames[("chicken", "idle")]
        self.assertEqual(len(row), 12)
        self.assertEqual(atlas.steps_for("chicken", "idle"), 12)
        sprite = atlas.get("chicken", "idle", 3)
        self.assertGreater(sprite.filled(), 10)

    def test_gfx_camera_keeps_the_cell_view_alignment(self):
        cam = Camera(132, 60, 10.0, 20.0, 5.0, 1.2, pitch=0.3, dist=4.6)
        gcam = GfxCamera.from_camera(cam, 320, 180)
        self.assertAlmostEqual(gcam.f, cam.f * 320 / 132)
        self.assertAlmostEqual(gcam.fy, cam.fy * 3)
        self.assertEqual(gcam.w, 320)
        self.assertEqual(gcam.h, 180)
        self.assertLess(abs(gcam.col_angle[160]), 0.01)
        self.assertGreater(gcam.horizon, 0)


    def test_model_renderer_draws_real_mesh_geometry(self):
        builder = MeshBuilder()
        builder.box(0, 0.5, 0, 1, 1, 1, 0x808080)
        builder.box(0.55, 0.75, 0, 0.3, 0.3, 0.3, 0xCC4444)
        mesh = builder.build()

        class CubeAtlas:
            def mesh_for(self, model, pose):
                return mesh

        cam = Camera(132, 60, 0.0, 4.6, 2.4, math.pi, pitch=0.3,
                     dist=4.6)
        gcam = GfxCamera.from_camera(cam, 288, 162)
        ent = SimpleNamespace(model="cube", pose="idle", x=0.0, z=0.0,
                              yaw=0.0, height=1.0, scale=1.0, y_off=0.0,
                              ground_y=0.0, flash=0.0, flash_color=None)
        fb = FrameBuffer(288, 162)
        renderer = ModelRenderer(CubeAtlas())
        first = renderer.draw(fb, gcam, ent, 1.0, 1.0, 1.0)
        self.assertGreater(first, 100)
        self.assertLess(fb.sample_depth(144, 120), 1e8)
        before = bytes(fb.data)
        ent.yaw = math.pi
        fb.clear()
        second = renderer.draw(fb, gcam, ent, 1.0, 1.0, 1.0)
        self.assertGreater(second, 100)
        self.assertNotEqual(before, bytes(fb.data),
                            "rotating the model must change the pixels")

    def test_framebuffer_pattern_fill_repeats_and_sets_depth(self):
        fb = FrameBuffer(1, 5)
        pattern = bytes((10, 20, 30, 40, 50, 60))
        fb.fill_column_pattern(0, 0, 5, pattern, 1.5)
        self.assertEqual(tuple(fb.data[0:3]), (10, 20, 30))
        self.assertEqual(tuple(fb.data[3:6]), (40, 50, 60))
        self.assertEqual(tuple(fb.data[6:9]), (10, 20, 30))
        self.assertEqual(fb.depth, [1.5] * 5)

    def test_smooth_triangle_interpolates_the_shade_table(self):
        fb = FrameBuffer(4, 4)
        table = [pack_rgb(i * 12, 0, 0) for i in range(16)]
        tri = ((0.0, 0.0, 1.0, 0.35),
               (4.0, 0.0, 1.0, 1.0),
               (0.0, 4.0, 1.0, 0.35))
        written = _raster_tri_smooth(fb.data, fb.depth, 4, 4, tri, table)
        self.assertGreater(written, 0)
        self.assertLess(fb.sample_depth(1, 1), 1e8)

    def test_model_renderer_depth_bias_composites_over_foreground(self):
        builder = MeshBuilder()
        builder.box(0, 0.5, 0, 1, 1, 1, 0x808080)
        mesh = builder.build()

        class CubeAtlas:
            def mesh_for(self, model, pose):
                return mesh

        cam = Camera(132, 60, 0.0, 4.6, 2.4, math.pi, pitch=0.3,
                     dist=4.6)
        gcam = GfxCamera.from_camera(cam, 288, 162)
        ent = SimpleNamespace(model="cube", pose="idle", x=0.0, z=0.0,
                              yaw=0.0, height=1.0, scale=1.0, y_off=0.0,
                              ground_y=0.0, flash=0.0, flash_color=None)
        fb = FrameBuffer(288, 162)
        for i in range(len(fb.depth)):
            fb.depth[i] = 2.0
        renderer = ModelRenderer(CubeAtlas())
        self.assertEqual(renderer.draw(fb, gcam, ent, 1, 1, 1), 0,
                         "foreground depth must hide the model without bias")
        written = renderer.draw(fb, gcam, ent, 1, 1, 1, depth_bias=3.0)
        self.assertGreater(written, 100)
        self.assertGreater(fb.sample_depth(144, 120), 2.0,
                           "the composite writes the model's real depth")

    def test_pixel_atlas_exposes_meshes_for_runtime_3d(self):
        atlas = PixelAtlas()
        atlas.build(keys=["chicken"])
        self.assertIsNotNone(atlas.mesh_for("chicken", "idle"))
        self.assertIsNone(atlas.mesh_for("castle", "idle"))


class TestWebGL(unittest.TestCase):
    def test_model_bundle_covers_every_pose(self):
        atlas = GLMeshAtlas().build(keys=["knight"])
        bundle = gl_model_bundle(atlas)
        entry = bundle["meta"]["knight"]["idle"]
        self.assertGreater(entry["count"], 100)
        pos = base64.b64decode(bundle["pos"])
        col = base64.b64decode(bundle["col"])
        norm = base64.b64decode(bundle["norm"])
        total = sum(pose["count"]
                    for poses in bundle["meta"].values()
                    for pose in poses.values())
        self.assertEqual(len(pos), total * 3 * 4)
        self.assertEqual(len(col), total * 3)
        self.assertEqual(len(norm), total * 3)
        self.assertNotEqual(set(col[:60]), {0})

    def test_world_scene_and_raycast(self):
        game = build_game(seed=3, width=132, height=60, terrain_size=48,
                          atlas_keys=["knight"], render_mode="webgl")
        game._update_camera(force=True)
        game.tick(0.0)
        game._render(game._last_env)
        bundle = gl_world_bundle(game.world)
        self.assertEqual(bundle["meta"]["w"], 48)
        self.assertGreater(len(bundle["heights"]), 0)
        payload = gl_scene(game, game.world, 1)
        self.assertEqual(payload["status"], "ready")
        self.assertIn("camera", payload)
        self.assertTrue(payload["entities"])
        self.assertTrue(payload["hud"]["chars"])
        self.assertIn("kind", payload["entities"][0])
        self.assertIsInstance(payload["lights"], list)
        self.assertTrue(payload["lights"])
        self.assertLessEqual(len(payload["lights"]), 6)
        for light in payload["lights"]:
            self.assertIn("f", light)
            self.assertGreaterEqual(light["f"], 0.0)
            self.assertLessEqual(light["f"], 1.0)
        self.assertIsNotNone(payload["hud_status"])
        status = payload["hud_status"]
        self.assertEqual(status["name"], game.world.player.name)
        self.assertEqual(status["max_hp"], game.world.player.max_hp)
        self.assertIn("quest", status)
        self.assertGreaterEqual(status["gold"], 0)
        self.assertTrue(payload["show_map"])
        self.assertGreaterEqual(len(payload["smoke"]), 3)
        for puff in payload["smoke"]:
            self.assertEqual(set(puff), {"x", "y", "z", "phase"})
        self.assertIn("x", payload["player"])
        colors = base64.b64decode(bundle["colors"])
        self.assertEqual(len(colors), 48 * 48 * 4)
        self.assertGreater(max(colors[3::4]), 0,
                           "terrain material ids should ride in the alpha")
        game.show_map = False
        self.assertFalse(gl_scene(game, game.world, 2)["show_map"])
        point = game.pick_world(66, 50)
        self.assertIsNotNone(point, "the WebGL click ray should hit terrain")

    def test_webgl_page_has_a_token_slot(self):
        self.assertIn("__TOKEN__", PLAY3D_HTML)
        self.assertIn("webgl2", PLAY3D_HTML.lower())
        self.assertIn("uWet", PLAY3D_HTML)
        self.assertIn("uSnowCap", PLAY3D_HTML)
        self.assertIn("uPointFlick", PLAY3D_HTML)
        self.assertIn("uSunCol", PLAY3D_HTML)
        self.assertIn("uRain", PLAY3D_HTML)
        self.assertIn("weatherEnv", PLAY3D_HTML)
        self.assertIn("uCloudAmt", PLAY3D_HTML)
        self.assertIn("uStarVis", PLAY3D_HTML)
        self.assertIn("uSunLight", PLAY3D_HTML)
        self.assertIn("cloudShade", PLAY3D_HTML)
        self.assertIn("lightningAt", PLAY3D_HTML)
        self.assertIn("float wisps", PLAY3D_HTML)
        self.assertIn("cloudCol", PLAY3D_HTML)
        self.assertIn("drawStatusPanel", PLAY3D_HTML)
        self.assertIn("hud_status", PLAY3D_HTML)
        self.assertIn("hudBar", PLAY3D_HTML)
        self.assertIn("mapCanvas", PLAY3D_HTML)
        self.assertIn("drawImage(mapCanvas", PLAY3D_HTML)

    def test_webgl_compact_hud_keeps_rows_apart(self):
        self.assertIn("const barH = compact ? 8 : 11;", PLAY3D_HTML)
        self.assertIn("const barY = y + (compact ? 19 : 30);", PLAY3D_HTML)
        self.assertIn("const barBottom = barY + barH;", PLAY3D_HTML)
        self.assertIn("barY + barH + (compact ? 11 : 12)", PLAY3D_HTML)
        self.assertIn("const questY = y + h - (compact ? 5 : 11);",
                      PLAY3D_HTML)
        # Smallest stage that still draws the panel: 11px rows, 5.2-row scrim.
        panel_h = 11 * 5.2
        bar_y, bar_h = 19, 8
        gear_y = max(panel_h - 20, bar_y + bar_h + 11)
        self.assertGreater(gear_y - 9, bar_y + bar_h,
                           "9px gear glyphs must clear the bars")
        quest_y = panel_h - 5
        self.assertGreater(quest_y - 10, gear_y + 2,
                           "10px quest glyphs must clear the gear line")
        self.assertLess(quest_y, panel_h)

    def test_webgl_page_draws_additive_light_glow(self):
        self.assertIn("function drawLightGlow", PLAY3D_HTML)
        self.assertIn('globalCompositeOperation = "lighter"', PLAY3D_HTML)
        self.assertIn("function projectLight", PLAY3D_HTML)
        self.assertIn("lightGlowRadius", PLAY3D_HTML)
        self.assertIn("1.0 - scene.env.daylight", PLAY3D_HTML)

    def test_webgl_page_draws_chimney_smoke(self):
        self.assertIn("function drawChimneySmoke", PLAY3D_HTML)
        self.assertIn("scene.smoke", PLAY3D_HTML)
        self.assertIn("function projectPoint", PLAY3D_HTML)
        self.assertIn("drawChimneySmoke(cssW, cssH)", PLAY3D_HTML)

    def test_webgl_page_shades_metal_with_rim_and_sheen(self):
        self.assertIn("float metal", PLAY3D_HTML)
        self.assertIn("float rimLight", PLAY3D_HTML)
        self.assertIn("float sheen", PLAY3D_HTML)

    def test_windmill_atlas_exposes_eight_blade_poses(self):
        atlas = GLMeshAtlas().build(keys=["windmill"])
        self.assertEqual(len(atlas.meshes), 8)
        for i in range(8):
            self.assertIsNotNone(atlas.mesh_for("windmill",
                                                "blades%d" % i))


class TestRules(unittest.TestCase):
    def test_damage_roll_bounds(self):
        rng = random.Random(1)
        for _ in range(50):
            d = damage_roll(10, 2, rng)
            self.assertGreaterEqual(d, 1)
            self.assertLessEqual(d, 14)

    def test_damage_roll_defence_reduces(self):
        rng = random.Random(2)
        low = sum(damage_roll(10, 0, rng) for _ in range(30))
        high = sum(damage_roll(10, 8, rng) for _ in range(30))
        self.assertGreater(low, high)

    def test_xp_curve_monotonic(self):
        levels = [xp_for_level(l) for l in range(1, 10)]
        self.assertEqual(levels, sorted(levels))
        self.assertGreater(levels[-1], levels[0])

    def test_inventory_ops(self):
        inv = Inventory()
        inv.add("potion", 3)
        inv.remove("potion", 1)
        self.assertEqual(inv.count("potion"), 2)
        inv.remove("potion", 5)
        self.assertEqual(inv.count("potion"), 0)
        self.assertEqual(inv.weapon_atk(), ITEMS["rusty_sword"].atk)
        self.assertEqual(inv.armor_dfn(), ITEMS["tunic"].dfn)

    def test_item_ordering_sensible(self):
        atks = [ITEMS[w].atk for w in WEAPON_ORDER]
        self.assertEqual(atks, sorted(atks))
        dfns = [ITEMS[a].dfn for a in ARMOR_ORDER]
        self.assertEqual(dfns, sorted(dfns))


class TestHudHelpers(unittest.TestCase):
    def test_wrap_text(self):
        lines = wrap_text("the quick brown fox jumps over the lazy dog", 12)
        for line in lines:
            self.assertLessEqual(len(line), 12)
        self.assertEqual(" ".join(lines),
                         "the quick brown fox jumps over the lazy dog")

    def test_eid_hash_stable(self):
        self.assertEqual(eid_hash("e12"), eid_hash("e12"))
        self.assertNotEqual(eid_hash("e12"), eid_hash("e13"))


class TestCliValidation(unittest.TestCase):
    def _run(self, argv):
        from aldervale.__main__ import run
        err = io.StringIO()
        with redirect_stderr(err):
            code = run(argv)
        return code, err.getvalue()

    def test_bad_fps_refused(self):
        code, err = self._run(["--fps", "3"])
        self.assertEqual(code, 1)
        self.assertIn("What:", err)
        self.assertIn("Why:", err)
        self.assertIn("Fix:", err)

    def test_bad_width_refused(self):
        code, _ = self._run(["--width", "9999"])
        self.assertEqual(code, 1)

    def test_bad_demo_seconds_refused(self):
        code, _ = self._run(["--demo", "-2"])
        self.assertEqual(code, 1)

    def test_bad_gfx_size_refused(self):
        code, err = self._run(["--gfx-shot", "frame.png",
                               "--gfx-size", "10x10"])
        self.assertEqual(code, 1)
        self.assertIn("What:", err)

    def test_unknown_gfx_scene_refused(self):
        code, err = self._run(["--gfx-shot", "frame.png",
                               "--gfx-scene", "nowhere"])
        self.assertEqual(code, 1)
        self.assertIn("Use one of:", err)


class TestReviewRegressions(unittest.TestCase):
    """Regressions for defects found in the aldervale code review."""

    def test_pack_rgb_clamps_channels(self):
        self.assertEqual(pack_rgb(300, 280, 290), pack_rgb(255, 255, 255))
        self.assertEqual(pack_rgb(-5, -1, 0), 0)
        self.assertEqual(pack_rgb(255.6, 254.9, 0.4), pack_rgb(255, 254, 0))

    def test_water_fog_reaches_fog_colour(self):
        from types import SimpleNamespace

        from aldervale.buffer import unpack_rgb
        from aldervale.render import Camera, Env, _terrain
        W = 64
        water = 1.4
        ter = SimpleNamespace(
            W=W, water=water,
            heights=[[water - 2.0] * W for _ in range(W)],
            colors=[[0x408030] * W for _ in range(W)],
            lights=[[200] * W for _ in range(W)],
        )
        scr = Screen(48, 24, color=True)
        cam = Camera(48, 24, 32.0, 32.0, water + 9.0, 0.0)
        env = Env(0.25, 3.0)
        _terrain(scr, ter, cam, env)
        row = cam.horizon
        r, g, b = unpack_rgb(scr.fg[row][24])
        fr, fgc, fb = unpack_rgb(env.fog)
        self.assertLess(abs(r - fr), 40, "water red channel misses fog")
        self.assertLess(abs(g - fgc), 40, "water green channel misses fog")
        self.assertLess(abs(b - fb), 40, "water blue channel misses fog")

    def test_terminal_min_width_clamped(self):
        from aldervale.game import Game

        class TinyTerm:
            def size(self):
                return (30, 20)

        g = Game(seed=1)
        g.term = TinyTerm()
        g._open_screen()
        self.assertGreaterEqual(g.w, 40)
        self.assertLessEqual(g.w, 260)

    def test_terminal_uses_large_viewport(self):
        from aldervale.game import Game

        class BigTerm:
            def size(self):
                return (250, 106)

        g = Game(seed=1)
        g.term = BigTerm()
        g._open_screen()
        self.assertEqual(g.w, 250)
        self.assertEqual(g.h, 105)


class TestStoryData(unittest.TestCase):
    """The story module is the single source of narrative truth."""

    def test_cast_entries_are_complete(self):
        from aldervale.story import CAST
        for key, entry in CAST.items():
            if isinstance(entry, tuple):
                for member in entry:
                    self.assertIn("name", member)
                    self.assertIn("model", member)
            else:
                self.assertIn("name", entry)
                self.assertIn("model", entry)

    def test_gate_guards_are_the_twins(self):
        from aldervale.story import CAST
        names = {g["name"] for g in CAST["guards"]}
        self.assertEqual(names, {"Ser Aldous", "Ser Aldric"})

    def test_dialogue_for_every_villager(self):
        from aldervale.story import CAST, dialogue_for
        for villager in CAST["villagers"]:
            payload = dialogue_for(villager["name"], "none")
            self.assertEqual(payload["name"], villager["name"])
            self.assertTrue(payload["pages"])
            self.assertIn(("Farewell", "close"), payload["choices"])

    def test_elder_dialogue_covers_quest_states(self):
        from aldervale.story import dialogue_for
        for state in ("none", "active", "return", "done"):
            payload = dialogue_for("Elder Quill", state)
            self.assertTrue(payload["pages"])
        offered = dialogue_for("Elder Quill", "none")
        self.assertIn("quest_accept", [a for _, a in offered["choices"]])
        returned = dialogue_for("Elder Quill", "return")
        self.assertIn("quest_complete", [a for _, a in returned["choices"]])

    def test_quest_objectives_cover_states(self):
        from aldervale.story import QUEST_OBJECTIVES
        self.assertEqual(set(QUEST_OBJECTIVES),
                         {"none", "active", "return", "done"})
        for text in QUEST_OBJECTIVES.values():
            self.assertTrue(text)

    def test_guard_dialogue_carries_twin_name(self):
        from aldervale.story import guard_dialogue
        payload = guard_dialogue("Ser Aldous")
        self.assertEqual(payload["name"], "Ser Aldous")
        self.assertTrue(payload["pages"])

    def test_player_name_single_source(self):
        from aldervale.entities import Player
        from aldervale.story import CAST
        self.assertEqual(Player("player", 0.0, 0.0).name,
                         CAST["player"]["name"])


class TestMouseAndOutline(unittest.TestCase):
    """Mouse event normalization and sprite silhouette outlines."""

    def test_mouse_event_normalization(self):
        from aldervale.term import _mouse_event
        self.assertEqual(_mouse_event(5, 6, 1, 0)[0], "ldown")
        self.assertEqual(_mouse_event(5, 6, 2, 0)[0], "rdown")
        self.assertEqual(_mouse_event(5, 6, 0, 1)[0], "move")
        self.assertEqual(_mouse_event(5, 6, 0, 0)[0], "up")
        wheel_up = _mouse_event(5, 6, 120 << 16, 4)
        self.assertEqual(wheel_up[0], "wheel")
        self.assertEqual(wheel_up[4], 1)
        wheel_down = _mouse_event(5, 6, (0xFFFF << 16) | 0xFFFF, 4)
        self.assertEqual(wheel_down[4], -1)

    def test_bake_sprite_has_silhouette_outline(self):
        from aldervale.mesh import OUTLINE_CHAR
        sp = bake_sprite(models.rock(seed=4), yaw=0.4, dist=9.0, f=120.0,
                         aspect=0.5, canvas=(30, 20))
        rows = sp.chars
        edges = 0
        for row in rows:
            stripped = row.strip()
            if stripped:
                if stripped[0] == OUTLINE_CHAR:
                    edges += 1
        self.assertGreater(edges, 2)

    def test_bake_flat_face_is_one_glyph(self):
        b = MeshBuilder()
        b.box(0.0, 0.0, 0.0, 1.4, 1.4, 1.4, 0xB0B0B0)
        sp = bake_sprite(b.build(), yaw=0.0, pitch=0.0, dist=9.0, f=120.0,
                         aspect=0.5, canvas=(40, 40))
        mid = sp.chars[sp.h // 2]
        interior = mid.strip(" ")[1:-1]
        self.assertEqual(len(set(interior)), 1, interior)


if __name__ == "__main__":
    unittest.main()
