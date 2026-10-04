import unittest

from studio.lib import cinema


class SceneDirectionTests(unittest.TestCase):
    def test_prompt_and_portable_json_preserve_direction(self):
        section = {
            "title": "Knight's tear",
            "duration": 5,
            "reference_subjects": "Knight: face and armor",
            "reference_environment": "Chapel: layout and lighting",
            "opening_frame": "Helmet close-up",
            "ending_frame": "A tear leaves his eye",
            "camera_movement": "push in",
            "camera_amplitude": "small",
            "camera_speed": "slow",
            "camera_target": "his eye",
            "beats": "0: he looks up\n4: the tear falls",
        }
        shot = cinema._shot_from_section(section, 0)
        exported = cinema._section_from_shot(shot)
        for key in section:
            self.assertEqual(exported[key], section[key])

        prompt = cinema.compose_h3_prompt(shot["structured"])
        self.assertIn("The camera pushes in with small amplitude at slow speed toward his eye.", prompt)
        self.assertIn("Chronological action beats: 0: he looks up; 4: the tear falls.", prompt)
        self.assertIn("Subject references: Knight: face and armor.", prompt)
        self.assertIn("End composition: A tear leaves his eye", prompt)


if __name__ == "__main__":
    unittest.main()
