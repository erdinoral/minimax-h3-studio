import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.comfy import (
    build_multishot_prompt,
    build_ref2va_prompt,
    build_t2v_prompt,
    detect_h3_tae,
)


class GraphApiCompatibilityTests(unittest.TestCase):
    def test_optional_tae_is_absent_on_clean_install(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(detect_h3_tae(Path(root)))

    def test_character_sheet_video_uses_regular_decoder(self):
        graph = build_t2v_prompt(text="three-panel character sheet", fast_preview_tae=None)
        self.assertEqual(graph["10"]["class_type"], "VAEDecode")

    def test_optional_tae_replaces_only_video_decoder(self):
        graph = build_t2v_prompt(text="test", fast_preview_tae="taeh3.safetensors")
        self.assertEqual(graph["10"]["class_type"], "H3TAEDecode")
        self.assertEqual(graph["23"]["class_type"], "VAEDecodeAudio")

    def test_reference_graph_accepts_optional_preview(self):
        graph = build_ref2va_prompt(
            text="test", ref_image_names=["portrait.png"], fast_preview_tae=None
        )
        self.assertEqual(graph["10"]["class_type"], "VAEDecode")

    def test_multishot_accepts_first_shot_preview(self):
        graph = build_multishot_prompt(script="test", preview_first_shot=True)
        self.assertTrue(graph["104"]["inputs"]["preview_first_shot"])


if __name__ == "__main__":
    unittest.main()
