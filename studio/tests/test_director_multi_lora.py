import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from lib import loras, cinema


class DirectorMultiLoraTests(unittest.TestCase):
    def test_offscreen_name_in_voice_bible_and_dialogue_does_not_cast_actor(self):
        actor={"id":"albedo","kind":"character","name":"Albedo"}
        text=('CAST VOICE BIBLE — named speakers:\n- Albedo: soft voice.\n- Ainz: deep voice.\n\n'
              'Main character: Ainz Ooal Gown Opening composition: Ainz sits on the throne. '
              'Action: Ainz looks at Albedo off screen. <d>Seni dinliyorum, Albedo.</d>')
        self.assertEqual(cinema.match_prompt(text,{'characters':[actor]}),[])
        self.assertEqual(cinema.match_prompt(text.replace('Main character: Ainz Ooal Gown','Main character: Ainz Ooal Gown, Albedo'),{'characters':[actor]})[0]['id'],'albedo')
        self.assertEqual(cinema.match_prompt('CAST VOICE BIBLE:\n- Albedo: soft voice.\n\nAinz sits. <d>Hello Albedo.</d>',{'characters':[actor]}),[])

    def test_stack_survives_director_asset_binding(self):
        specs = {name: {"id": name, "file": name, "graphs": ["fl2va", "ref2va"]}
                 for name in ("a.safetensors", "b.safetensors", "c.safetensors")}
        def lookup(lora_id="", file=""):
            return specs.get(file) or specs.get(lora_id)
        body = SimpleNamespace(lora_name="a.safetensors|b.safetensors|c.safetensors", lora_id="a.safetensors", lora_strength=.8)
        with patch.object(server, "find_spec", side_effect=lookup), patch.object(server, "spec_ready", return_value=True):
            result, graph = server._lora_src_for_shot(body, {"hits": [{"kind": "character", "name": "Ada"}]}, "face")
        self.assertEqual(graph, "ref2va")
        self.assertEqual(result.lora_name, "a.safetensors|b.safetensors|c.safetensors")

    def select(self, names="style.safetensors", weights=None, missing=(), graph="face"):
        def lookup(lora_id="", file=""):
            name = file or lora_id
            if not name:
                return None
            return {"id": name, "file": name, "strength": .7,
                    "graphs": ["fl2va"] if name == "turbo.safetensors" else ["fl2va", "ref2va"]}
        body = SimpleNamespace(lora_name=names, lora_id="", lora_strength=.6, lora_strengths=weights or {})
        with patch.object(server, "find_spec", side_effect=lookup), patch.object(server, "spec_ready", side_effect=lambda s:s["file"] not in missing):
            return server._lora_src_for_shot(body, {"hits": []}, graph)[0]

    def test_selected_weights_are_kept(self):
        result=self.select("motion.safetensors|style.safetensors", {"motion.safetensors":0})
        self.assertEqual(result.lora_name, "motion.safetensors|style.safetensors")
        self.assertEqual(result.lora_strengths, {"motion.safetensors":0, "style.safetensors":.6})

    def test_overflow_is_rejected(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select("a.safetensors|b.safetensors|c.safetensors|d.safetensors|e.safetensors|f.safetensors")
        self.assertEqual(caught.exception.detail["code"], "lora.stackLimit")

    def test_missing_adapter_is_rejected(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select(missing=["style.safetensors"])
        self.assertEqual(caught.exception.detail["code"], "lora.selectionUnavailable")

    def test_incompatible_turbo_is_skipped(self):
        self.assertEqual(self.select("turbo.safetensors|style.safetensors").lora_name, "style.safetensors")

    def test_incompatible_selection_is_rejected(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select("turbo.safetensors")
        self.assertEqual(caught.exception.detail["code"], "lora.noCompatibleSelection")

    def test_draft_turbo_uses_fl2v_and_swaps_to_ref2v_on_asset_shots(self):
        ref2v = loras.find_spec(lora_id="lightx2v-ref2v-4step")["file"]
        for draft_id in ("lightx2v-fl2v-4step-v12", "erosmax-beta1-fl2v-4step"):
            draft = loras.find_spec(lora_id=draft_id)
            body = SimpleNamespace(lora_name=draft["file"], lora_id="", lora_strength=None, lora_strengths={})
            with patch.object(server, "spec_ready", return_value=True):
                face, face_graph = server._lora_src_for_shot(body, {"hits": []}, "face")
                new, new_graph = server._lora_src_for_shot(body, {"hits": []}, "t2v")
            self.assertEqual((face_graph, face.lora_name), ("ref2va", ref2v))
            self.assertEqual((new_graph, new.lora_name), ("fl2va", draft["file"]))

    def test_character_catalog_entries_are_gone(self):
        self.assertFalse([s for s in loras.CATALOG if s.get("category") == "character"])
        for lora_id in ("pinkfluffybunny", "albedo-h3", "mara-whitlock", "fyre", "ai30"):
            self.assertIsNone(loras.find_spec(lora_id=lora_id))


if __name__ == "__main__":
    unittest.main()
