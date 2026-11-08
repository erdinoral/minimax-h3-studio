import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import comfy


def cubin(sm, new_abi=True):
    header = bytearray(52)
    header[0:4] = b"\x7fELF"
    header[4] = 2
    struct.pack_into("<H", header, 18, 190)
    flags = 0x6000004 | (sm << 8) if new_abi else 0x00500000 | sm
    struct.pack_into("<I", header, 48, flags)
    return b"host-code" + bytes(header) + b"kernel"


class SageArchGuard(unittest.TestCase):
    def setUp(self):
        comfy._sage_arch_cache.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.pkg = Path(self.tmp.name) / "sageattention"
        self.pkg.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, *sms, new_abi=True):
        (self.pkg / name).write_bytes(b"".join(cubin(sm, new_abi) for sm in sms))

    def test_reads_both_cuda_elf_abis(self):
        blob = cubin(120) + cubin(89) + cubin(80, new_abi=False)
        self.assertEqual(comfy.cuda_binary_archs(blob), {120, 89, 80})
        self.assertEqual(comfy.cuda_binary_archs(b"compressed fatbin"), set())

    def test_linux_torch210_wheel_without_blackwell_is_rejected_on_rtx50(self):
        self.write("_qattn_sm89.cpython-310-x86_64-linux-gnu.so", 80, 90)
        self.write("_qattn_sm90.cpython-310-x86_64-linux-gnu.so", 90)
        self.assertFalse(comfy.sage_supports_gpu(self.pkg, 120))
        self.assertTrue(comfy.sage_supports_gpu(self.pkg, 89))
        self.assertTrue(comfy.sage_supports_gpu(self.pkg, 86))
        self.assertFalse(comfy.sage_supports_gpu(self.pkg, 75))

    def test_blackwell_build_and_unknown_builds_stay_enabled(self):
        self.write("_qattn_sm89.pyd", 89, 120)
        self.assertTrue(comfy.sage_supports_gpu(self.pkg, 120))
        self.assertTrue(comfy.sage_supports_gpu(self.pkg, 121))
        comfy._sage_arch_cache.clear()
        for f in self.pkg.iterdir():
            f.write_bytes(b"compressed")
        self.assertTrue(comfy.sage_supports_gpu(self.pkg, 120))

    def test_detect_sage_mode_disables_unsupported_build(self):
        root = Path(self.tmp.name) / "app"
        (root / "custom_nodes" / "ComfyUI-KJNodes").mkdir(parents=True)
        pkg = root / "env" / "lib" / "python3.10" / "site-packages" / "sageattention"
        pkg.mkdir(parents=True)
        (pkg / "_qattn_sm89.cpython-310-x86_64-linux-gnu.so").write_bytes(cubin(80) + cubin(90))
        with patch.object(comfy, "_gpu_sm", return_value=120):
            self.assertIsNone(comfy.detect_sage_mode(root))
        with patch.object(comfy, "_gpu_sm", return_value=89):
            self.assertEqual(comfy.detect_sage_mode(root), "auto")
        with patch.object(comfy, "_gpu_sm", return_value=None):
            self.assertEqual(comfy.detect_sage_mode(root), "auto")


if __name__ == "__main__":
    unittest.main()
