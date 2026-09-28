import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.comfy import (
    build_multishot_prompt,
    build_ref2va_prompt,
    build_t2v_prompt,
)


class FastPreviewGraphTests(unittest.TestCase):
    def test_final_video_uses_full_vae(self):
        graph = build_t2v_prompt(text="A quiet street")
        self.assertEqual(graph["10"]["class_type"], "VAEDecode")

    def test_tae_draft_replaces_only_video_decode(self):
        graph = build_t2v_prompt(text="A quiet street", fast_preview_tae="taeh3.safetensors")
        self.assertEqual(graph["10"]["class_type"], "H3TAEDecode")
        self.assertEqual(graph["10"]["inputs"]["samples"], ["14", 0])
        self.assertEqual(graph["23"]["class_type"], "VAEDecodeAudio")
        self.assertEqual(graph["92"]["class_type"], "SaveVideo")

    def test_reference_draft_uses_tae(self):
        graph = build_ref2va_prompt(
            text="A quiet street",
            ref_image_names=["reference.png"],
            fast_preview_tae="taeh3.safetensors",
        )
        self.assertEqual(graph["10"]["class_type"], "H3TAEDecode")

    def test_multishot_saves_first_shot_early(self):
        graph = build_multishot_prompt(script="One shot")
        self.assertTrue(graph["104"]["inputs"]["preview_first_shot"])


if __name__ == "__main__":
    unittest.main()
