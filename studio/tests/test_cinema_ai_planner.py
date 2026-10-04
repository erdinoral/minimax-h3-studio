import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).parents[1]))
from lib import cinema, cinema_planner as planner


def sample():
    current = {"film_id":"film-a", "duration":5, "quality":"480", "steps":10, "studio_mode":"assets", "setup":{"look":"realistic"},
        "characters":[{"id":"nea-id", "name":"NEA", "notes":"Original wardrobe", "voice":"Original voice", "use_lora":True, "lora_id":"nea", "lora_file":"nea.safetensors", "lora_strength":0.85}],
        "locations":[{"id":"metro-id", "name":"Metro", "notes":"Original location"}],
        "creatures":[], "vehicles":[], "shots":[{"id":"old-shot","chapter":"Bölüm 1","text":"Existing scene", "mode":"t2v"}], "chapters":["Bölüm 1"]}
    section = {k:"" for k in planner.SECTION_FIELDS}
    section.update(mode="t2v", title="The platform", location="Metro", character="NEA", action="NEA walks slowly along the platform and stops beside a white pillar.", camera="Medium shot, eye-level tracking camera.", opening_frame="NEA stands at the platform entrance.", ending_frame="NEA stops by a white pillar.", audio="Quiet station hum.")
    package = {"schema":"h3-cinema/v1", "title":"Metro", "logline":"A mysterious encounter.", "characters":[{"name":"NEA", "notes":"Invented different face", "lora_id":"wrong"}], "locations":[], "sections":[section, {**section,"mode":"continue", "title":"The footsteps"}]}
    return current, package


class Planner(unittest.IsolatedAsyncioTestCase):
    async def test_repair_missing_scenes_before_returning_package(self):
        current, package = sample()
        router = type("Router", (), {})()
        router.chat = AsyncMock(side_effect=[json.dumps({**package,"sections":package["sections"][:1]}),json.dumps(package)])
        result = await planner.generate_package(router, "model", [], current, 2)
        self.assertEqual(len(result["sections"]),2)
        self.assertEqual(router.chat.await_count,2)
        self.assertIn("Repair the COMPLETE package",router.chat.call_args.args[1][-1]["content"])

    async def test_repeated_invalid_reply_is_rejected_without_partial_package(self):
        current, package = sample()
        package["sections"][1]["location"]="Unregistered location"
        router = type("Router", (), {})()
        router.chat = AsyncMock(return_value=json.dumps(package))
        with self.assertRaisesRegex(ValueError,"unknownAsset"):
            await planner.generate_package(router,"model",[],current,2)
        self.assertEqual(router.chat.await_count,2)

    def test_existing_lora_identity_and_images_are_not_returned_for_overwrite(self):
        current, package = sample()
        before=copy.deepcopy(current)
        package["characters"].append({"name":"Visitor", "notes":"An adult man in a dark coat.", "images":[{"file":"fake.png"}],"lora_id":"wrong"})
        result=planner.validate_package(package,current,2)
        self.assertEqual(current,before)
        self.assertEqual([a["name"] for a in result["characters"]],["Visitor"])
        self.assertNotIn("images",result["characters"][0])
        self.assertNotIn("lora_id",result["characters"][0])

    def test_hard_cut_required_for_location_change_and_first_scene(self):
        current, package=sample()
        package["locations"]=[{"name":"Street","notes":"Wet nighttime street."}]
        package["sections"][1]["location"]="Street"
        with self.assertRaisesRegex(ValueError,"invalidContinuity"):
            planner.validate_package(package,current,2)
        package["sections"][1]["mode"]="t2v"
        self.assertEqual(planner.validate_package(package,current,2)["sections"][1]["mode"],"t2v")
        package["sections"][0]["mode"]="continue"
        with self.assertRaisesRegex(ValueError,"invalidContinuity"):
            planner.validate_package(package,current,2)

    def test_importer_fills_editor_fields_and_preserves_existing_film(self):
        current, package=sample()
        validated=planner.validate_package(package,current,2)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(cinema,"CINEMA_FILE",root/"cinema.json"),patch.object(cinema,"FILMS_DIR",root/"films"),patch.object(cinema,"REFS_DIR",root/"refs"):
                cinema.save(current)
                result=cinema.import_project_json(validated,mode="merge",new_film=False,chapter="Bölüm 2",keep_stills=True)
                out=result["cinema"]
                self.assertEqual(out["film_id"],"film-a")
                self.assertEqual(len(out["shots"]),3)
                self.assertEqual(out["shots"][0]["id"],"old-shot")
                self.assertEqual(out["shots"][1]["structured"]["opening_frame"],package["sections"][0]["opening_frame"])
                self.assertEqual(out["shots"][1]["structured"]["character"],"NEA")
                self.assertTrue(out["characters"][0]["use_lora"])
                self.assertEqual(out["characters"][0]["lora_id"],"nea")
                self.assertEqual(out["characters"][0]["voice"],"Original voice")
                self.assertEqual(out["quality"],"480")
                self.assertEqual(out["steps"],10)

    def test_missing_schema_metadata_is_normalized_without_inventing_scenes(self):
        current, package = sample()
        package.pop("schema")
        result = planner.validate_package(json.dumps(package), current, 2)
        self.assertEqual(result["schema"], "h3-cinema/v1")
        self.assertEqual(len(result["sections"]), 2)
        self.assertEqual(result["sections"][0]["action"], package["sections"][0]["action"])

    def test_messages_include_named_cast_and_exact_clip_contract(self):
        current,_=sample()
        messages=planner.planning_messages(current,{},"NEA encounters a visitor",12,5,"en")
        self.assertIn("exactly 12 sections",messages[0]["content"])
        context=json.loads(messages[1]["content"])
        self.assertEqual(context["existing_assets"]["characters"][0]["lora_file"],"nea.safetensors")
        self.assertEqual(context["clip_seconds"],5)
        self.assertIn("opening_frame",context["section_shape"])
