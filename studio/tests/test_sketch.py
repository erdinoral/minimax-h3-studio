import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from lib import qwen_still, sketch


class EditMethodTest(unittest.TestCase):
    def test_edit_prompt_keeps_layout_and_completes_people(self):
        prompt = sketch.edit_prompt("a girl skipping rope", "Pixar 3D animation style.", "faithful")
        self.assertIn("Picture 1 is a rough hand drawing", prompt)
        self.assertIn("of: a girl skipping rope.", prompt)
        self.assertIn("Visual style: Pixar 3D animation style.", prompt)
        for kept in ("same number of people", "pose", "positions and sizes", "touches"):
            self.assertIn(kept, prompt)
        self.assertIn("anatomically correct people with natural faces, hands", prompt)
        self.assertIn(sketch.EDIT_FIDELITY["faithful"], prompt)

    def test_unknown_method_and_fidelity_fall_back(self):
        self.assertEqual(sketch.method("EDIT"), "edit")
        self.assertEqual(sketch.method("img2img"), "img2img")
        self.assertEqual(sketch.method("whatever"), "edit")
        self.assertIn(sketch.EDIT_FIDELITY["balanced"], sketch.edit_prompt("", "", "odd"))
        self.assertIn("the scene shown in the drawing", sketch.edit_prompt("", ""))

    def test_reference_is_white_paper_at_output_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "board.png"
            im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
            ImageDraw.Draw(im).line((200, 50, 200, 350), fill="black", width=8)
            im.save(src)
            out = sketch.prepare_reference(src, Path(tmp) / "ref.png", 1664, 928)
            with Image.open(out) as ref:
                self.assertEqual(ref.size, (1664, 928))
                self.assertEqual(ref.convert("L").getpixel((40, 464)), 255)
                self.assertLess(ref.convert("L").getpixel((832, 464)), 60)

    def test_edit_graph_feeds_drawing_as_picture_one_on_fresh_latent(self):
        graph = qwen_still.build_sketch_edit(prompt="P", negative="N", reference="ref.png", aspect="16:9",
                                             steps=30, seed=5)
        self.assertEqual(graph["10"]["inputs"]["unet_name"], qwen_still.EDIT_MODEL)
        self.assertEqual(graph["30"]["class_type"], "TextEncodeQwenImageEditPlus")
        self.assertEqual(graph["30"]["inputs"]["image1"], ["25", 0])
        self.assertEqual(graph["25"]["inputs"]["image"], "ref.png")
        self.assertNotIn("image1", graph["31"]["inputs"])
        self.assertEqual(graph["40"]["class_type"], "EmptySD3LatentImage")
        self.assertEqual((graph["40"]["inputs"]["width"], graph["40"]["inputs"]["height"]), qwen_still.SIZES["16:9"])
        self.assertEqual(graph["50"]["inputs"]["denoise"], 1.0)
        self.assertEqual(graph["50"]["inputs"]["steps"], 30)


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def drawing(self, size=(800, 800), mode="RGB"):
        im = Image.new(mode, size, "white" if mode == "RGB" else (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        draw.line((400, 100, 400, 700), fill="black", width=8)
        path = self.root / f"drawing_{mode}.png"
        im.save(path)
        return path

    def test_paper_becomes_mid_gray_and_strokes_stay_dark(self):
        out = sketch.prepare(self.drawing(), self.root / "out.png", 1664, 928, seed=1)
        with Image.open(out) as im:
            self.assertEqual(im.size, (1664, 928))
            gray = im.convert("L")
            # Square drawing padded into 16:9: paper and padding are no longer white.
            self.assertTrue(60 < gray.getpixel((100, 464)) < 200)
            self.assertTrue(60 < gray.getpixel((832, 30)) < 200)
            self.assertLess(gray.getpixel((832, 464)), 40)

    def test_transparent_png_counts_as_white_paper(self):
        out = sketch.prepare(self.drawing(mode="RGBA"), self.root / "out.png", 928, 1664)
        with Image.open(out) as im:
            gray = im.convert("L")
            self.assertTrue(60 < gray.getpixel((100, 832)) < 200)
            self.assertLess(gray.getpixel((464, 832)), 40)

    def test_closed_shape_is_filled_with_its_outline_colour(self):
        im = Image.new("RGB", (640, 360), "white")
        draw = ImageDraw.Draw(im)
        draw.rectangle((200, 100, 400, 300), outline=(200, 30, 30), width=6)
        draw.line((450, 50, 600, 300), fill="black", width=6)
        src = self.root / "shape.png"
        im.save(src)
        out = sketch.prepare(src, self.root / "out.png", 640, 360, seed=3)
        with Image.open(out) as res:
            r, g, b = res.getpixel((300, 200))
            self.assertGreater(r, 140)
            self.assertLess(g, 110)
            # Open strokes do not trap paper, and outside paper stays neutral.
            r, g, b = res.getpixel((100, 200))
            self.assertLess(abs(r - g), 40)

    def test_frame_around_everything_is_not_filled(self):
        im = Image.new("RGB", (640, 360), "white")
        ImageDraw.Draw(im).rectangle((5, 5, 634, 354), outline="blue", width=6)
        src = self.root / "frame.png"
        im.save(src)
        out = sketch.prepare(src, self.root / "out.png", 640, 360, seed=3)
        with Image.open(out) as res:
            r, g, b = res.getpixel((320, 180))
            self.assertLess(b - r, 40)

    def test_near_aspect_is_cropped_not_padded(self):
        src = self.root / "board.png"
        Image.new("RGB", (1280, 720), (90, 180, 240)).save(src)
        out = sketch.prepare(src, self.root / "out.png", 1664, 928, seed=1)
        with Image.open(out) as res:
            r, g, b = res.getpixel((1, 464))
            self.assertGreater(b - r, 60)

    def test_same_seed_same_paper(self):
        a = sketch.prepare(self.drawing(), self.root / "a.png", 640, 360, seed=7)
        b = sketch.prepare(self.drawing(), self.root / "b.png", 640, 360, seed=7)
        self.assertEqual(a.read_bytes(), b.read_bytes())


class PromptTest(unittest.TestCase):
    def test_style_line_leads_and_text_is_collapsed(self):
        prompt = sketch.frame_prompt("  a man\n running ", "Disney 3D style.")
        self.assertTrue(prompt.startswith("Disney 3D style. a man running."))
        self.assertIn("complete, detailed background", prompt)

    def test_prompt_punctuation_joins_cleanly(self):
        prompt = sketch.frame_prompt("a girl waves.", "soft studio lighting")
        self.assertTrue(prompt.startswith("soft studio lighting. a girl waves. A finished"))

    def test_empty_text_still_asks_for_a_scene(self):
        self.assertTrue(sketch.frame_prompt("", "").startswith("the scene."))

    def test_fidelity_maps_to_denoise(self):
        self.assertEqual(sketch.denoise("faithful"), 0.60)
        self.assertEqual(sketch.denoise("FREE"), 0.70)
        self.assertEqual(sketch.denoise("nonsense"), sketch.FIDELITY["balanced"])
        self.assertLess(sketch.REFINE, 0.7)


if __name__ == "__main__":
    unittest.main()
