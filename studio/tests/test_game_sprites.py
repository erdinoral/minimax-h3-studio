import json
import math
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from lib import game_sprites as gs

KEY = (40, 200, 70)
SIZE = 256
SKIN = (230, 180, 150)
SHIRT = (150, 90, 60)
BELT = (40, 110, 40)      # dark green: resembles the screen, must stay
EMBLEM = (70, 170, 70)    # closer still, enclosed by the shirt, must stay
SLEEVE = (170, 40, 40)
LEGS = (40, 40, 120)
SWORD = (190, 190, 200)


def backdrop(seed=0):
    rng = np.random.default_rng(seed)
    shade = np.linspace(-12, 12, SIZE)[:, None, None]
    img = np.array(KEY, np.float32) + shade + rng.integers(-4, 5, (SIZE, SIZE, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


def character(img, dx=0, dy=0, legs=(0, 0), fringe=None):
    """Side-view stand-in: arm loop around a screen pocket, thin sword, belt and emblem in key-like greens."""
    def box(y0, y1, x0, x1, color):
        img[max(0, y0 + dy):max(0, y1 + dy), max(0, x0 + dx):max(0, x1 + dx)] = color

    box(60, 90, 113, 143, SKIN)
    box(90, 150, 108, 148, SHIRT)
    box(140, 147, 108, 148, BELT)
    box(100, 112, 122, 134, EMBLEM)
    box(95, 135, 148, 173, SLEEVE)
    box(102, 128, 148, 166, KEY)          # pocket: screen seen through the arm loop
    box(150, 230, 110 + legs[0], 124 + legs[0], LEGS)
    box(150, 230, 132 + legs[1], 146 + legs[1], LEGS)
    box(40, 96, 168, 171, SWORD)
    if fringe is not None:
        mix = (fringe * np.array(KEY) + (1 - fringe) * np.array(SHIRT)).astype(np.uint8)
        box(90, 140, 107, 108, mix)
    return img


def frame(**kw):
    return character(backdrop(kw.pop("seed", 0)), **kw)


def opaque_bbox(cell):
    ys, xs = np.nonzero(cell[..., 3])
    return xs.min(), ys.min(), xs.max(), ys.max()


def process(clips, animation, tmp, source_fps=24, **settings):
    s = gs.settings_for(animation, settings)
    return gs.process(gs.ArrayFrames(clips, source_fps), animation, "green", s, Path(tmp), {"job_id": "test"})


class MaskTest(unittest.TestCase):
    def setUp(self):
        self.img = frame()
        self.key, _ = gs.estimate_key([self.img], "green")
        self.dist = gs.key_distance(self.img, self.key)

    def mask(self, **kw):
        return gs.mask_frame(self.dist, gs.settings_for("idle", kw))

    def test_screen_removed_including_enclosed_pocket(self):
        fg = self.mask()
        self.assertFalse(fg[5, 5] or fg[250, 250] or fg[200, 128], "edge and between-legs screen")
        self.assertFalse(fg[115, 157], "enclosed arm pocket")
        for name, (y, x) in {"skin": (75, 128), "shirt": (120, 115), "belt": (143, 128),
                             "emblem": (106, 128), "sleeve": (98, 160), "legs": (200, 117)}.items():
            self.assertTrue(fg[y, x], name)
        self.assertGreater(fg[40:96, 168:171].mean(), 0.95, "thin sword survives")

    def test_hole_tolerance_zero_keeps_pocket(self):
        self.assertTrue(self.mask(hole_tolerance=0)[115, 157])

    def test_high_tolerance_eats_key_like_character_colour(self):
        # Why the UI offers a mask preview: too much tolerance floods the edge-touching belt.
        self.assertTrue(self.mask(tolerance=30)[143, 109])
        self.assertFalse(self.mask(tolerance=60)[143, 109])

    def test_fringe_cleanup(self):
        img = frame(fringe=0.6)
        dist = gs.key_distance(img, self.key)
        fringe = (slice(90, 140), 107)
        self.assertTrue(gs.mask_frame(dist, gs.settings_for("idle", {"edge_clean": 0}))[fringe].all())
        self.assertFalse(gs.mask_frame(dist, gs.settings_for("idle", {"edge_clean": 1}))[fringe].any())
        half = frame(fringe=0.5)
        dist = gs.key_distance(half, self.key)
        s = gs.settings_for("idle", {})
        fg = gs.mask_frame(dist, s)
        colors = gs.clean_colors(half, fg, self.key, dist, s)
        edge = colors[90:140, 107].astype(int)
        self.assertTrue(fg[90:140, 107].all())
        self.assertTrue((edge[:, 1] <= np.maximum(edge[:, 0], edge[:, 2])).all(), "green spill removed")

    def test_background_pixels_never_lend_screen_colour(self):
        s = gs.settings_for("idle", {})
        fg = gs.mask_frame(self.dist, s)
        colors = gs.clean_colors(self.img, fg, self.key, self.dist, s)
        self.assertNotEqual(tuple(colors[5, 5]), tuple(self.img[5, 5]))
        fg_colors = set(map(tuple, colors[fg].tolist()))
        self.assertTrue(set(map(tuple, colors[~fg].tolist())) <= fg_colors)

    def test_stabilize_votes_only_borderline_pixels(self):
        a = np.zeros((4, 4), bool)
        b = a.copy(); b[1, 1] = b[2, 2] = True
        dists = [np.full((4, 4), 100.0)] * 3
        dists[1] = dists[1].copy(); dists[1][1, 1] = gs._threshold(30)
        out = gs.stabilize([a, b, a], dists, 1, 30)
        self.assertFalse(out[1, 1])
        self.assertTrue(out[2, 2])


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_jump_keeps_vertical_motion_with_one_scale(self):
        frames = [frame(dy=-int(round(30 * math.sin(math.pi * t / 23)))) for t in range(24)]
        r = process(frames, "jump", self.tmp, frames=12)
        self.assertTrue(r["ok"], r["issues"])
        cells = [np.asarray(Image.open(Path(self.tmp) / f)) for f in r["files"]["frames"]]
        boxes = [opaque_bbox(c) for c in cells]
        heights = {b[3] - b[1] for b in boxes}
        widths = {b[2] - b[0] for b in boxes}
        self.assertLessEqual(max(heights) - min(heights), 1, "shared scale")
        self.assertLessEqual(max(widths) - min(widths), 1)
        bottoms = [b[3] for b in boxes]
        self.assertEqual(bottoms[0], 61, "feet on the cell floor above the 2px margin")
        rise = bottoms[0] - min(bottoms)
        scale = 60 / (230 - 40 + 30)
        self.assertAlmostEqual(rise, 30 * scale * math.sin(math.pi * 11.5 / 23), delta=1.6)
        self.assertEqual(r["pivot"]["y"], 62)

    def test_locked_pivot_pins_feet_and_torso(self):
        frames = [frame(dx=t // 4, dy=-3 * (t % 2), legs=(t % 4 - 2, 2 - t % 4)) for t in range(36)]
        r = process(frames, "walk", self.tmp)
        self.assertTrue(r["ok"], r["issues"])
        cells = [np.asarray(Image.open(Path(self.tmp) / f)) for f in r["files"]["frames"]]
        self.assertEqual({opaque_bbox(c)[3] for c in cells}, {61})
        heads = {int(np.nonzero(c[opaque_bbox(c)[1] + 2, :, 3])[0].mean()) for c in cells}
        self.assertLessEqual(max(heads) - min(heads), 1)
        doc = json.loads((Path(self.tmp) / "walk.json").read_text())
        self.assertEqual(doc["animations"][0]["pivot"], r["pivot"])
        self.assertEqual(doc["animations"][0]["pivot_mode"], "locked")
        self.assertTrue(doc["animations"][0]["loop"])

    def test_transparency_is_hard_and_corners_clear(self):
        r = process([frame() for _ in range(8)], "idle", self.tmp, frames=4)
        for f in r["files"]["frames"]:
            img = Image.open(Path(self.tmp) / f)
            self.assertEqual(img.mode, "RGBA")
            a = np.asarray(img)[..., 3]
            self.assertEqual(set(np.unique(a).tolist()) - {0, 255}, set())
            self.assertEqual(int(a[0, 0]) + int(a[0, -1]) + int(a[-1, 0]) + int(a[-1, -1]), 0)
            rgb = np.asarray(img)[..., :3][a > 0].astype(int)
            screen = (rgb[:, 1] > rgb[:, 0] + 60) & (rgb[:, 1] > rgb[:, 2] + 60) & (rgb[:, 1] > 180)
            self.assertFalse(screen.any(), "no screen-green pixels left")

    def test_json_matches_sheet_and_zip(self):
        r = process([frame(dy=-(t % 3)) for t in range(30)], "jump", self.tmp, frames=11, cell=32, fps=15)
        out = Path(self.tmp)
        doc = json.loads((out / r["files"]["json"]).read_text())
        sheet = np.asarray(Image.open(out / doc["image"]))
        self.assertEqual((doc["image_size"]["w"], doc["image_size"]["h"]), (sheet.shape[1], sheet.shape[0]))
        self.assertEqual(doc["layout"], {"columns": 8, "rows": 2, "order": "row-major"})
        self.assertEqual(sheet.shape[:2], (64, 256))
        anim = doc["animations"][0]
        self.assertEqual(len(anim["frames"]), 11)
        self.assertEqual(anim["fps"], 15)
        self.assertAlmostEqual(anim["frame_duration_ms"], 1000 / 15, places=2)
        self.assertFalse(anim["loop"])
        for meta in anim["frames"]:
            crop = sheet[meta["y"]:meta["y"] + meta["h"], meta["x"]:meta["x"] + meta["w"]]
            np.testing.assert_array_equal(crop, np.asarray(Image.open(out / meta["file"])))
        self.assertFalse(sheet[32:, 3 * 32:].any(), "unused cells stay transparent")
        with zipfile.ZipFile(out / r["files"]["zip"]) as z:
            names = set(z.namelist())
        self.assertTrue({doc["image"], r["files"]["json"], "README.txt", *r["files"]["frames"]} <= names)

    def test_empty_mask_is_not_success(self):
        r = process([backdrop(i) for i in range(8)], "idle", self.tmp, frames=4)
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "failed")
        self.assertIn("emptyMask", [i["code"] for i in r["issues"]])
        self.assertFalse(list(Path(self.tmp).glob("*_sheet.png")))
        self.assertTrue((Path(self.tmp) / "mask_preview.png").is_file())

    def test_missing_screen_is_not_success(self):
        gray = [character(np.full((SIZE, SIZE, 3), 128, np.uint8)) for _ in range(6)]
        r = process(gray, "idle", self.tmp, frames=3)
        self.assertFalse(r["ok"])
        self.assertIn("noBackdrop", [i["code"] for i in r["issues"]])

    def test_shared_palette_limit(self):
        frames = []
        for t in range(8):
            img = frame()
            img[90:140, 108:148] = np.linspace(60, 220, 40, dtype=np.uint8)[None, :, None] * np.array([1, 0.6, 0.4])
            frames.append(img)
        r = process(frames, "idle", self.tmp, frames=4, palette=8)
        self.assertTrue(r["ok"], r["issues"])
        used = set()
        for f in r["files"]["frames"]:
            a = np.asarray(Image.open(Path(self.tmp) / f))
            used |= set(map(tuple, a[..., :3][a[..., 3] > 0].tolist()))
        self.assertLessEqual(len(used), 8)
        doc = json.loads((Path(self.tmp) / r["files"]["json"]).read_text())
        self.assertEqual(set(doc["palette"]), {"#%02x%02x%02x" % c for c in used})

    def test_loop_window_finds_one_cycle(self):
        frames = []
        for t in range(48):
            swing = int(round(6 * math.sin(2 * math.pi * t / 16)))
            frames.append(frame(legs=(swing, -swing), seed=t))
        r = process(frames, "walk", self.tmp)
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["window"]["end"] - r["window"]["start"], 16)
        self.assertEqual(r["seam"]["grade"], "good")
        self.assertEqual(r["natural_fps"], 12.0)

    def test_atlas_rows_match_json(self):
        a = Path(self.tmp) / "a"
        b = Path(self.tmp) / "b"
        ra = process([frame() for _ in range(8)], "idle", a, frames=4)
        rb = process([frame(dy=-(t % 4) * 5) for t in range(16)], "jump", b, frames=6)
        out = Path(self.tmp) / "atlas"
        info = gs.build_atlas([(a, ra), (b, rb)], out)
        doc = json.loads((out / info["json"]).read_text())
        sheet = np.asarray(Image.open(out / doc["image"]))
        self.assertEqual(sheet.shape[:2], (128, 6 * 64))
        self.assertEqual([x["name"] for x in doc["animations"]], ["idle", "jump"])
        for row, anim in enumerate(doc["animations"]):
            for meta in anim["frames"]:
                self.assertEqual(meta["y"], row * 64)
                crop = sheet[meta["y"]:meta["y"] + 64, meta["x"]:meta["x"] + 64]
                np.testing.assert_array_equal(crop, np.asarray(Image.open(out / meta["file"])))

    def test_preview_reports_coverage(self):
        r = gs.preview(gs.ArrayFrames([frame() for _ in range(6)]), "idle", "green",
                       gs.settings_for("idle", {}), Path(self.tmp) / "p.png")
        self.assertEqual(r["status"], "ok")
        self.assertTrue((Path(self.tmp) / "p.png").is_file())
        self.assertTrue(all(0.05 < c < 0.4 for c in r["coverage"]))


class SettingsTest(unittest.TestCase):
    def test_defaults_and_validation(self):
        s = gs.settings_for("walk")
        self.assertEqual((s.cell, s.frames, s.fps), (64, 8, 10.0))
        for bad in ({"cell": 48}, {"palette": 12}, {"frames": 1}, {"fps": 0}, {"tolerance": 0},
                    {"detail": "x"}, {"loop_start": 2, "loop_end": 1}, {"frames": "many"}):
            with self.assertRaises(gs.SpriteError):
                gs.settings_for("walk", bad)
        with self.assertRaises(gs.SpriteError):
            gs.settings_for("moonwalk")

    def test_prompt_rules(self):
        walk = gs.build_prompt("walk", "a knight with a red cape")
        for part in ("<Picture 1>", "full profile facing right", "in place", "never travels",
                     "no zoom", "no cuts", "no motion blur", "no cast shadow", "fully inside the frame",
                     "held objects", "repeating cycle", "a knight with a red cape"):
            self.assertIn(part, walk)
        self.assertIn("happens once", gs.build_prompt("jump"))

    def test_backdrop_suggestion_avoids_character_colours(self):
        green = np.full((64, 64, 3), 255, np.uint8)
        green[16:48, 16:48] = (30, 180, 40)
        self.assertEqual(gs.suggest_backdrop(green)["suggested"], "blue")
        red = np.full((64, 64, 3), 255, np.uint8)
        red[16:48, 16:48] = (200, 30, 30)
        self.assertEqual(gs.suggest_backdrop(red)["suggested"], "green")
        both = np.full((64, 64, 3), 255, np.uint8)
        both[16:48, 16:32] = (30, 180, 40)
        both[16:48, 32:48] = (30, 60, 200)
        self.assertTrue(gs.suggest_backdrop(both)["conflict"])

    def test_sheet_layout(self):
        lay = gs.sheet_layout(10, 64)
        self.assertEqual((lay["columns"], lay["rows"], lay["width"], lay["height"]), (8, 2, 512, 128))
        self.assertEqual(lay["rects"][9], {"x": 64, "y": 64, "w": 64, "h": 64})


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg missing")
class VideoTest(unittest.TestCase):
    def test_compressed_clip_round_trip(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            video = tmp / "clip.mp4"
            frames = [frame(dy=-int(round(30 * math.sin(math.pi * t / 23))), seed=t) for t in range(24)]
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SIZE}x{SIZE}",
                 "-r", "24", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(video)],
                input=b"".join(f.tobytes() for f in frames), capture_output=True)
            if proc.returncode:
                self.skipTest("libx264 unavailable")
            source = gs.VideoFrames(video)
            self.assertEqual(source.size, (SIZE, SIZE))
            r = gs.process(source, "jump", "green", gs.settings_for("jump", {}), tmp / "out")
            self.assertTrue(r["ok"], r["issues"])
            self.assertEqual(r["source_fps"], 24.0)
            self.assertEqual(len(r["files"]["frames"]), 10)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
