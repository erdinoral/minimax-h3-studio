import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import server
from lib import qwen_still
from PIL import Image


class DirectorImageProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_one_creature_image_keeps_card_and_updates_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = "h3_sheet_012345abcdef_front.png"
            with (
                patch.object(server.cinema, "CINEMA_FILE", root / "cinema.json"),
                patch.object(server.cinema, "LIBRARY_FILE", root / "library.json"),
                patch.object(server.cinema, "_archive_film"),
                patch.object(server, "REFS", root),
                patch.object(server, "COMFY_INPUT", root / "input"),
            ):
                card = server.cinema.upsert_asset("creature", {"name": "The Shape", "images": [{"file": file}]})
                server.cinema.save_film_asset_to_library("creature", card["id"])
                (root / file).write_bytes(b"still")
                result = await server.cinema_delete_asset_image("creature", card["id"], file)
                self.assertTrue(result["ok"])
                self.assertEqual(server.cinema.load()["creatures"][0]["images"], [])
                self.assertEqual(server.cinema.load_library()["creatures"][0]["images"], [])
                self.assertFalse((root / file).exists())

    def test_delete_card_cleans_orphan_source_but_keeps_library_still(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stem = "h3_sheet_012345abcdef"
            panel = stem + "_portrait.png"
            with (
                patch.object(server.cinema, "CINEMA_FILE", root / "cinema.json"),
                patch.object(server.cinema, "LIBRARY_FILE", root / "library.json"),
                patch.object(server.cinema, "REFS_DIR", root),
                patch.object(server.cinema, "COMFY_INPUT_DIR", root / "input"),
                patch.object(server.cinema, "_archive_film"),
            ):
                asset = server.cinema.upsert_asset("creature", {"name": "The Shape", "images": [{"file": panel}]})
                server.cinema.upsert_library_asset("creature", asset)
                (root / panel).write_bytes(b"panel")
                (root / (stem + ".png")).write_bytes(b"source")
                self.assertTrue(server.cinema.delete_asset("creature", asset["id"]))
                self.assertTrue((root / panel).exists())
                self.assertFalse((root / (stem + ".png")).exists())

    def test_creature_image_can_be_removed_without_old_still_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(server.cinema, "CINEMA_FILE", Path(tmp) / "cinema.json"),
                patch.object(server.cinema, "_archive_film"),
            ):
                asset = server.cinema.upsert_asset("creature", {"name": "The Shape", "images": [
                    {"file": f"h3_sheet_old_{part}.png"} for part in ("portrait", "front", "back")
                ]})
                updated = server.cinema.update_asset("creature", asset["id"], {
                    "images": [{"file": "h3_sheet_old_front.png"}, {"file": "h3_sheet_old_back.png"}],
                    "image": "h3_sheet_old_front.png",
                })
                self.assertEqual(len(updated["images"]), 2)
                self.assertEqual(len(server.cinema.load()["creatures"][0]["images"]), 2)
                server.cinema.update_asset("creature", asset["id"], {"images": [], "image": "", "url": ""})
                self.assertEqual(server.cinema.load()["creatures"][0]["images"], [])

    async def test_qwen_sheet_enters_director_job_queue(self):
        with (
            patch.object(server, "_jobs", []),
            patch.object(server.qwen_still, "missing_models", return_value=[]),
            patch.object(server, "_save_jobs"),
            patch.object(server, "_ensure_queue_loop"),
        ):
            result = await server._queue_cinema_qwen_sheet_job(kind="creature", name="The Shape", notes="shadow")
            job = result["job"]
            self.assertEqual(job["mode"], "qwen_sheet")
            self.assertEqual(job["lane"], "director")
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["qwen_sheet_args"]["name"], "The Shape")

    def test_native_qwen_graph_uses_h3_comfy_nodes(self):
        graph = qwen_still.build_graph(prompt="Empty room", negative="people", aspect="16:9", steps=30, seed=7)
        self.assertEqual(graph["20"]["inputs"]["type"], "qwen_image")
        self.assertEqual(graph["40"]["class_type"], "EmptySD3LatentImage")
        self.assertEqual(graph["50"]["inputs"]["steps"], 30)
        self.assertEqual(graph["31"]["inputs"]["text"], "people")

    def test_provider_survives_film_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(server.cinema, "CINEMA_FILE", Path(tmp) / "cinema.json"),
                patch.object(server.cinema, "_archive_film"),
            ):
                server.cinema.save({"film_id": "test-film", "image_provider": "image_studio"})
                server.cinema.save({"film_id": "test-film", "title": "Updated"})
                self.assertEqual(server.cinema.load()["image_provider"], "image_studio")

    async def test_image_studio_location_attaches_empty_set_still(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "image_studio_result.png").write_bytes(b"test-image")

            def fake_graph(**kwargs):
                self.assertIn("Empty LOCATION", kwargs["prompt"])
                self.assertIn("EMPTY set only", kwargs["prompt"])
                self.assertIn("person, human", kwargs["negative"])
                return {"graph": True}

            with (
                patch.object(server, "REFS", root),
                patch.object(server, "COMFY_OUTPUT", root),
                patch.object(server.qwen_still, "missing_models", return_value=[]),
                patch.object(server.qwen_still, "build_graph", side_effect=fake_graph),
                patch.object(server.comfy, "healthy", new_callable=AsyncMock, return_value=True),
                patch.object(server.comfy, "queue_prompt", new_callable=AsyncMock, return_value="job-1"),
                patch.object(server.comfy, "history", new_callable=AsyncMock, return_value={"job-1": {"outputs": {"70": {"images": [{"filename": "image_studio_result.png"}]}}}}),
                patch.object(server.asyncio, "sleep", new_callable=AsyncMock),
                patch.object(server.comfy, "upload_image", new_callable=AsyncMock, return_value="h3_sheet_test.png"),
                patch.object(server.cinema, "load", return_value={"locations": [], "setup": {}}),
                patch.object(server.cinema, "upsert_asset", side_effect=lambda kind, asset: {"id": "loc-1", **asset}),
                patch.object(server.cinema, "save_film_asset_to_library"),
            ):
                result = await server._generate_cinema_image_studio_sheet(
                    kind="location", name="Empty Attic", notes="Alex near a window"
                )

            self.assertEqual(result["image_provider"], "image_studio")
            self.assertEqual(result["asset"]["id"], "loc-1")
            self.assertEqual(len(result["asset"]["images"]), 1)
            self.assertTrue(result["asset"]["images"][0]["file"].startswith("h3_sheet_"))

    async def test_entity_regeneration_replaces_old_auto_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (1600, 900), "black").save(root / "image_studio_result.png")
            old = {"id": "entity-1", "name": "The Shape", "images": [
                {"file": f"h3_sheet_old_{part}.png"} for part in ("portrait", "front", "back")
            ]}

            def fake_graph(**kwargs):
                self.assertEqual(kwargs["aspect"], "16:9")
                self.assertIn("Unique ENTITY", kwargs["prompt"])
                self.assertIn("Only a shadow", kwargs["prompt"])
                self.assertIn("generic stock monster", kwargs["negative"])
                self.assertIn("dragon", kwargs["negative"])
                return {"graph": True}

            async def fake_upload(path, name):
                return name

            with (
                patch.object(server, "REFS", root),
                patch.object(server, "COMFY_OUTPUT", root),
                patch.object(server.qwen_still, "missing_models", return_value=[]),
                patch.object(server.qwen_still, "build_graph", side_effect=fake_graph),
                patch.object(server.comfy, "healthy", new_callable=AsyncMock, return_value=True),
                patch.object(server.comfy, "queue_prompt", new_callable=AsyncMock, return_value="job-1"),
                patch.object(server.comfy, "history", new_callable=AsyncMock, return_value={"job-1": {"outputs": {"70": {"images": [{"filename": "image_studio_result.png"}]}}}}),
                patch.object(server.asyncio, "sleep", new_callable=AsyncMock),
                patch.object(server.comfy, "upload_image", side_effect=fake_upload),
                patch.object(server.cinema, "load", return_value={"creatures": [old], "setup": {}}),
                patch.object(server.cinema, "upsert_asset", side_effect=lambda kind, asset: asset),
                patch.object(server.cinema, "save_film_asset_to_library"),
            ):
                result = await server._generate_cinema_image_studio_sheet(
                    kind="creature", name="The Shape", notes="Only a shadow",
                    asset_id="entity-1", aspect="9:16",
                )

            files = [image["file"] for image in result["asset"]["images"]]
            self.assertEqual(len(files), 3)
            self.assertTrue(all(name.startswith("h3_sheet_") and "old" not in name for name in files))


if __name__ == "__main__":
    unittest.main()
