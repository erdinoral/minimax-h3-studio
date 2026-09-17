import unittest

from studio.lib.cinema import normalize_produce_shots
from studio.lib.director import force_continue_chain


class ShotContinuityTests(unittest.TestCase):
    def test_same_character_in_new_scene_is_independent_by_default(self):
        shots = [
            {"h3Prompt": "X drives a car through the city."},
            {"h3Prompt": "X enters a castle courtyard."},
        ]
        result = force_continue_chain(shots, {"characters": [{"name": "X"}]})
        self.assertEqual([s["linkToPrev"] for s in result], ["standalone", "standalone"])

    def test_explicit_same_moment_continuation_is_preserved(self):
        result = force_continue_chain([
            {"h3Prompt": "X opens the door."},
            {"h3Prompt": "X steps through the same doorway.", "linkToPrev": "continue"},
        ])
        self.assertEqual([s["linkToPrev"] for s in result], ["standalone", "continue"])

    def test_plain_script_shots_start_new_videos(self):
        result = normalize_produce_shots(script="X in a car.\n\n---\n\nX at a castle.")
        self.assertEqual([s["mode"] for s in result], ["t2v", "t2v"])


if __name__ == "__main__":
    unittest.main()
