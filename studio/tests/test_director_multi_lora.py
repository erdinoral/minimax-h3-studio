import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from lib import asset_references, loras, cinema


class DirectorMultiLoraTests(unittest.TestCase):
    def test_global_albedo_is_skipped_in_ainz_only_structured_scene(self):
        body=SimpleNamespace(lora_name='AlbedoOverlordEng_H3_v1.safetensors',lora_id='',lora_strength=.8,lora_strengths={})
        with patch.object(server,'spec_ready',return_value=True):
            src,_=server._lora_src_for_shot(body,{'hits':[], 'prompt':'Main character: Ainz Ooal Gown Opening composition: Ainz on the throne.'},'t2v')
            self.assertIsNone(src.lora_name)
            src,_=server._lora_src_for_shot(body,{'hits':[], 'prompt':'Main character: Albedo Opening composition: Albedo walks.'},'t2v')
            self.assertEqual(src.lora_name,'AlbedoOverlordEng_H3_v1.safetensors')

    def test_offscreen_name_in_voice_bible_dialogue_and_identity_does_not_cast_actor(self):
        actor={"id":"albedo","kind":"character","name":"Albedo","use_lora":True,"lora_id":"albedo-h3"}
        text=('CAST VOICE BIBLE — named speakers:\n- Albedo: soft voice.\n- Ainz: deep voice.\n\n'
              'Main character: Ainz Ooal Gown Opening composition: Ainz sits on the throne. '
              'Action: Ainz looks at Albedo off screen. <d>Seni dinliyorum, Albedo.</d>\n'
              'Character Albedo uses the learned identity: lbd0c1tr0n.')
        self.assertEqual(cinema.match_prompt(text,{'characters':[actor]}),[])
        self.assertEqual(cinema.match_prompt(text.replace('Main character: Ainz Ooal Gown','Main character: Ainz Ooal Gown, Albedo'),{'characters':[actor]})[0]['id'],'albedo')
        self.assertEqual(cinema.match_prompt('CAST VOICE BIBLE:\n- Albedo: soft voice.\n\nAinz sits. <d>Hello Albedo.</d>',{'characters':[actor]}),[])

    def test_named_albedo_is_loaded_and_triggered_for_each_director_shot(self):
        actor={"id":"albedo", "kind":"character", "name":"Albedo", "use_lora":True,
               "lora_id":"albedo-h3", "lora_strength":.8, "voice":"calm alto",
               "images":[{"file":"old-unrelated-face.png"}]}
        lib={"characters":[actor]}
        body=SimpleNamespace(lora_name="",lora_id="",lora_strength=.8,lora_strengths={})
        for bindings in (None, [], [{"asset_id":"albedo"}]):
            for index in range(6):
                text=f'Albedo walks through the castle, shot {index+1}.'
                with patch('lib.loras.spec_ready',return_value=True), patch.object(server,'spec_ready',return_value=True), patch('lib.lora_guidance.load_store',return_value={}):
                    plan=asset_references.resolve(text,bindings,lib,lambda f:False,continuation=bool(index))
                    src,_=server._lora_src_for_shot(body,plan,'continue' if index else 't2v')
                    prompt=loras.apply_selected_triggers(plan['prompt'],file=src.lora_name)
                self.assertEqual(src.lora_name,'AlbedoOverlordEng_H3_v1.safetensors')
                self.assertEqual(plan['ref_images'],[])
                self.assertEqual(len(plan['hits']),1)
                self.assertIn('lbd0c1tr0n',prompt)
                self.assertIn('calm alto',prompt)

    def test_named_lora_actor_is_not_added_when_disabled_or_absent(self):
        actor={"id":"albedo","name":"Albedo","use_lora":False,"lora_id":"albedo-h3"}
        plan=asset_references.resolve('Albedo walks.',[],{'characters':[actor]},lambda f:False)
        self.assertEqual(plan['hits'],[])
        actor['use_lora']=True
        plan=asset_references.resolve('An empty castle.',[],{'characters':[actor]},lambda f:False)
        self.assertEqual(plan['hits'],[])

    def test_stack_survives_director_asset_binding(self):
        specs = {name: {"id": name, "file": name, "graphs": ["fl2va", "ref2va"]}
                 for name in ("a.safetensors", "b.safetensors", "c.safetensors")}
        def lookup(lora_id="", file=""):
            return specs.get(file) or specs.get(lora_id)
        body = SimpleNamespace(lora_name="a.safetensors|b.safetensors|c.safetensors", lora_id="a.safetensors", lora_strength=.8)
        with patch.object(server, "find_spec", side_effect=lookup), patch.object(server, "spec_ready", return_value=True):
            result, graph = server._lora_src_for_shot(body, {"hits": [{"kind": "character", "use_lora": True, "lora_id": "b.safetensors"}]}, "face")
        self.assertEqual(graph, "ref2va")
        self.assertEqual(result.lora_name, "b.safetensors|a.safetensors|c.safetensors")

    def select(self, names="style.safetensors", actors=(), weights=None, missing=(), graph="face"):
        def lookup(lora_id="", file=""):
            name = file or lora_id
            if not name:
                return None
            return {"id": name, "file": name, "strength": .7,
                    "graphs": ["fl2va"] if name == "turbo.safetensors" else ["fl2va", "ref2va"]}
        body = SimpleNamespace(lora_name=names, lora_id="", lora_strength=.6, lora_strengths=weights or {})
        with patch.object(server, "find_spec", side_effect=lookup), patch.object(server, "spec_ready", side_effect=lambda s:s["file"] not in missing):
            return server._lora_src_for_shot(body, {"hits": list(actors)}, graph)[0]

    def actor(self, name="actor.safetensors", weight=.9, enabled=True):
        return {"kind":"character", "use_lora":enabled, "lora_id":name, "lora_strength":weight}

    def test_actor_and_style_are_both_loaded(self):
        result=self.select(actors=[self.actor()])
        self.assertEqual(result.lora_name, "actor.safetensors|style.safetensors")
        self.assertEqual(result.lora_strengths, {"actor.safetensors":.9, "style.safetensors":.6})

    def test_zero_card_weight_wins_and_duplicate_is_loaded_once(self):
        result=self.select("actor.safetensors|style.safetensors", [self.actor(weight=0)], {"actor.safetensors":1, "style.safetensors":0})
        self.assertEqual(result.lora_strengths, {"actor.safetensors":0, "style.safetensors":0})
        self.assertEqual(result.lora_name.count("actor.safetensors"),1)

    def test_two_actor_adapters_are_kept(self):
        result=self.select(actors=[self.actor(), self.actor("second.safetensors",.5)])
        self.assertEqual(result.lora_name, "actor.safetensors|second.safetensors|style.safetensors")

    def test_disabled_actor_is_ignored(self):
        self.assertEqual(self.select(actors=[self.actor(enabled=False)]).lora_name, "style.safetensors")

    def test_overflow_is_rejected_without_dropping_actor(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select("a.safetensors|b.safetensors|c.safetensors", [self.actor()])
        self.assertEqual(caught.exception.detail["code"], "lora.stackLimit")

    def test_missing_adapter_is_rejected(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select(actors=[self.actor()], missing=["actor.safetensors"])
        self.assertEqual(caught.exception.detail["code"], "lora.actorUnavailable")

    def test_incompatible_turbo_does_not_remove_actor(self):
        result=self.select("turbo.safetensors|style.safetensors", [self.actor()])
        self.assertEqual(result.lora_name, "actor.safetensors|style.safetensors")

    def test_incompatible_selection_without_actor_is_rejected(self):
        with self.assertRaises(server.HTTPException) as caught:
            self.select("turbo.safetensors")
        self.assertEqual(caught.exception.detail["code"], "lora.noCompatibleSelection")


if __name__ == "__main__":
    unittest.main()
