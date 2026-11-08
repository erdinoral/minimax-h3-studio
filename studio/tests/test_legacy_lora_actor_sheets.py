import unittest
from unittest.mock import AsyncMock, patch


LEGACY = {"id": "nea", "kind": "character", "name": "NEA", "notes": "silver hair",
          "use_lora": True, "lora_id": "nea", "lora_strength": 0.9}


class LegacyLoraActorSheetTests(unittest.IsolatedAsyncioTestCase):
    def test_legacy_lora_actor_without_images_needs_sheet(self):
        import server
        self.assertTrue(server._asset_needs_sheet(dict(LEGACY)))

    async def test_legacy_lora_actor_uses_selected_image_provider(self):
        import server
        for provider, method in (("image_studio", "qwen"), ("minimax", "h3"), ("look_sheets", "sheet")):
            cine = {"characters": [dict(LEGACY)], "image_provider": provider,
                    "shots": [{"text": "NEA walks.", "structured": {"character": "NEA"}}]}
            gen = AsyncMock(return_value={"asset": {"id": "nea", "name": "NEA"}, "job": {"id": "j1"}})
            with patch.object(server.comfy, "healthy", AsyncMock(return_value=True)), \
                 patch.object(server, "cinema_generate_sheet", gen), patch.object(server, "_jobs", []):
                queued = await server._queue_sheets_for_cinema(cine, mentioned_only=True)
            self.assertEqual([q["job_id"] for q in queued], ["j1"], provider)
            self.assertEqual(gen.call_args.args[0].production_method, method)


if __name__ == "__main__":
    unittest.main()
