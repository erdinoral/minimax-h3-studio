import unittest

from lib.comfy import ComfyClient


def _messages(exc_type, message):
    return [["execution_error", {"exception_type": exc_type, "exception_message": message}]]


class ExecutionErrorFormat(unittest.TestCase):
    def test_long_cuda_error_keeps_the_cause_line(self):
        message = ("CUDA error: no kernel image is available for execution on the device\n"
                   "CUDA kernel errors might be asynchronously reported at some other API call, "
                   "so the stacktrace below might be incorrect.\n"
                   "For debugging consider passing CUDA_LAUNCH_BLOCKING=1\n"
                   "Compile with `TORCH_USE_CUDA_DSA` to enable device-side assertions.\n")
        text = ComfyClient.format_execution_error(_messages("torch.AcceleratorError", message))
        self.assertEqual(text, "torch.AcceleratorError: CUDA error: no kernel image is available for execution on the device")

    def test_out_of_memory_and_tensor_dumps_stay_short(self):
        oom = ComfyClient.format_execution_error(_messages("torch.OutOfMemoryError", "CUDA out of memory. " + "x" * 400))
        self.assertIn("CUDA OOM", oom)
        dump = ComfyClient.format_execution_error(_messages("RuntimeError", "tensor([" + "1, " * 200 + "])"))
        self.assertEqual(dump, "RuntimeError: Comfy node hatası (ayrıntı kısaltıldı)")

    def test_very_long_first_line_is_clipped(self):
        text = ComfyClient.format_execution_error(_messages("RuntimeError", "y" * 500))
        self.assertTrue(text.endswith("…"))
        self.assertLess(len(text), 230)


if __name__ == "__main__":
    unittest.main()
