import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import server


def _parts(role="face_swap", first_status="done"):
    first = {"id": "p1", "motion_long_id": "mlong-x", "motion_long_index": 1, "status": first_status,
             "v2v_role": role, "motion_long_window": {"skip": 0, "frames": 100}}
    second = {"id": "p2", "motion_long_id": "mlong-x", "motion_long_index": 2, "status": "running",
              "v2v_role": role}
    return first, second


class IdentityAnchor(unittest.TestCase):
    def run_anchor(self, jobs, job, crop_results):
        calls = {"frames": [], "crops": 0}

        def extract(video, index, output):
            calls["frames"].append(index)
            Path(output).write_bytes(b"frame")
            return output

        def crop(source, output, folder):
            result = crop_results[calls["crops"]]
            calls["crops"] += 1
            if result:
                Path(output).write_bytes(b"face")
                return Path(output)
            return None

        with tempfile.TemporaryDirectory() as tmp, patch.object(server, "_jobs", jobs), \
                patch.object(server, "REFS", Path(tmp)), patch.object(server, "FRAMES", Path(tmp)), \
                patch.object(server, "_ensure_job_video", new_callable=AsyncMock, return_value=Path(tmp) / "p1.mp4"), \
                patch.object(server.motion_long, "extract_frame", side_effect=extract), \
                patch.object(server.face_crop, "crop_main_face", side_effect=crop), \
                patch.object(server.comfy, "upload_image", new_callable=AsyncMock, return_value="anchor.png"):
            name = asyncio.run(server._motion_long_identity_anchor(job))
        return name, calls

    def test_later_part_gets_a_face_from_part_one(self):
        first, second = _parts()
        name, calls = self.run_anchor([first, second], second, [None, True])
        self.assertEqual(name, "anchor.png")
        self.assertEqual(second["identity_anchor"], "anchor.png")
        self.assertEqual(calls["frames"], [50, 25])

    def test_no_anchor_for_first_part_other_roles_or_unfinished_part_one(self):
        first, second = _parts()
        self.assertEqual(self.run_anchor([first, second], first, [True])[0], None)
        first, second = _parts(role="swap")
        self.assertEqual(self.run_anchor([first, second], second, [True])[0], None)
        first, second = _parts(first_status="running")
        name, calls = self.run_anchor([first, second], second, [True])
        self.assertIsNone(name)
        self.assertEqual(calls["frames"], [])

    def test_missing_face_skips_the_anchor(self):
        first, second = _parts()
        name, calls = self.run_anchor([first, second], second, [None, None, None])
        self.assertIsNone(name)
        self.assertNotIn("identity_anchor", second)
        self.assertEqual(calls["frames"], [50, 25, 75])


if __name__ == "__main__":
    unittest.main()
