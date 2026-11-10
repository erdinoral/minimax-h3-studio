import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lib import h3_image, look_sheets, qwen_still


def _touch(root: Path, *relative: str) -> None:
    for rel in relative:
        path = root / "models" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


H3_FILES = ("diffusion_models/" + h3_image.UNET, "vae/" + h3_image.VAE, "text_encoders/" + h3_image.TEXT_ENCODERS[0])
QWEN_FILES = tuple(f"{folder}/{name}" for folder, name in qwen_still.MODELS.items())


class H3ImageGraphs(unittest.TestCase):
    def test_text_to_image_uses_the_distilled_release_settings(self):
        graph = h3_image.build_graph(prompt="A pier", negative="ignored", aspect="16:9", steps=30, seed=7)
        self.assertEqual(graph["10"]["inputs"]["unet_name"], h3_image.UNET)
        self.assertEqual(graph["20"]["inputs"]["type"], "minimax")
        self.assertEqual(graph["30"]["class_type"], "MiniMaxH3ImageConditioning")
        self.assertEqual((graph["30"]["inputs"]["width"], graph["30"]["inputs"]["height"]), h3_image.SIZES["16:9"])
        sampler = graph["50"]["inputs"]
        self.assertEqual((sampler["steps"], sampler["cfg"], sampler["denoise"]), (6, 1.0, 1.0))
        self.assertEqual(sampler["latent_image"], ["30", 1])
        self.assertEqual(graph["31"]["class_type"], "ConditioningZeroOut")
        self.assertEqual(graph["70"]["class_type"], "SaveImage")

    def test_source_image_starts_from_its_encoded_latent(self):
        graph = h3_image.build_graph(prompt="P", aspect="9:16", seed=1, source_image="layout.png")
        self.assertEqual(graph["40"]["class_type"], "VAEEncode")
        self.assertEqual(graph["50"]["inputs"]["latent_image"], ["40", 0])
        self.assertEqual(graph["50"]["inputs"]["denoise"], 0.55)
        self.assertEqual((graph["26"]["inputs"]["width"], graph["26"]["inputs"]["height"]), h3_image.SIZES["9:16"])

    def test_storyboard_frame_passes_up_to_three_pictures(self):
        graph = h3_image.build_storyboard_frame(prompt="Picture 1 waves", ref_images=["a.png", "", "b.png", "c.png", "d.png"],
                                                aspect="16:9", seed=3)
        inputs = graph["30"]["inputs"]
        self.assertEqual([inputs[f"images.image_{i}"] for i in (1, 2, 3)], [["25_1", 0], ["25_2", 0], ["25_3", 0]])
        self.assertNotIn("images.image_4", inputs)
        self.assertEqual(graph["25_3"]["inputs"]["image"], "c.png")
        plain = h3_image.build_storyboard_frame(prompt="Empty", ref_images=[], aspect="16:9", seed=3)
        self.assertFalse(any(key.startswith("images.") for key in plain["30"]["inputs"]))

    def test_sketch_edit_reads_the_drawing_as_picture_one_on_a_fresh_latent(self):
        graph = h3_image.build_sketch_edit(prompt="P", negative="N", reference="ref.png", aspect="16:9", steps=30, seed=2)
        self.assertEqual(graph["30"]["inputs"]["images.image_1"], ["25", 0])
        self.assertEqual(graph["50"]["inputs"]["latent_image"], ["30", 1])
        self.assertEqual(graph["50"]["inputs"]["denoise"], 1.0)

    def test_reference_views_render_one_image_per_view_at_full_resolution(self):
        for kind in ("character", "vehicle", "location"):
            graph = h3_image.build_reference_views(kind=kind, notes="same identity", style_line="realistic",
                                                   source_image="source.png", steps=20, seed=8, width=480, height=864)
            count = look_sheets.view_count(kind)
            self.assertEqual(len([n for n in graph if n.startswith("70_")]), count)
            for index in range(count):
                text = graph[f"view_{index}_text"]["inputs"]
                self.assertEqual(text["images.image_1"], ["25", 0])
                self.assertIn("<Picture 1>", text["prompt"])
                self.assertEqual(graph[f"70_{index}"]["inputs"]["images"], [f"view_{index}_decode", 0])
            width, height = graph["view_0_text"]["inputs"]["width"], graph["view_0_text"]["inputs"]["height"]
            self.assertEqual((width % 32, height % 32), (0, 0))
            self.assertAlmostEqual(width / height, 480 / 864, delta=0.02)
            self.assertGreater(width * height, 3_500_000)
            self.assertNotIn("70", graph)

    def test_missing_models_accepts_either_video_text_encoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(len(h3_image.missing_models(root)), 3)
            _touch(root, "diffusion_models/" + h3_image.UNET, "vae/" + h3_image.VAE,
                   "text_encoders/" + h3_image.TEXT_ENCODERS[1])
            self.assertEqual(h3_image.missing_models(root), [])
            self.assertEqual(h3_image.text_encoder(root), h3_image.TEXT_ENCODERS[1])


class StudioStills(unittest.TestCase):
    def test_only_h3_image_draws_even_when_qwen_files_exist(self):
        import server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(server, "COMFY_ROOT", root):
                _touch(root, *QWEN_FILES)
                self.assertEqual(server._still_missing(), h3_image.missing_models(root))
                _touch(root, *H3_FILES)
                self.assertEqual(server._still_missing(), [])
                graph = server._build_still("build_graph", prompt="P", negative="N", aspect="16:9", steps=20, seed=1)
                self.assertEqual(graph["10"]["inputs"]["unet_name"], h3_image.UNET)
                self.assertEqual(graph["20"]["inputs"]["clip_name"], h3_image.TEXT_ENCODERS[0])

    def test_drawings_always_use_visual_reference(self):
        import server
        args = server._sketch_args(source="d.png", text="a man waving", style="", fidelity="balanced", aspect="16:9")
        self.assertEqual(args["method"], "edit")
        self.assertIn("Picture 1", args["prompt"])


class ReferenceStill(unittest.IsolatedAsyncioTestCase):
    async def test_scene_reference_is_drawn_by_h3_image_and_imported(self):
        import server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root, *H3_FILES)
            still = root / "out.png"
            still.write_bytes(b"png")
            run = AsyncMock(return_value=still)
            imported = AsyncMock(return_value={"name": "h3_ref.png", "filename": "h3_ref.png"})
            with patch.object(server, "COMFY_ROOT", root), patch.object(server, "_run_qwen_still", run), \
                    patch.object(server.comfy, "healthy", AsyncMock(return_value=True)), \
                    patch.object(server, "_import_reference_bytes", imported), patch.object(server, "_set_ref_prompt"):
                result = await server.create_image_studio_reference(server.ImageStudioReferenceBody(prompt="A pier", aspect="9:16"))
                status = await server.image_studio_status()
        graph = run.call_args.args[1]
        self.assertEqual(graph["10"]["inputs"]["unet_name"], h3_image.UNET)
        self.assertEqual((graph["30"]["inputs"]["width"], graph["30"]["inputs"]["height"]), h3_image.SIZES["9:16"])
        self.assertEqual(imported.call_args.args[0], b"png")
        self.assertEqual(result["source"], "h3-image")
        self.assertTrue(status["available"])
        self.assertEqual(server._reference_stills, [])


if __name__ == "__main__":
    unittest.main()
