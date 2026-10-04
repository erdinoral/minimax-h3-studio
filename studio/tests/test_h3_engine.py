import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from lib import optional_models as models, h3_models

class EngineSelection(unittest.TestCase):
    def test_both_graphs_change_and_auxiliary_choices_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "diffusion_models").mkdir()
            (root / "diffusion_models" / models.ALIASES[0]).write_bytes(b"abc")
            with patch.object(models, "MODELS_ROOT", root), patch.object(h3_models, "MODELS_ROOT", root), patch.object(h3_models, "SETTINGS_PATH", root / "settings.json"), patch.dict(models.SINGULARITY, bytes=3):
                h3_models.SETTINGS_PATH.write_text('{"clip":"my_encoder.safetensors","vae":"my_vae.safetensors"}')
                state = models.select_engine("singularity")
                self.assertEqual(state["active"], "singularity")
                for graph in ("fl2va", "ref2va"):
                    self.assertEqual(h3_models.resolve(graph)["unet"], models.ALIASES[0])
                    self.assertEqual(h3_models.resolve(graph)["clip"], "my_encoder.safetensors")
                self.assertEqual(models.select_engine("minimax")["active"], "minimax")
                self.assertEqual(h3_models.load()["vae"], "my_vae.safetensors")
                h3_models.save({"unet": models.ALIASES[0]})
                self.assertEqual(models.engine_status()["active"], "custom")

    def test_missing_or_unknown_engine_does_not_mutate_selection(self):
        with patch.object(models, "installed", return_value=None), patch.object(h3_models, "save") as save:
            for engine in ("singularity", "unknown"):
                with self.assertRaises(ValueError): models.select_engine(engine)
            save.assert_not_called()
