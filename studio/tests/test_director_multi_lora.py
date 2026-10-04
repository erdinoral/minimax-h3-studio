import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class DirectorMultiLoraTests(unittest.TestCase):
    def test_stack_survives_director_asset_binding(self):
        specs = {name: {"id": name, "file": name, "graphs": ["fl2va", "ref2va"]}
                 for name in ("a.safetensors", "b.safetensors", "c.safetensors")}
        def lookup(lora_id="", file=""):
            return specs.get(file) or specs.get(lora_id)
        body = SimpleNamespace(lora_name="a.safetensors|b.safetensors|c.safetensors", lora_id="a.safetensors", lora_strength=.8)
        with patch.object(server, "find_spec", side_effect=lookup), patch.object(server, "spec_ready", return_value=True):
            result, graph = server._lora_src_for_shot(body, {"hits": [{"kind": "character", "use_lora": True, "lora_id": "b.safetensors"}]}, "face")
        self.assertEqual(graph, "ref2va")
        self.assertEqual(result.lora_name, body.lora_name)


if __name__ == "__main__":
    unittest.main()
