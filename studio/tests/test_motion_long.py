import ast
import unittest
from pathlib import Path

from lib.frames import duration_to_length
from lib.motion_long import FPS, part_prompts, plan_windows


class PlanWindowsTest(unittest.TestCase):
    def test_covers_the_whole_video_exactly(self):
        for seconds in (4.0, 7.5, 15.0, 28.04, 30.0):
            windows = plan_windows(seconds)
            self.assertEqual(sum(w["frames"] for w in windows), round(seconds * FPS))
            self.assertEqual(windows[0]["start_frame"], 0)
            for prev, cur in zip(windows, windows[1:]):
                self.assertEqual(cur["start_frame"], prev["start_frame"] + prev["frames"])

    def test_each_part_fits_its_render(self):
        for window in plan_windows(28.04):
            self.assertGreaterEqual(duration_to_length(window["duration"]), window["frames"] + window["skip"])
            self.assertAlmostEqual(window["ref_seconds"] * FPS, window["frames"] + window["skip"])

    def test_later_parts_start_on_the_previous_boundary_frame(self):
        windows = plan_windows(12.0)
        self.assertEqual(windows[0]["skip"], 0)
        for window in windows[1:]:
            self.assertEqual(window["skip"], 1)
            self.assertAlmostEqual(window["ref_start"] * FPS, window["start_frame"] - 1)

    def test_short_tail_joins_previous_part(self):
        windows = plan_windows(10.5)
        self.assertEqual([w["frames"] for w in windows], [120, 132])
        self.assertEqual(windows[-1]["duration"], 6)


class PartPromptsTest(unittest.TestCase):
    def test_each_part_gets_only_its_own_beats(self):
        windows = plan_windows(10.42)
        beats = [
            {"start": 0, "text": "He walks toward the stool."},
            {"start": 5.3, "text": "He turns and sits down"},
            {"start": 7.9, "text": "He looks at his phone"},
        ]
        first, second = part_prompts("Base.", beats, windows)
        self.assertEqual(first, "Base. In this shot: He walks toward the stool.")
        self.assertEqual(second, "Base. In this shot: He walks toward the stool. Then He turns and sits down. Then He looks at his phone.")

    def test_explicit_end_and_no_beats(self):
        windows = plan_windows(10.42)
        beats = [{"start": 0, "end": 4.0, "text": "walks"}, {"start": 6.0, "text": "sits"}]
        self.assertEqual(part_prompts("B.", beats, windows), ["B. In this shot: walks.", "B. In this shot: sits."])
        self.assertEqual(part_prompts("B.", [], windows), ["B.", "B."])


class JobLaneTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_job_lane"]
        nodes += [n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "MOTION_MODES" for t in n.targets)]
        self.env = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "server-lanes", "exec"), self.env)

    def test_motion_jobs_get_their_own_lane(self):
        lane = self.env["_job_lane"]
        self.assertEqual(lane({"mode": "v2v", "lane": "scene"}), "motion")
        self.assertEqual(lane({"mode": "motion_long"}), "motion")
        self.assertEqual(lane({"mode": "t2v", "lane": "scene"}), "scene")
        self.assertEqual(lane({"mode": "continue", "lane": "director"}), "director")
        self.assertEqual(lane({"mode": "t2v", "batch_id": "b1"}), "director")


if __name__ == "__main__":
    unittest.main()
