import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from lib import loras, lora_access


class FilmLoras(unittest.TestCase):
    def test_redirect_drops_key_outside_civitai(self):
        handler=lora_access.DownloadRedirectHandler()
        req=Request('https://civitai.com/download',headers={'Authorization':'Bearer private'})
        other=handler.redirect_request(req,None,302,'Found',{},'https://cdn.example.test/file')
        same=handler.redirect_request(req,None,302,'Found',{},'https://civitai.com/file')
        self.assertIsNone(other.get_header('Authorization'))
        self.assertEqual(same.get_header('Authorization'),'Bearer private')

    def tiny(self, root):
        path=Path(root)/"MMH3-FocusSlider-V1.safetensors"
        header=json.dumps({"lora_A":{"dtype":"F16","shape":[1],"data_offsets":[0,2]}}).encode()
        path.write_bytes(len(header).to_bytes(8,"little")+header+b"\0\0")
        return path

    def test_tiny_valid_slider_is_ready_and_verified(self):
        with tempfile.TemporaryDirectory() as root, patch.object(loras,"LORAS_DIR",Path(root)):
            path=self.tiny(root)
            self.assertTrue(loras.file_ready(path.name))
            loras.verify_download(path,{"expected_bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})

    def test_corrupt_download_cannot_be_activated(self):
        with tempfile.TemporaryDirectory() as root:
            path=self.tiny(root)
            with self.assertRaisesRegex(ValueError,"SHA256"):
                loras.verify_download(path,{"sha256":"0"*64})
            path.write_text('<html>Login required</html>')
            self.assertFalse(loras.valid_safetensors(path))

    def test_key_is_not_sent_to_other_hosts(self):
        with patch.object(lora_access,"key",return_value="private"):
            self.assertIn("Authorization",lora_access.request_headers('https://civitai.com/api/download/models/1'))
            self.assertNotIn("Authorization",lora_access.request_headers('https://huggingface.co/file'))
            self.assertNotIn("Authorization",lora_access.request_headers('https://civitai.com.evil.test/file'))

    def test_camera_trigger_is_first_even_with_character_and_reference_prefix(self):
        specs={"actor":{"file":"actor","trigger":"NEA"},"camera":{"file":"camera","trigger":"camera motion","trigger_position":"start"}}
        with patch.object(loras,"find_spec",side_effect=lambda **kw:specs.get(kw.get('file'))),patch('lib.lora_guidance.guidance',side_effect=ValueError):
            text=loras.apply_selected_triggers('CONTINUATION LOCK: NEA walks. camera motion is requested.',file='camera|actor')
            self.assertTrue(text.startswith('camera motion, '))
            self.assertEqual(loras.apply_selected_triggers(text,file='actor|camera'),text)

    def test_catalog_has_unique_files_and_no_fake_speech_trigger(self):
        entries=[s for s in loras.CATALOG if s.get('sha256')]
        self.assertEqual(len({s['file'] for s in entries}),len(entries))
        self.assertEqual(loras.find_spec(lora_id='natural-face-speech')['trigger'],'')
        self.assertEqual(loras.find_spec(lora_id='character-swap')['graphs'],['ref2va'])
