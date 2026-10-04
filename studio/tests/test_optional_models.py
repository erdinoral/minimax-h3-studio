import hashlib
import httpx
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from lib import optional_models as models

class OptionalModels(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patch=patch.object(models,"MODELS_ROOT",self.root)
        self.patch.start()
        models.folder().mkdir()
    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()
    async def test_existing_alias_does_not_start_duplicate_download(self):
        with patch.dict(models.SINGULARITY,{"bytes":3}):
            (models.folder()/models.ALIASES[1]).write_bytes(b"abc")
            with patch.object(models,"_download") as download:
                result=await models.start(models.SINGULARITY["id"])
                self.assertTrue(result["ready"])
                self.assertEqual(result["installed_file"],models.ALIASES[1])
                download.assert_not_called()
    async def test_existing_unet_folder_alias_is_reused(self):
        with patch.dict(models.SINGULARITY,{"bytes":3}):
            (self.root/"unet").mkdir()
            (self.root/"unet"/models.ALIASES[0]).write_bytes(b"abc")
            with patch.object(models,"_download") as download:
                result=await models.start(models.SINGULARITY["id"])
                self.assertTrue(result["ready"])
                download.assert_not_called()
    def test_partial_never_appears_as_installed(self):
        with patch.dict(models.SINGULARITY,{"bytes":3}):
            (models.folder()/(models.SINGULARITY["file"]+".part")).write_bytes(b"abc")
            self.assertFalse(models.catalog()[0]["ready"])
    def test_hash_mismatch_is_rejected(self):
        path=models.folder()/"test.part"
        path.write_bytes(b"abc")
        with patch.dict(models.SINGULARITY,{"bytes":3,"sha256":hashlib.sha256(b"xyz").hexdigest()}):
            with self.assertRaisesRegex(ValueError,"SHA256"):
                models.verify(path)
    def test_correct_hash_verifies(self):
        path=models.folder()/"test.part"
        path.write_bytes(b"abc")
        with patch.dict(models.SINGULARITY,{"bytes":3,"sha256":hashlib.sha256(b"abc").hexdigest()}):
            models.verify(path)
    async def test_unknown_model_cannot_start(self):
        with self.assertRaisesRegex(ValueError,"Unknown"):
            await models.start("../anything")

    async def test_resume_download_is_verified_before_activation(self):
        partial=models.folder()/(models.SINGULARITY["file"]+".part")
        partial.write_bytes(b"a")
        seen=[]
        def handler(request):
            seen.append(request.headers.get("range"))
            return httpx.Response(206,headers={"Content-Range":"bytes 1-2/3"},content=b"bc")
        original=httpx.AsyncClient
        client=lambda **kwargs: original(transport=httpx.MockTransport(handler),**kwargs)
        with patch.dict(models.SINGULARITY,{"bytes":3,"sha256":hashlib.sha256(b"abc").hexdigest()}),patch.object(models.httpx,"AsyncClient",side_effect=client):
            await models._download()
            self.assertEqual(seen,["bytes=1-"])
            self.assertEqual(models.installed().read_bytes(),b"abc")
            self.assertFalse(partial.exists())
    async def test_download_with_wrong_hash_stays_partial(self):
        original=httpx.AsyncClient
        client=lambda **kwargs: original(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b"xyz")),**kwargs)
        with patch.dict(models.SINGULARITY,{"bytes":3,"sha256":hashlib.sha256(b"abc").hexdigest()}),patch.object(models.httpx,"AsyncClient",side_effect=client):
            await models._download()
            self.assertIsNone(models.installed())
            self.assertIn("SHA256",models._status["error"])
