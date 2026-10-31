"""Integration tier: world generation, quest chain, rendering and the CLI."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, ".")

from aldervale.atlas import SpriteAtlas
from aldervale.buffer import Screen
from aldervale.game import Game
from aldervale.inspect import (_reset, build_game, probe_controls,
                               run_inspection)
from aldervale.render import Camera, Env, render_scene
from aldervale.terrain import Terrain
from aldervale.webgame import WebGame
from aldervale.world import World

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMALL = 72


def _tiny_atlas():
    return SpriteAtlas().build(keys=["knight", "rock_s", "gold"])


class TestTerrain(unittest.TestCase):
    def test_deterministic(self):
        a = Terrain(11, size=SMALL, octaves=3)
        b = Terrain(11, size=SMALL, octaves=3)
        for z in (5, 20, 40, 60):
            for x in (5, 20, 40, 60):
                self.assertEqual(a.height(x, z), b.height(x, z))

    def test_village_flattened_and_walkable(self):
        t = Terrain(11, size=SMALL, octaves=3)
        vx, vz = t.village
        h_center = t.height(vx, vz)
        for dx, dz in ((0, 0), (3, 0), (-3, 2), (1, -4)):
            self.assertLess(abs(t.height(vx + dx, vz + dz) - h_center), 1.6)
        self.assertTrue(t.walkable(vx, vz))

    def test_island_has_sea_at_corners(self):
        t = Terrain(11, size=SMALL, octaves=3)
        W = t.W
        for x, z in ((2, 2), (W - 3, 2), (2, W - 3), (W - 3, W - 3)):
            self.assertLessEqual(t.height(x, z), t.water)

    def test_path_exists_between_village_and_castle(self):
        t = Terrain(11, size=SMALL, octaves=3)
        vx, vz = t.village
        kx, kz = t.castle
        steps = 30
        hits = 0
        for i in range(steps + 1):
            f = i / steps
            if t.is_path(vx + (kx - vx) * f, vz + (kz - vz) * f):
                hits += 1
        self.assertGreater(hits, 3)

    def test_materials_match_their_terrain(self):
        from aldervale.terrain import M_DIRT, M_ROCK, M_SAND
        t = Terrain(11, size=SMALL, octaves=3)
        vx, vz = t.village
        self.assertEqual(t.material(vx, vz), M_DIRT)
        self.assertEqual(t.material(2, 2), M_SAND)
        rocks = sum(1 for row in t.materials for m in row if m == M_ROCK)
        self.assertGreater(rocks, 10)

    def test_texture_grid_is_coherent(self):
        t = Terrain(11, size=SMALL, octaves=3)
        total = 0
        count = 0
        for z in range(2, SMALL - 2, 3):
            for x in range(2, SMALL - 2, 3):
                total += abs(t.texture_at(x, z) - t.texture_at(x + 1, z))
                total += abs(t.texture_at(x, z) - t.texture_at(x, z + 1))
                count += 2
        self.assertLess(total / count, 34.0)


class _FakeWorld:
    pass


class TestRenderScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terrain = Terrain(11, size=SMALL, octaves=3)
        cls.atlas = _tiny_atlas()

    def _world_with_entities(self):
        w = _FakeWorld()
        w.terrain = self.terrain
        w.atlas = self.atlas
        w.fireflies = []
        w.entities = []
        ter = self.terrain
        vx, vz = ter.village
        for i, model in enumerate(("knight", "rock_s", "knight")):
            w.entities.append(SimpleNamespace(
                model=model, pose="idle", x=vx + i * 2.0, z=vz - 4.0,
                yaw=math.pi, height=1.95, scale=1.0, y_off=0.0,
                ground_y=ter.height(vx + i * 2.0, vz - 4.0), flash=0.0,
                flash_color=None))
        return w

    def test_scene_fills_screen_with_sky_on_top(self):
        w = self._world_with_entities()
        scr = Screen(64, 30, color=True)
        vx, vz = self.terrain.village
        cam = Camera(64, 30, vx, vz + 14,
                     self.terrain.height(vx, vz + 14) + 3.2, math.pi)
        env = Env(0.25, 5.0)
        render_scene(scr, w, cam, env)
        self.assertGreater(scr.stats(), 300)
        top = "".join(scr.chars[0])
        self.assertIn(top[2], " .:,")

    def test_night_darkens_and_lights_fireflies(self):
        w = self._world_with_entities()
        w.fireflies = [(self.terrain.village[0] + 2,
                        self.terrain.village[1] - 2, 0.7)]
        scr = Screen(64, 30, color=True)
        vx, vz = self.terrain.village
        cam = Camera(64, 30, vx, vz + 14,
                     self.terrain.height(vx, vz + 14) + 3.2, math.pi)
        render_scene(scr, w, cam, Env(0.75, 5.0))
        day = Env(0.25, 5.0)
        self.assertLess(Env(0.75, 5.0).ambient[0], day.ambient[0])

    def test_entities_occluded_behind_terrain_depth(self):
        w = self._world_with_entities()
        scr = Screen(64, 30, color=True)
        vx, vz = self.terrain.village
        cam = Camera(64, 30, vx, vz + 14,
                     self.terrain.height(vx, vz + 14) + 3.2, math.pi)
        render_scene(scr, w, cam, Env(0.25, 5.0))
        self.assertIsNotNone(scr.depth[15])

    def _billboard(self, z):
        return SimpleNamespace(
            x=self.terrain.village[0], z=z, height=4.3, scale=1.0,
            ground_y=self.terrain.height(self.terrain.village[0], z),
            y_off=0.0, yaw=0.0, pose="idle", model="rock_s",
            flash=0.0, flash_color=None, kind="prop")

    def test_ground_clutter_adds_tufts_and_flowers(self):
        from aldervale.render import _terrain
        w = self._world_with_entities()
        scr = Screen(132, 60, color=True)
        vx, vz = self.terrain.village
        cam = Camera(132, 60, vx, vz + 14,
                     self.terrain.height(vx, vz + 14) + 3.2, math.pi)
        _terrain(scr, self.terrain, cam, Env(0.25, 2.0))
        text = "\n".join("".join(row) for row in scr.chars)
        self.assertTrue('"' in text or "*" in text,
                        "no grass tuft or flower detail in view")

    def test_castle_gate_has_two_animated_torches(self):
        w = World(3, None, terrain_size=SMALL)
        w.update(1.0 / 30.0, Env(0.25, 1.0))
        torches = [e for e in w.entities if e.model == "torch"]
        self.assertEqual(len(torches), 2)
        for t in torches:
            self.assertIn(t.pose, ("fire0", "fire1", "fire2", "fire3"))
            self.assertGreater(t.height, 2.0)

    def test_hurt_vignette_does_not_wipe_a_row(self):
        from aldervale.hud import draw_hurt_vignette
        w = World(3, None, terrain_size=SMALL)
        w.player.hurt_t = 0.4
        scr = Screen(80, 24, color=True)
        draw_hurt_vignette(scr, w)
        filled = sum(1 for ch in scr.chars[0] if ch != " ")
        self.assertLess(filled, 80 // 2, "vignette painted the whole top row")

    def test_location_names_follow_landmarks(self):
        from aldervale.hud import location_name
        w = World(3, None, terrain_size=SMALL)
        ter = w.terrain
        vx, vz = ter.village
        kx, kz = ter.castle
        cx, cz = ter.camp
        w.player.x, w.player.z = vx, vz
        self.assertEqual(location_name(w), "Aldervale")
        w.player.x, w.player.z = kx, kz
        self.assertEqual(location_name(w), "Suncrest Castle")
        w.player.x, w.player.z = cx, cz
        self.assertEqual(location_name(w), "The Bone Camp")

    def test_weather_overlays_draw_rain_and_snow(self):
        from aldervale.render import _weather
        rain = Screen(80, 40, color=True)
        _weather(rain, "rain", Env(0.66, 3.0))
        wet = sum(1 for row in rain.chars for ch in row
                  if ch in ("/", "\\", "|"))
        self.assertGreaterEqual(wet, 16)
        snow = Screen(80, 40, color=True)
        _weather(snow, "snow", Env(0.80, 3.0))
        flakes = sum(1 for row in snow.chars for ch in row
                     if ch in ("*", '"'))
        self.assertGreaterEqual(flakes, 18)
        clear = Screen(80, 40, color=True)
        _weather(clear, "clear", Env(0.66, 3.0))
        self.assertEqual(clear.stats(), 0)

    def test_wet_and_snowy_ground_change_the_palette(self):
        from aldervale.render import _terrain
        w = self._world_with_entities()
        vx, vz = self.terrain.village
        cam = Camera(80, 40, vx, vz + 14,
                     self.terrain.height(vx, vz + 14) + 3.2, math.pi)
        dry = Screen(80, 40, color=True)
        wet = Screen(80, 40, color=True)
        snow = Screen(80, 40, color=True)
        _terrain(dry, self.terrain, cam, Env(0.25, 2.0))
        _terrain(wet, self.terrain, cam, Env(0.25, 2.0), wet=0.20)
        _terrain(snow, self.terrain, cam, Env(0.25, 2.0), snow=0.22)
        changed_wet = sum(1 for y in range(40) for x in range(80)
                          if wet.fg[y][x] != dry.fg[y][x])
        changed_snow = sum(1 for y in range(40) for x in range(80)
                           if snow.fg[y][x] != dry.fg[y][x])
        self.assertGreater(changed_wet, 100)
        self.assertGreater(changed_snow, 100)

    def test_campfire_light_pool_warms_ground(self):
        from aldervale.render import _light_pools
        w = _FakeWorld()
        vx, vz = self.terrain.village
        cam = Camera(80, 40, vx, vz + 20,
                     self.terrain.height(vx, vz + 20) + 3.2, math.pi)
        gy = self.terrain.height(vx, vz + 10)
        w.entities = [SimpleNamespace(model="campfire", x=vx, z=vz + 10,
                                      ground_y=gy)]
        scr = Screen(80, 40, color=True)
        base = (40, 40, 40)
        packed = (base[0] << 16) | (base[1] << 8) | base[2]
        for y in range(40):
            for x in range(80):
                scr.set(x, y, ".", packed, 10.0)
        _light_pools(scr, w, cam, Env(0.80, 5.0))
        row = int(cam.horizon - (gy - cam.y) / 10.0 * cam.fy)
        col = 40
        color = scr.fg[row][col]
        r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
        self.assertGreater(r, base[0] + 20, "ground did not warm up")
        self.assertGreater(r, b, "light is not warm")

    def test_water_glitter_marks_the_sun_path(self):
        from aldervale.render import SUN_AZ, _terrain
        w = _FakeWorld()
        scr = Screen(96, 44, color=True)
        ter = self.terrain
        cam = Camera(96, 44, 8.0, 8.0, ter.water + 5.0, SUN_AZ)
        _terrain(scr, ter, cam, Env(0.25, 1.0))
        stars = sum(1 for row in scr.chars for ch in row if ch == "*")
        self.assertGreater(stars, 0, "no sun glitter on the water")

    def test_near_billboards_are_clipped(self):
        from aldervale.render import _entities
        w = self._world_with_entities()
        vx, vz = self.terrain.village
        cam_z = vz + 14
        cam = Camera(64, 30, vx, cam_z,
                     self.terrain.height(vx, cam_z) + 3.2, math.pi)
        w.entities = [self._billboard(cam_z - 2.0)]
        scr = Screen(64, 30, color=True)
        _entities(scr, w, cam, Env(0.25, 0.0))
        self.assertEqual(scr.stats(), 0)
        w.entities = [self._billboard(cam_z - 6.0)]
        scr = Screen(64, 30, color=True)
        _entities(scr, w, cam, Env(0.25, 0.0))
        self.assertGreater(scr.stats(), 0)


class TestWorldSim(unittest.TestCase):
    def _world(self):
        return World(3, None, terrain_size=SMALL)

    def test_deterministic_generation(self):
        a = self._world()
        b = self._world()
        self.assertEqual(len(a.entities), len(b.entities))
        for ea, eb in zip(a.entities, b.entities):
            self.assertEqual(ea.eid, eb.eid)
            self.assertEqual((ea.x, ea.z), (eb.x, eb.z))

    def test_spawns_present(self):
        w = World(3, None)
        kinds = [getattr(e, "kind", None) for e in w.entities]
        self.assertEqual(kinds.count("captain"), 1)
        self.assertEqual(kinds.count("wolf"), 6)
        self.assertEqual(kinds.count("skeleton"), 7)
        self.assertEqual(kinds.count("villager"), 5)
        self.assertEqual(kinds.count("chicken"), 4)
        self.assertEqual(kinds.count("wyvern"), 1)
        models = [e.model for e in w.entities]
        self.assertIn("castle", models)
        self.assertIn("shrine", models)

    def test_village_has_a_windmill(self):
        w = World(3, None)
        mills = [e for e in w.entities if e.model == "windmill"]
        self.assertEqual(len(mills), 1)
        mill = mills[0]
        self.assertTrue(mill.solid)
        self.assertGreaterEqual(mill.radius, 3.0)
        self.assertIn(mill.pose, {"blades%d" % i for i in range(8)})

    def test_full_quest_chain(self):
        w = self._world()
        self.assertEqual(w.quest, "none")
        self.assertEqual(w.npc_choice("quest_accept"), "close")
        self.assertEqual(w.quest, "active")
        captain = next(e for e in w.entities
                       if getattr(e, "kind", "") == "captain")
        p = w.player
        p.x = captain.x
        p.z = captain.z - 1.2
        p.yaw = 0.0
        captain.hp = 1
        captain.aggro_r = 0.0
        p.attack_t = 0.0
        p.attack_done = False
        env = Env(0.25, 0.0)
        for _ in range(24):
            w.update(1.0 / 30.0, env)
        self.assertIn(captain.eid, w.kills)
        amulet = next(e for e in w.entities
                      if getattr(e, "item_id", None) == "amulet")
        w.pickup_item(amulet)
        self.assertEqual(w.quest, "return")
        self.assertEqual(w.npc_choice("quest_complete"), "victory")
        self.assertEqual(w.quest, "done")
        self.assertGreaterEqual(w.player.inventory.count("gold"), 280)
        self.assertGreaterEqual(w.player.level, 2)

    def test_save_load_roundtrip(self):
        w = self._world()
        w.player.inventory.add("gold", 123)
        gold_total = w.player.inventory.count("gold")
        w.player.x += 3.0
        w.quest = "active"
        w.set_weather("rain")
        path = os.path.join(self.get_temp_dir(), "save.json")
        w.save(path)
        w2 = World.load(path, None, terrain_size=SMALL)
        self.assertEqual(w2.player.inventory.count("gold"), gold_total)
        self.assertAlmostEqual(w2.player.x, w.player.x, places=4)
        self.assertEqual(w2.quest, "active")
        self.assertEqual(w2.weather, "rain")
        self.assertEqual(len(w2.entities), len(w.entities))

    def test_weather_cycles_without_consuming_game_rng(self):
        w = self._world()
        w.set_weather("clear")
        w.weather_left = 0.0
        w.messages = []
        w.update(1.0 / 30.0, Env(0.25, 0.0))
        self.assertIn(w.weather, ("rain", "snow"))
        self.assertGreater(w.weather_left, 0.0)
        self.assertTrue(w.messages)
        first = w.weather
        w.weather_left = 0.0
        w.update(1.0 / 30.0, Env(0.25, 0.0))
        self.assertEqual(w.weather, "clear")
        self.assertNotEqual(first, w.weather)

    def test_location_plate_shows_weather(self):
        from aldervale.hud import draw_location
        w = self._world()
        w.set_weather("rain")
        scr = Screen(80, 24, color=True)
        draw_location(scr, w)
        self.assertIn("rain", "".join(scr.chars[1]))

    def get_temp_dir(self):
        d = tempfile.mkdtemp(prefix="aldervale_test_")
        self.addCleanup(lambda: _rmtree(d))
        return d

    def test_interact_and_shrine(self):
        w = self._world()
        p = w.player
        elder = next(e for e in w.entities
                     if getattr(e, "name", None) == "Elder Quill")
        p.x = elder.x + 0.8
        p.z = elder.z
        p.yaw = -math.pi / 2
        self.assertIs(w.interact_target(), elder)
        p.hp = 10
        shrine = next(e for e in w.entities if e.model == "shrine")
        p.x = shrine.x + 1.0
        p.z = shrine.z
        p.yaw = -math.pi / 2
        self.assertIs(w.interact_target(), shrine)
        self.assertTrue(w.shrine_pray())
        self.assertFalse(w.shrine_pray())
        self.assertGreater(p.hp, 10)

    def test_chest_loot(self):
        w = self._world()
        chest = next(e for e in w.entities if hasattr(e, "opened"))
        gold_before = w.player.inventory.count("gold")
        w.open_chest(chest)
        self.assertTrue(chest.opened)
        self.assertGreater(w.player.inventory.count("gold"), gold_before)
        self.assertEqual(chest.model, "chest_o")


def _rmtree(d):
    import shutil
    shutil.rmtree(d, ignore_errors=True)


class TestGameShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = Game(seed=3, width=80, height=40,
                        save_path=os.path.join(tempfile.gettempdir(),
                                               "av_test_save.json"))
        cls.game.term = None
        cls.game.atlas = _tiny_atlas()
        cls.game.world = World(3, cls.game.atlas)
        cls.game._open_screen()
        cls.game._ensure_camera()
        cls.game.state = "play"
        cls.game.dt = 1.0 / 30.0

    def _render_once(self):
        env = Env(self.game.world.day_t, self.game.world.time)
        self.game._render(env)
        return self.game.screen

    def test_movement_changes_position(self):
        g = self.game
        p = g.world.player
        z0 = p.z
        g.cam_yaw = math.pi
        g._movement(1.0, 0.0, False)
        g.world.update(1.0 / 30.0, Env(0.25, 0.0))
        self.assertLess(p.z, z0)
        self.assertTrue(p.moving)

    def test_attack_kills_wounded_wolf(self):
        g = self.game
        w = g.world
        p = w.player
        wolf = next(e for e in w.entities
                    if getattr(e, "kind", "") == "wolf")
        wolf.hp = 1
        wolf.aggro_r = 0.0
        wolf.state = "idle"
        p.x = wolf.x
        p.z = wolf.z - 1.0
        p.yaw = 0.0
        p.attack_t = -1.0
        g._try_attack()
        self.assertTrue(p.attacking)
        env = Env(0.25, 0.0)
        for _ in range(20):
            w.update(1.0 / 30.0, env)
        self.assertIn(wolf.eid, w.kills)

    def test_state_transitions(self):
        g = self.game
        g._key_play("i")
        self.assertEqual(g.state, "inventory")
        g._key_inventory("esc")
        self.assertEqual(g.state, "play")
        g._key_play("h")
        self.assertEqual(g.state, "help")
        g._key_help("x")
        self.assertEqual(g.state, "play")
        g._key_play("esc")
        self.assertEqual(g.state, "pause")
        g._key_pause("c")
        self.assertEqual(g.state, "play")

    def test_potion_use_heals(self):
        g = self.game
        p = g.world.player
        vx, vz = g.world.terrain.village
        p.x, p.z = vx, vz + 6
        p.ground_y = g.world.terrain.height(p.x, p.z)
        p.inventory.add("potion", 1)
        p.hp = 5
        p.heal_remaining = 0.0
        g._use_potion()
        self.assertEqual(p.inventory.count("potion"), 1)
        self.assertGreater(p.heal_remaining, 0.0)
        env = Env(0.25, 0.0)
        for _ in range(120):
            g.world.update(g.dt, env)
        self.assertAlmostEqual(p.hp, p.max_hp, places=2)

    def test_render_frame_smoke(self):
        scr = self._render_once()
        self.assertGreater(scr.stats(), 500)

    def test_save_and_load_via_game(self):
        g = self.game
        g.world.player.inventory.add("gold", 55)
        gold_total = g.world.player.inventory.count("gold")
        g.world.save(g.save_path)
        loaded = World.load(g.save_path, g.atlas)
        self.assertEqual(loaded.player.inventory.count("gold"), gold_total)
        os.remove(g.save_path)


class TestGfxRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = build_game(seed=7, width=132, height=60,
                              terrain_size=SMALL, atlas_keys=[], gfx=True,
                              gfx_size=(80, 45))

    def _frame(self, day_t=0.24):
        g = self.game
        _reset(g)
        vx, vz = g.world.terrain.village
        g.world.player.x, g.world.player.z = vx, vz + 6
        g.world.player.ground_y = g.world.terrain.height(vx, vz + 6)
        g.world.player.yaw = math.pi
        g.cam = None
        g._ensure_camera()
        g._render(Env(day_t, g.world.time))
        return g

    def test_pixel_render_writes_colour_depth_and_hud(self):
        g = self._frame()
        self.assertEqual((g.frame.w, g.frame.h), (80, 45))
        colours = set()
        for i in range(0, len(g.frame.data), 3):
            colours.add(bytes(g.frame.data[i:i + 3]))
            if len(colours) > 8:
                break
        self.assertGreater(len(colours), 8, "the frame is not blank")
        self.assertLess(g.frame.sample_depth(40, 40), 1e8)
        self.assertGreater(len(g.screen.depth), 40)
        self.assertTrue(any(ch != " " for row in g.screen.chars for ch in row),
                        "the HUD text is drawn over the pixel frame")
        self.assertIsNotNone(g.pick_world(66, 52))

    def test_night_is_darker_than_day(self):
        day = self._frame(0.24)
        day_sum = sum(day.frame.data)
        night = self._frame(0.80)
        night_sum = sum(night.frame.data)
        self.assertLess(night_sum, day_sum * 0.75)


class TestCliSubprocess(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "aldervale", *args],
            cwd=PROJECT, capture_output=True, text=True, timeout=120)

    def test_version(self):
        r = self._run("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ALDERVALE", r.stdout)

    def test_unknown_flag_is_misuse(self):
        r = self._run("--bogus")
        self.assertEqual(r.returncode, 2)

    def test_headless_demo(self):
        r = self._run("--demo", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("demo:", r.stdout)

    def test_screenshot_writes_frame(self):
        d = tempfile.mkdtemp(prefix="aldervale_shot_")
        self.addCleanup(lambda: _rmtree(d))
        path = os.path.join(d, "vista.txt")
        r = self._run("--screenshot", path)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertGreater(len(lines), 40)
        self.assertTrue(all(len(line) > 40 for line in lines[:5]))

    def test_autostart_requires_serve(self):
        r = self._run("--autostart")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--autostart needs --serve", r.stderr)

    def test_open_play_requires_serve(self):
        r = self._run("--open-play")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--open-play needs --serve", r.stderr)

    def test_open_play_conflicts_with_autostart(self):
        r = self._run("--serve", "--open-play", "--autostart")
        self.assertEqual(r.returncode, 1)
        self.assertIn("different targets", r.stderr)

    def test_serve_port_validation(self):
        r = self._run("--serve", "70000")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--serve PORT", r.stderr)

    def test_open_requires_serve(self):
        r = self._run("--open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--open needs --serve", r.stderr)

    def test_web_shot_requires_a_studio_page(self):
        d = tempfile.mkdtemp(prefix="aldervale_web_")
        self.addCleanup(lambda: _rmtree(d))
        r = self._run("--web-shot", os.path.join(d, "shot.png"),
                      "--web-dir", d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Studio page not found", r.stderr)


class FakeWebSession:
    def __init__(self):
        self.seq = 3
        self.inputs = []

    def snapshot(self):
        return {"status": "ready", "seq": self.seq, "w": 2, "h": 1,
                "frame": {"chars": ["AB"], "colors": [[1, 2]]},
                "state": "play", "weather": "clear", "day_t": 0.2,
                "player": {"x": 1.0, "z": 2.0, "hp": 46, "max_hp": 46,
                           "stamina": 100, "state": "idle"}}

    def state(self):
        data = self.snapshot()
        data.pop("frame", None)
        return data

    def set_input(self, pressed, held, mouse):
        self.inputs.append((pressed, held, mouse))


class FakeWebSession3D:
    def scene(self):
        return {"status": "ready", "seq": 1,
                "camera": {"x": 0, "y": 1, "z": 2, "yaw": 0,
                           "f": 100, "fy": 50, "w": 2, "h": 1,
                           "horizon": 0},
                "entities": [], "hud": {"chars": ["  "], "colors": [[0, 0]]},
                "state": "play", "weather": "clear",
                "player": {"hp": 46, "max_hp": 46, "stamina": 100}}

    def state(self):
        return {"status": "ready", "seq": 1, "state": "play",
                "render_mode": "webgl"}

    def world_bundle(self):
        return {"meta": {"w": 2, "water": 1.0},
                "heights": "", "colors": ""}

    def model_bundle(self):
        return {"meta": {}, "pos": "", "norm": "", "col": ""}


class TestLauncherHTTP(unittest.TestCase):
    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        from aldervale import launcher
        self.launcher = launcher
        self.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), launcher.Handler)
        self.server.daemon_threads = True
        self.server.spawn = lambda mode: (self.calls.append(mode) or
                                          (True, "spawned " + mode))
        self.server.last_spawn = 0.0
        self.server.last_mode = None
        self.server.launch_lock = threading.Lock()
        self.server.web_lock = threading.Lock()
        self.server.web_error = None
        self.server.web_building = False
        self.server.web_session = FakeWebSession()
        self.server.web_lock3d = threading.Lock()
        self.server.web_error3d = None
        self.server.web_building3d = False
        self.server.web_session3d = FakeWebSession3D()
        self._fake = self.server
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port

        def stop():
            self.server.shutdown()
            self.thread.join(5)
            self.server.server_close()
        self.addCleanup(stop)

    def _post(self, payload, token=None):
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Aldervale-Token"] = token
        req = urllib.request.Request(self.base + "/start",
                                     data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())

    def _post_api(self, payload, token=None):
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Aldervale-Token"] = token
        req = urllib.request.Request(self.base + "/api/input",
                                     data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())

    def test_play_page_frame_and_state(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/play", timeout=5) as r:
            page = r.read().decode()
        self.assertIn("<canvas", page)
        self.assertIn(self.launcher.TOKEN, page)
        self.assertIn("/api/frame", page)
        with urllib.request.urlopen(self.base + "/api/frame", timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["seq"], 3)
        with urllib.request.urlopen(self.base + "/api/state", timeout=5) as r:
            state = json.loads(r.read())
        self.assertEqual(state["player"]["x"], 1.0)
        self.assertNotIn("frame", state)

    def test_input_api_forwards_and_requires_token(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post_api({"held": ["w"]})
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()
        self._post_api({"pressed": ["space"], "held": ["w", "shift"],
                        "mouse": [["ldown", 4, 5, 1, 0]]},
                       self.launcher.TOKEN)
        pressed, held, mouse = self._fake.web_session.inputs[-1]
        self.assertEqual(pressed, ["space"])
        self.assertEqual(held, ["w", "shift"])
        self.assertEqual(mouse, [["ldown", 4, 5, 1, 0]])

    def test_frame_reports_loading_before_session(self):
        import urllib.request
        self._fake.web_session = None
        self._fake.web_building = True
        with urllib.request.urlopen(self.base + "/api/frame", timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["status"], "loading")

    def test_webgl_page_and_assets(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/play3d", timeout=5) as r:
            page = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("webgl2", page.lower())
        self.assertIn(self.launcher.TOKEN, page)
        with urllib.request.urlopen(self.base + "/api/scene3d",
                                    timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["status"], "ready")
        with urllib.request.urlopen(self.base + "/api/world3d",
                                    timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["status"], "ready")
        with urllib.request.urlopen(self.base + "/api/models3d",
                                    timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["status"], "ready")

    def test_page_and_token_protected_start(self):
        import urllib.error
        import urllib.request
        with urllib.request.urlopen(self.base + "/", timeout=5) as r:
            page = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("START GAME", page)
        self.assertIn(self.launcher.TOKEN, page)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post({"mode": "play"})
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()
        status, data = self._post({"mode": "demo"}, self.launcher.TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls, ["demo"])
        status, data = self._post({"mode": "play"}, self.launcher.TOKEN)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls, ["demo", "play"])
        self.assertTrue(self.launcher.check_health(self.port))

    def test_duplicate_start_is_coalesced(self):
        status, data = self._post({"mode": "play"}, self.launcher.TOKEN)
        self.assertTrue(data["ok"])
        status, data = self._post({"mode": "play"}, self.launcher.TOKEN)
        self.assertTrue(data["ok"])
        self.assertIn("already", data["message"].lower())
        self.assertEqual(self.calls, ["play"])

    def test_health_and_unknown_path(self):
        import urllib.error
        import urllib.request
        with urllib.request.urlopen(self.base + "/health", timeout=5) as r:
            self.assertEqual(r.read(), b"ok")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/nope", timeout=5)
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()


class TestCamera(unittest.TestCase):
    def test_default_camera_is_close_enough_for_model_detail(self):
        g = Game(seed=3, terrain_size=SMALL, width=132, height=60)
        self.assertLessEqual(g.cam_dist, 5.0)
        self.assertGreaterEqual(g.cam_dist, 4.0)
        self.assertGreaterEqual(g.cam_ease_d, 3.0)

    def test_camera_pulls_in_when_a_hill_blocks(self):
        from aldervale.render import clear_camera_distance

        class Ridge:
            def height(self, x, z):
                return 8.0 if -5.0 < z < -2.5 else 0.0

        clear = clear_camera_distance(Ridge(), 0.0, 0.0, 1.55, 0.0, 1.0,
                                      3.0, 4.6)
        self.assertLess(clear, 4.6)
        self.assertGreaterEqual(clear, 2.2)

    def test_camera_keeps_full_distance_on_flat_ground(self):
        from aldervale.render import clear_camera_distance

        class Flat:
            def height(self, x, z):
                return 0.0

        self.assertEqual(
            clear_camera_distance(Flat(), 0.0, 0.0, 1.55, 0.0, 1.0,
                                  3.0, 4.6), 4.6)


class TestInspection(unittest.TestCase):
    """The headless lens: PNG scenes, text mirrors and the control probe."""

    KEYS = ["knight", "wolf", "rock_s", "gold", "house1"]

    def test_inspection_writes_png_text_and_report(self):
        out = tempfile.mkdtemp(prefix="aldervale_inspect_")
        self.addCleanup(_rmtree, out)
        report = run_inspection(out, seed=3, width=64, height=30,
                                terrain_size=SMALL, scale=1,
                                scenes=["village", "rain"], probe=False,
                                atlas_keys=self.KEYS)
        self.assertEqual(len(report["scenes"]), 2)
        for name in ("02_village.png", "02_village.txt", "18_rain.png",
                     "18_rain.txt", "report.json", "index.html",
                     "studio-data.js"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        with open(os.path.join(out, "02_village.png"), "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(out, "report.json"), encoding="utf-8") as f:
            self.assertIn('"viewport"', f.read())

    def test_probe_controls_all_pass(self):
        game = build_game(seed=3, width=80, height=40,
                          terrain_size=SMALL, atlas_keys=self.KEYS)
        failed = [c["name"] for c in probe_controls(game) if not c["ok"]]
        self.assertEqual(failed, [])


class TestResponsiveMenus(unittest.TestCase):
    """Every menu panel must stay inside its own box at any viewport size."""

    WIDTHS = (40, 48, 64, 80, 132)

    def _screen(self, width, height=30):
        return Screen(width, height, color=True)

    @staticmethod
    def _find_box(scr):
        for y in range(scr.h):
            row = "".join(scr.chars[y])
            if "+" not in row or "-" not in row:
                continue
            left = row.index("+")
            right = row.rindex("+")
            if right - left < 6:
                continue
            bottom = y
            for yy in range(y + 1, scr.h):
                if scr.chars[yy][left] == "+" and scr.chars[yy][right] == "+":
                    bottom = yy
            return left, y, right, bottom
        return None

    def _assert_panel_contained(self, scr, label):
        box = self._find_box(scr)
        self.assertIsNotNone(box, "%s: no panel box drawn" % label)
        left, top, right, bottom = box
        self.assertGreaterEqual(left, 0, label)
        self.assertLess(right, scr.w, label)
        self.assertGreaterEqual(top, 0, label)
        self.assertLess(bottom, scr.h, label)
        for y in range(top + 1, bottom):
            self.assertEqual(scr.chars[y][left], "|",
                             "%s: left border broken at row %d" % (label, y))
            self.assertEqual(scr.chars[y][right], "|",
                             "%s: right border broken at row %d" % (label, y))
        for y in list(range(0, top)) + list(range(bottom + 1, scr.h)):
            self.assertEqual("".join(scr.chars[y]).strip(), "",
                             "%s: content outside the panel at row %d"
                             % (label, y))
        for y in range(top, bottom + 1):
            for x in list(range(0, left)) + list(range(right + 1, scr.w)):
                self.assertEqual(scr.chars[y][x], " ",
                                 "%s: glyph outside the panel at %d,%d"
                                 % (label, x, y))

    def test_help_fits_every_width(self):
        from aldervale import hud
        for width in self.WIDTHS:
            scr = self._screen(width)
            hud.draw_help(scr)
            self._assert_panel_contained(scr, "help@%d" % width)
            text = "\n".join("".join(row) for row in scr.chars)
            self.assertIn("pause", text, "help@%d lost a control line"
                          % width)

    def test_inventory_fits_every_width(self):
        from aldervale import hud
        w = World(3, None, terrain_size=SMALL)
        p = w.player
        for item_id in ("iron_sword", "leather_armor", "potion", "pelt"):
            p.inventory.add(item_id, 1)
        for width in self.WIDTHS:
            scr = self._screen(width)
            hud.draw_inventory(scr, w, "U use a potion   E equip the best")
            self._assert_panel_contained(scr, "inventory@%d" % width)
            text = "\n".join("".join(row) for row in scr.chars)
            self.assertIn("SATCHEL", text, "inventory@%d lost its title"
                          % width)
            self.assertIn("[I] or [ESC] close", text,
                          "inventory@%d lost its close hint" % width)

    def test_shop_fits_every_width(self):
        from aldervale import hud
        w = World(3, None, terrain_size=SMALL)
        for width in self.WIDTHS:
            scr = self._screen(width)
            hud.draw_shop(scr, w, "buy", 6, "Bram eyes your purse.")
            self._assert_panel_contained(scr, "shop@%d" % width)
            text = "\n".join("".join(row) for row in scr.chars)
            self.assertIn("Healing Draught", text,
                          "shop@%d cut the last ware" % width)

    def test_shop_sell_fits_every_width(self):
        from aldervale import hud
        for width in self.WIDTHS:
            w = World(3, None, terrain_size=SMALL)
            for item_id in ("pelt", "bone", "potion"):
                w.player.inventory.add(item_id, 2)
            scr = self._screen(width)
            hud.draw_shop(scr, w, "sell", 1, "Sold a pelt.")
            self._assert_panel_contained(scr, "sell@%d" % width)
            text = "\n".join("".join(row) for row in scr.chars)
            self.assertIn("Your goods", text, "sell@%d lost its header"
                          % width)

    def test_overlay_boxes_fit_every_width(self):
        from aldervale import hud
        w = World(3, None, terrain_size=SMALL)
        for width in self.WIDTHS:
            for name, draw in (
                    ("pause", lambda s: hud.draw_pause(s, 1)),
                    ("death", lambda s: hud.draw_death(s, w)),
                    ("victory", lambda s: hud.draw_victory(s, w, 2.0))):
                scr = self._screen(width)
                draw(scr)
                self._assert_panel_contained(scr, "%s@%d" % (name, width))

    def test_title_fits_every_width(self):
        from aldervale import hud
        from aldervale.render import Camera, Env
        for width in self.WIDTHS:
            scr = self._screen(width)
            w = World(3, None, terrain_size=SMALL)
            cam = Camera(width, scr.h, 0.0, 0.0, 5.0, 0.0)
            hud.draw_title(scr, w, cam, Env(0.25, 0.0), 0, True)
            rows = ["".join(row) for row in scr.chars]
            for i, row in enumerate(rows):
                if row.strip():
                    self.assertLessEqual(len(row.rstrip()), width,
                                         "title@%d overflows on row %d"
                                         % (width, i))
            text = "\n".join(rows)
            self.assertIn("WASD walk", text,
                          "title@%d lost its control footer" % width)
            self.assertIn("ALDERVALE v1.2", text,
                          "title@%d lost its version line" % width)


class TestReviewFixes(unittest.TestCase):
    """Regressions for defects found in the aldervale code review."""

    def _world(self):
        return World(3, None, terrain_size=SMALL)

    def test_gold_pickups_collected_same_frame(self):
        from aldervale.entities import Pickup
        w = self._world()
        p = w.player
        w._add_drop(Pickup("gold_a", "gold", 5, p.x, p.z, 0.22))
        w._add_drop(Pickup("gold_b", "gold", 7, p.x, p.z, 0.22))
        w.update(1.0 / 30.0, Env(0.25, 0.0))
        self.assertIn("gold_a", w.collected)
        self.assertIn("gold_b", w.collected)
        self.assertEqual(p.inventory.count("gold"), 30 + 5 + 7)

    def test_hud_bars_do_not_overlap(self):
        w = self._world()
        from aldervale import hud
        scr = Screen(110, 50, color=True)
        hud.draw_hud(scr, w, Env(0.25, 0.0), 60)
        row = "".join(scr.chars[scr.h - 4])
        p = w.player
        self.assertIn("%d/%d" % (p.hp, p.max_hp), row,
                      "HP readout overwritten by the stamina bar")
        hp = row.find("HP")
        stam = row.find("Stam")
        xp = row.find("XP")
        pot = row.find("Pot")
        self.assertLess(hp, stam)
        self.assertLess(stam, xp)
        self.assertLess(xp, pot)

    def test_hud_adapts_to_narrow_viewports(self):
        w = self._world()
        from aldervale import hud
        for width in (80, 64, 48):
            scr = Screen(width, 40, color=True)
            hud.draw_hud(scr, w, Env(0.25, 0.0), 60)
            rows = ["".join(row) for row in scr.chars]
            self.assertIn("HP", rows[36], "no HP bar at width %d" % width)
            if width >= 64:
                self.assertIn("Stam", rows[36], "no stamina at width %d"
                              % width)
                self.assertIn("Pot", rows[35], "no potion count at width %d"
                              % width)
                self.assertIn("Quest:", rows[37], "no quest line at width %d"
                              % width)
            else:
                self.assertIn("Stam", rows[37], "no stamina row at width %d"
                              % width)
                self.assertIn("Pot", rows[36], "no potion count at width %d"
                              % width)
                self.assertIn("Quest:", rows[38], "no quest line at width %d"
                              % width)

    def test_death_transitions_to_dead_state(self):
        from aldervale.entities import Actor
        w = self._world()
        game = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        game.term = None
        game.atlas = None
        game.world = w
        game._open_screen()
        game._ensure_camera()
        game.state = "play"
        p = w.player
        p.hp = 1
        attacker = Actor("att", "wolf", p.x, p.z + 1.0, 1.0, kind="wolf",
                         hp=10, atk=5, dfn=0, speed=1.0, xp_reward=0,
                         aggro_r=0.0, attack_range=1.0, attack_dmg=50,
                         name="Test Wolf")
        w.hit_player(50, attacker)
        self.assertTrue(p.dead)
        game._sync_death()
        self.assertEqual(game.state, "dead")
        game._key_dead("x")
        self.assertEqual(game.state, "play")
        self.assertEqual(p.hp, p.max_hp)


    def test_gate_guards_spawn_as_twins(self):
        w = World(3, None)
        guards = [e for e in w.entities if getattr(e, "ai_kind", "") == "guard"]
        self.assertEqual(len(guards), 2)
        self.assertEqual({g.name for g in guards},
                         {"Ser Aldous", "Ser Aldric"})
        for g in guards:
            payload = w.npc_talk(g)
            self.assertIn(payload["name"], ("Ser Aldous", "Ser Aldric"))
            self.assertTrue(payload["pages"])

    def test_npc_talk_delegates_to_story(self):
        from aldervale import story
        w = self._world()
        elder = next(e for e in w.entities
                     if getattr(e, "name", None) == "Elder Quill")
        self.assertEqual(w.npc_talk(elder),
                         story.dialogue_for("Elder Quill", w.quest))


class TestLaunchers(unittest.TestCase):
    """The one-click run buttons: PLAY.bat, run.sh and the VS Code config."""

    def test_play_bat_version_fastpath(self):
        if sys.platform != "win32":
            self.skipTest("PLAY.bat is Windows-only")
        r = subprocess.run(
            ["cmd", "/c", os.path.join(PROJECT, "PLAY.bat"), "--version"],
            cwd=PROJECT, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ALDERVALE", r.stdout)

    def test_web_launchers_are_one_click(self):
        for name, needles in (
                ("PLAY_WEB.bat", ("--serve", "--open-play")),
                ("play_web.sh", ("--serve", "--open-play"))):
            path = os.path.join(PROJECT, name)
            self.assertTrue(os.path.isfile(path), name)
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            for needle in needles:
                self.assertIn(needle, content, name)

    def test_web_launchers_detect_python_like_play_bat(self):
        with open(os.path.join(PROJECT, "PLAY_WEB.bat"),
                  encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.assertIn("py -3", content,
                      "PLAY_WEB.bat should fall back to the py launcher")
        self.assertIn("python -m aldervale", content)
        self.assertIn("https://www.python.org/downloads/", content,
                      "a missing Python needs the same friendly message as PLAY.bat")
        self.assertIn('"%~1"=="--version"', content,
                      "PLAY_WEB.bat needs the same --version fast path as PLAY.bat")

    def test_play_web_version_fastpath(self):
        if sys.platform != "win32":
            self.skipTest("PLAY_WEB.bat is Windows-only")
        r = subprocess.run(
            ["cmd", "/c", os.path.join(PROJECT, "PLAY_WEB.bat"), "--version"],
            cwd=PROJECT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ALDERVALE", r.stdout)

    def test_readme_lists_every_module_and_license_files(self):
        with open(os.path.join(PROJECT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        package = os.path.join(PROJECT, "aldervale")
        for name in sorted(os.listdir(package)):
            if name.endswith(".py"):
                self.assertIn(name, readme, "%s is missing from the README tree" % name)
        for name in ("COMMERCIAL.md", "LICENSE"):
            self.assertIn(name, readme, "%s is missing from the README" % name)
        self.assertIn("## 📜 License", readme, "the README needs the canonical License section")
        self.assertNotIn("Aegean-E/AIKit", readme,
                         "the badge must point at the current AIKit repository")

    def test_run_sh_targets_module(self):
        with open(os.path.join(PROJECT, "run.sh"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("python3 -m aldervale", content)
        self.assertIn("python -m aldervale", content)

    def test_play_bat_wt_directory_has_no_trailing_backslash(self):
        with open(os.path.join(PROJECT, "PLAY.bat"),
                  encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.assertNotIn('-d "%~dp0"', content,
                         "trailing backslash escapes the quote and wt "
                         "swallows the whole command line as -d")
        self.assertIn('-d "%CD%"', content)
        self.assertIn("-w -1 --maximized", content,
                      "the game should open a dedicated maximized window")

    def test_vscode_launch_configs(self):
        with open(os.path.join(PROJECT, ".vscode", "launch.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        names = [c["name"] for c in data["configurations"]]
        self.assertIn("ALDERVALE: Play", names)
        for cfg in data["configurations"]:
            self.assertEqual(cfg["module"], "aldervale")
            self.assertEqual(cfg["cwd"], "${workspaceFolder}")


class TestHeldControls(unittest.TestCase):
    """Movement must respond to held keys polled every frame."""

    @classmethod
    def setUpClass(cls):
        cls.game = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        cls.game.term = FakePollTerm()
        cls.game.atlas = _tiny_atlas()
        cls.game.world = World(3, cls.game.atlas, terrain_size=SMALL)
        cls.game._open_screen()
        cls.game._ensure_camera()
        cls.game.state = "play"
        cls.game.dt = 1.0 / 30.0

    def _tick(self, held, n=6):
        g = self.game
        g.term.held = set(held)
        g.world.player.attack_t = -1.0
        env = Env(g.world.day_t, 0.0)
        for _ in range(n):
            g._handle_keys()
            g.world.update(g.dt, env)

    def test_w_moves_player_forward(self):
        g = self.game
        p = g.world.player
        g.cam_yaw = math.pi
        z0 = p.z
        self._tick({"w"})
        self.assertLess(p.z, z0 - 0.4)

    def test_arrow_up_moves_and_left_turns(self):
        g = self.game
        p = g.world.player
        g.cam_yaw = math.pi
        z0 = p.z
        self._tick({"up"})
        self.assertLess(p.z, z0 - 0.4)
        yaw0 = g.cam_yaw
        self._tick({"left"})
        self.assertLess(g.cam_yaw, yaw0)

    def test_a_d_strafe(self):
        g = self.game
        p = g.world.player
        g.cam_yaw = math.pi
        x0 = p.x
        self._tick({"a"})
        self.assertGreater(p.x, x0 + 0.3)
        x1 = p.x
        self._tick({"d"})
        self.assertLess(p.x, x1 - 0.3)

    def test_shift_sprints(self):
        g = self.game
        p = g.world.player
        g.cam_yaw = math.pi
        z0 = p.z
        self._tick({"w"}, n=10)
        walk = z0 - p.z
        p.stamina = 100.0
        z1 = p.z
        self._tick({"w", "shift"}, n=10)
        sprint = z1 - p.z
        self.assertGreater(sprint, walk * 1.2)

    def test_space_press_attacks(self):
        g = self.game
        p = g.world.player
        p.attack_t = -1.0
        p.stamina = 100.0
        g.term.queue_press(["space"])
        g._handle_keys()
        self.assertTrue(p.attacking)

    def test_hold_b_guards_and_release_drops_it(self):
        g = self.game
        p = g.world.player
        p.attack_t = -1.0
        p.stamina = 100.0
        self._tick({"b"}, n=1)
        self.assertTrue(p.guarding)
        self._tick(set(), n=1)
        self.assertFalse(p.guarding)

    def test_guard_blocks_damage_through_held_key(self):
        from aldervale.entities import Actor
        g = self.game
        p = g.world.player
        p.hp = 100
        p.max_hp = 100
        p.attack_t = -1.0
        p.stamina = 100.0
        self._tick({"b"}, n=1)
        foe = Actor("guarded", "wolf", p.x + 1.0, p.z, 1.0, kind="wolf",
                    hp=5, atk=5, dfn=0, speed=1.0, xp_reward=0, aggro_r=0.0,
                    attack_range=1.0, attack_dmg=20, name="Test")
        g.world.hit_player(20, foe)
        self.assertLess(100 - p.hp, 12)
        self.assertLess(p.stamina, 100.0)


class FakePollTerm:
    def __init__(self):
        self.held = set()
        self._presses = []
        self._mouse = []
        self.out = []
        self.flushes = 0

    def queue_press(self, keys):
        self._presses = list(keys)

    def queue_mouse(self, events):
        self._mouse.extend(events)

    def poll(self):
        pressed = self._presses
        self._presses = []
        return pressed, set(self.held)

    def take_mouse(self):
        events = self._mouse
        self._mouse = []
        return events

    def write(self, text):
        self.out.append(text)

    def flush(self):
        self.flushes += 1

    def size(self):
        return (80, 40)


class TestMouse(unittest.TestCase):
    """Mouse orbit, zoom, pick, walk-to and click-to-attack."""

    def _game(self):
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "play"
        g.dt = 1.0 / 30.0
        g._render(Env(g.world.day_t, 0.0))
        return g

    def test_mouse_release_before_press_is_safe(self):
        g = self._game()
        g.term.queue_mouse([("move", 10, 10, 0, 0),
                            ("up", 10, 10, 0, 0)])
        g._handle_keys()
        self.assertIsNone(g.walk_target)

    def test_right_drag_orbits_and_tilts(self):
        g = self._game()
        yaw0 = g.cam_yaw
        pitch0 = g.cam_pitch
        g.term.queue_mouse([("rdown", 40, 20, 0, 0),
                            ("move", 48, 24, 2, 0)])
        g._handle_keys()
        self.assertGreater(g.cam_yaw, yaw0 + 0.2)
        self.assertGreater(g.cam_pitch, pitch0)

    def test_wheel_zooms(self):
        g = self._game()
        d0 = g.cam_dist
        g.term.queue_mouse([("wheel", 40, 20, 0, 1)])
        g._handle_keys()
        self.assertLess(g.cam_dist, d0)
        g.term.queue_mouse([("wheel", 40, 20, 0, -1)])
        g._handle_keys()
        self.assertAlmostEqual(g.cam_dist, d0, places=5)

    def test_pick_rejects_sky(self):
        g = self._game()
        self.assertIsNone(g.pick_world(40, 0))

    def test_click_sets_walk_target(self):
        g = self._game()
        target = None
        for row in range(5, g.h - 6):
            for col in range(5, g.w - 5):
                if g.pick_world(col, row) is not None:
                    target = (col, row)
                    break
            if target:
                break
        self.assertIsNotNone(target, "no pickable ground cell found")
        g.term.queue_mouse([("ldown", target[0], target[1], 1, 0),
                            ("up", target[0], target[1], 0, 0)])
        g._handle_keys()
        self.assertIsNotNone(g.walk_target)

    def test_click_drag_does_not_walk(self):
        g = self._game()
        target = None
        for row in range(5, g.h - 6):
            for col in range(5, g.w - 5):
                if g.pick_world(col, row) is not None:
                    target = (col, row)
                    break
            if target:
                break
        self.assertIsNotNone(target)
        g.term.queue_mouse([("ldown", target[0], target[1], 1, 0),
                            ("move", target[0] + 6, target[1] + 3, 1, 0),
                            ("up", target[0] + 6, target[1] + 3, 0, 0)])
        g._handle_keys()
        self.assertIsNone(g.walk_target)

    def test_walk_target_carries_player(self):
        g = self._game()
        p = g.world.player
        g.cam_yaw = math.pi
        p.x, p.z = 36.0, 50.0
        p.ground_y = g.world.terrain.height(p.x, p.z)
        g.walk_target = (36.0, 44.0)
        z0 = p.z
        env = Env(g.world.day_t, 0.0)
        for _ in range(20):
            g._handle_keys()
            g.world.update(g.dt, env)
        self.assertLess(p.z, z0 - 0.5)

    def test_click_near_enemy_attacks(self):
        g = self._game()
        p = g.world.player
        foe = next(e for e in g.world.entities
                   if getattr(e, "kind", "") in ("skeleton", "bandit",
                                                 "captain"))
        foe.x, foe.z = p.x, p.z + 1.4
        p.attack_t = -1.0
        p.stamina = 100.0
        g.pick_world = lambda col, row: (foe.x, foe.z)
        g._click_at(10, 10)
        self.assertTrue(p.attacking)


class TestTitleFlow(unittest.TestCase):
    """Starting a new game from the title screen through the poll path."""

    def test_new_game_starts_from_title(self):
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "title"
        g.term.queue_press(["n"])
        g._handle_keys()
        self.assertEqual(g.state, "play")
        self.assertIsNotNone(g.world.player)

    def test_continue_without_save_starts_world(self):
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40,
                 save_path=os.path.join(tempfile.gettempdir(),
                                        "av_no_such_save.json"))
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "title"
        g.term.queue_press(["c"])
        g._handle_keys()
        self.assertEqual(g.state, "play")

    def test_mouse_click_on_new_game_starts_world(self):
        from aldervale import hud
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "title"
        row = hud.title_menu_top(g.screen)
        g.term.queue_mouse([("ldown", 40, row, 1, 0),
                            ("up", 40, row, 0, 0)])
        g._handle_keys()
        self.assertEqual(g.state, "play")
        self.assertEqual(g.menu_sel, 0)

    def test_title_arrows_and_enter_choose_continue(self):
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40,
                 save_path=os.path.join(tempfile.gettempdir(),
                                        "av_no_such_save.json"))
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "title"
        g.term.queue_press(["down"])
        g._handle_keys()
        self.assertEqual(g.menu_sel, 1)
        g.term.queue_press(["enter"])
        g._handle_keys()
        self.assertEqual(g.state, "play")

    def test_mouse_click_on_help_opens_help(self):
        from aldervale import hud
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        g.term = FakePollTerm()
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "title"
        row = hud.title_menu_top(g.screen) + 2
        g.term.queue_mouse([("ldown", 40, row, 1, 0),
                            ("up", 40, row, 0, 0)])
        g._handle_keys()
        self.assertEqual(g.state, "help")
        self.assertEqual(g.help_from, "title")


class TestMechanics(unittest.TestCase):
    """Combat simulation mechanics: guard, facing, backstab, potions, respawn."""

    def _world(self):
        return World(3, None, terrain_size=SMALL)

    def test_returning_enemy_does_not_instant_heal(self):
        w = self._world()
        skel = next(e for e in w.entities
                    if getattr(e, "kind", "") == "skeleton")
        skel.hp = 5
        skel.state = "return"
        env = Env(0.25, 0.0)
        for _ in range(30):
            w.update(1.0 / 30.0, env)
        self.assertLessEqual(skel.hp, 6)

    def test_guard_reduces_damage_and_costs_stamina(self):
        from aldervale.entities import Actor
        w = self._world()
        p = w.player
        p.hp = 100
        p.max_hp = 100
        p.guarding = True
        p.stamina = 100.0
        attacker = Actor("att", "wolf", p.x + 1.0, p.z, 1.0, kind="wolf",
                         hp=5, atk=5, dfn=0, speed=1.0, xp_reward=0,
                         aggro_r=0.0, attack_range=1.0, attack_dmg=20,
                         name="Test")
        w.hit_player(20, attacker)
        guarded = 100 - p.hp
        w2 = self._world()
        p2 = w2.player
        p2.hp = 100
        p2.max_hp = 100
        p2.guarding = False
        w2.hit_player(20, attacker)
        open_loss = 100 - p2.hp
        self.assertLess(guarded, open_loss * 0.6)
        self.assertAlmostEqual(p.stamina, 90.0)

    def test_guard_needs_stamina(self):
        from aldervale.entities import Actor
        w = self._world()
        p = w.player
        p.hp = 100
        p.max_hp = 100
        p.guarding = True
        p.stamina = 5.0
        attacker = Actor("att", "wolf", p.x + 1.0, p.z, 1.0, kind="wolf",
                         hp=5, atk=5, dfn=0, speed=1.0, xp_reward=0,
                         aggro_r=0.0, attack_range=1.0, attack_dmg=20,
                         name="Test")
        w.hit_player(20, attacker)
        self.assertGreater(100 - p.hp, 8)

    def test_enemy_strike_requires_facing(self):
        w = self._world()
        p = w.player
        p.hp = 100
        p.max_hp = 100
        skel = next(e for e in w.entities
                    if getattr(e, "kind", "") == "skeleton")
        skel.hp = 999999
        skel.x, skel.z = p.x, p.z + 1.2
        skel.state = "windup"
        skel.windup_t = skel.windup_s - 0.01
        skel.yaw = math.pi
        env = Env(0.25, 0.0)
        w.update(1.0 / 30.0, env)
        self.assertLess(p.hp, 100)
        p.hp = 100
        skel.hp = 999999
        skel.x, skel.z = p.x, p.z + 1.2
        skel.state = "windup"
        skel.windup_t = skel.windup_s - 0.01
        skel.yaw = 0.0
        w.update(1.0 / 30.0, env)
        self.assertEqual(p.hp, 100)

    def test_backstab_deals_bonus(self):
        w = self._world()
        p = w.player
        foe = next(e for e in w.entities
                   if getattr(e, "kind", "") == "skeleton")
        foe.x, foe.z = p.x, p.z + 1.2
        foe.yaw = 0.0
        foe.hp = 500
        p.yaw = 0.0
        w.resolve_player_swing()
        back = 500 - foe.hp
        w2 = self._world()
        p2 = w2.player
        foe2 = next(e for e in w2.entities
                    if getattr(e, "kind", "") == "skeleton")
        foe2.x, foe2.z = p2.x, p2.z + 1.2
        foe2.yaw = math.pi
        foe2.hp = 500
        p2.yaw = 0.0
        w2.resolve_player_swing()
        front = 500 - foe2.hp
        self.assertGreater(back, front)

    def test_potion_heals_over_time(self):
        g = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        g.term = None
        g.atlas = _tiny_atlas()
        g.world = World(3, g.atlas, terrain_size=SMALL)
        g._open_screen()
        g._ensure_camera()
        g.state = "play"
        g.dt = 1.0 / 30.0
        p = g.world.player
        p.inventory.add("potion", 1)
        p.hp = 5
        g._use_potion()
        self.assertEqual(p.inventory.count("potion"), 1)
        self.assertAlmostEqual(p.hp, 5.0)
        env = Env(0.25, 0.0)
        for _ in range(30):
            g.world.update(1.0 / 30.0, env)
        self.assertGreater(p.hp, 10)
        self.assertLess(p.hp, p.max_hp + 0.01)
        for _ in range(90):
            g.world.update(1.0 / 30.0, env)
        self.assertAlmostEqual(p.hp, p.max_hp, places=2)

    def test_sell_menu_ignores_currency(self):
        w = self._world()
        ids = [iid for iid, _n in w.sellables()]
        self.assertNotIn("gold", ids)
        self.assertIn("potion", ids)
        self.assertFalse(w.sell("gold"))
        self.assertTrue(w.sell("potion"))
        self.assertFalse(w.sell("amulet"))
        self.assertFalse(w.sell("not_an_item"))

    def test_killed_enemy_respawns_far_away(self):
        w = self._world()
        skel = next(e for e in w.entities
                    if getattr(e, "kind", "") == "skeleton")
        living_before = len([e for e in w.entities
                             if getattr(e, "kind", "") == "skeleton"
                             and not getattr(e, "dead", False)])
        w.kill_actor(skel)
        self.assertTrue(any(r["kind"] == "skeleton" for r in w.respawn))
        w.respawn[-1]["t"] = 0.1
        p = w.player
        p.x, p.z = 4.0, 4.0
        env = Env(0.25, 0.0)
        w.update(0.2, env)
        living_after = len([e for e in w.entities
                            if getattr(e, "kind", "") == "skeleton"
                            and not getattr(e, "dead", False)])
        self.assertEqual(living_after, living_before)


class TestSharedSimulationStep(unittest.TestCase):
    """The browser session must step the world exactly like the terminal loop."""

    def _game(self):
        game = Game(seed=3, terrain_size=SMALL, width=80, height=40)
        game.world = World(3, None, terrain_size=SMALL)
        game.screen = Screen(80, 40, color=True)
        game.term = None
        game.state = "play"
        return game

    def test_a_menu_freezes_the_world(self):
        game = self._game()
        game.state = "inventory"
        before = game.world.time
        game.tick(0.1)
        self.assertEqual(game.world.time, before,
                         "menus must pause the simulation, as in the terminal loop")
        game.state = "play"
        game.tick(0.1)
        self.assertGreater(game.world.time, before)

    def test_a_fallen_hero_enters_the_death_state(self):
        game = self._game()
        game.world.player.state = "dead"
        game.tick(0.05)
        self.assertEqual(game.state, "dead",
                         "the browser needs the death screen to offer respawn")

    def test_victory_arms_once_and_then_counts_up(self):
        game = self._game()
        game.world.quest = "done"
        game.tick(0.05)
        self.assertTrue(game.world.victory_shown)
        first = game.victory_t
        self.assertGreater(first, 0.0)
        game.world.quest = "done"
        game.tick(0.05)
        self.assertGreater(game.victory_t, first,
                           "the overlay clock keeps moving after it is armed")

    def test_the_web_session_steps_through_the_shared_tick(self):
        import threading
        from types import SimpleNamespace

        calls = {}

        class FakeScreen:
            chars = [list("AB"), list("  ")]
            fg = [[0x111111, 0x222222], [0, 0]]

        def tick(dt):
            calls["tick"] = dt
            return "env"

        game = SimpleNamespace(
            _handle_keys=lambda: calls.__setitem__("keys", True),
            tick=tick,
            _render=lambda env: calls.__setitem__("render", env),
            screen=FakeScreen(),
        )
        session = object.__new__(WebGame)
        session.game = game
        session.lock = threading.RLock()
        session.seq = 0
        session.frame = None
        session.step()
        self.assertTrue(calls.get("keys"), "input is handled first")
        self.assertEqual(calls.get("tick"), 1.0 / 20.0)
        self.assertEqual(calls.get("render"), "env")
        self.assertEqual(session.seq, 1)
        self.assertEqual(session.frame["chars"], ["AB", "  "])


if __name__ == "__main__":
    unittest.main()
