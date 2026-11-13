import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import h3_models, loras, lora_access, model_downloads, optional_models


class ModelDownloadsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for target, value in ((h3_models, self.root), (optional_models, self.root)):
            patcher = patch.object(target, "MODELS_ROOT", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (patch.object(loras, "LORAS_DIR", self.root / "loras"),
                        patch.object(lora_access, "key", return_value="")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def rows(self):
        return {row["id"]: row for row in model_downloads.catalog()["items"]}

    def test_catalog_covers_packs_engine_and_loras(self):
        rows = self.rows()
        for item_id in ("shared", "fl2va", "ref2va", "h3-image", "encoder-int8", optional_models.SINGULARITY["id"]):
            self.assertFalse(rows[item_id]["installed"])
        downloadable = [spec for spec in loras.CATALOG if spec.get("url")]
        self.assertEqual(len([r for r in rows.values() if r["group"] == "lora"]), len(downloadable))
        state = model_downloads.catalog()
        keyed = [r for r in rows.values() if r["needs_key"]]
        self.assertEqual(state["missing"], len(rows) - len(keyed))

    def test_pack_install_state_and_delete(self):
        pack = next(p for p in model_downloads.PACKS if p["id"] == "h3-image")
        for folder, name, _ in pack["files"][:1]:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
            (self.root / folder / name).write_bytes(b"x")
        self.assertFalse(self.rows()["h3-image"]["installed"])
        folder, name, _ = pack["files"][1]
        (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / folder / name).write_bytes(b"yy")
        self.assertTrue(self.rows()["h3-image"]["installed"])
        with self.assertRaisesRegex(ValueError, "storage.protected"):
            model_downloads.remove("h3-image", {name})
        self.assertEqual(model_downloads.remove("h3-image")["freed"], 3)
        self.assertFalse(self.rows()["h3-image"]["installed"])
        with self.assertRaises(FileNotFoundError):
            model_downloads.remove("h3-image")
        with self.assertRaises(KeyError):
            model_downloads.remove("missing")

    def test_download_resumes_partial_file(self):
        pack = next(p for p in model_downloads.PACKS if p["id"] == "fl2va")
        folder, name, _ = pack["files"][0]
        payload = b"0123456789"
        (self.root / folder).mkdir(parents=True)
        (self.root / folder / (name + ".part")).write_bytes(payload[:4])
        ranges = []

        def handler(request):
            ranges.append(request.headers.get("range"))
            return httpx.Response(206, content=payload[4:], headers={"content-range": "bytes 4-9/10"})

        real_client = httpx.AsyncClient
        with patch.object(model_downloads.httpx, "AsyncClient",
                          lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            async def go():
                model_downloads.enqueue(["fl2va"])
                await model_downloads._runner
            asyncio.run(go())
        self.assertEqual(ranges, ["bytes=4-"])
        self.assertEqual((self.root / folder / name).read_bytes(), payload)
        self.assertFalse((self.root / folder / (name + ".part")).exists())
        row = self.rows()["fl2va"]
        self.assertTrue(row["installed"])
        self.assertIsNone(row["error"])

    def test_failed_item_records_error_and_queue_continues(self):
        def handler(request):
            if "fl2va" in str(request.url):
                return httpx.Response(500)
            return httpx.Response(200, content=b"ok")

        real_client = httpx.AsyncClient
        with patch.object(model_downloads.httpx, "AsyncClient",
                          lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            async def go():
                model_downloads.enqueue(["fl2va", "ref2va"])
                await model_downloads._runner
            asyncio.run(go())
        rows = self.rows()
        self.assertFalse(rows["fl2va"]["installed"])
        self.assertTrue(rows["fl2va"]["error"])
        self.assertTrue(rows["ref2va"]["installed"])
        self.assertFalse(model_downloads.busy())


if __name__ == "__main__":
    unittest.main()
