import unittest
import tempfile
import asyncio
from unittest.mock import AsyncMock, patch
from pathlib import Path
from lib import model_storage


class ModelStorageTests(unittest.TestCase):
    def test_delete_one_file_preserves_other_weights_and_protected_model(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'loras';folder.mkdir()
            (folder/'unused.safetensors').write_bytes(b'weights')
            (folder/'active.safetensors').write_bytes(b'active')
            self.assertEqual(model_storage.remove(root,'loras','unused.safetensors',{'active.safetensors'}),7)
            self.assertTrue((folder/'active.safetensors').exists())
            with self.assertRaisesRegex(ValueError,'protected'):
                model_storage.remove(root,'loras','active.safetensors',{'active.safetensors'})

    def test_paths_and_nonweight_files_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as root:
            for folder,name in [('loras','../outside.safetensors'),('..','model.safetensors'),('loras','C:\\secret.safetensors'),('loras','config.json')]:
                with self.assertRaises(ValueError):model_storage.remove(root,folder,name)

    def test_inventory_protection_and_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'diffusion_models';folder.mkdir()
            (folder/'active.safetensors').write_bytes(b'model')
            (folder/'partial.safetensors.part').write_bytes(b'partial')
            rows=model_storage.inventory(root,{'active.safetensors'})
            self.assertEqual(len(rows),2);self.assertTrue(rows[0]['protected'])
            self.assertEqual(model_storage.remove(root,'diffusion_models','partial.safetensors.part'),7)
            with self.assertRaises(FileNotFoundError):model_storage.remove(root,'loras','missing.safetensors')


class StorageEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_comfy_job_blocks_deletion_before_touching_weights(self):
        import server
        with patch.object(server,'_jobs',[]),patch.object(server,'_lock',asyncio.Lock()),patch.object(server,'_lora_dl_status',{}),patch.object(server.optional_models,'catalog',return_value=[]),patch.object(server.comfy,'queue_status',AsyncMock(return_value={'queue_running':[1],'queue_pending':[]})),patch.object(server.model_storage,'remove') as remove:
            with self.assertRaises(server.HTTPException) as err:
                await server.model_storage_delete(server.ModelDeleteBody(folder='loras',file='unused.safetensors'))
            self.assertEqual(err.exception.detail['code'],'storage.busy')
            remove.assert_not_called()
