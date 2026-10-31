import unittest

from studio.lib.director import (
    CONTINUE_CAMERA,
    diversify_outline_cameras,
    normalize_shot_outline,
    outline_generation_user_prompt,
    scene_format_addendum,
    scene_format_from_text,
    single_shot_user_prompt,
)


def _brief(rows):
    return {"expectedShotCount": len(rows), "clipDurationSec": 5, "shotOutline": rows}


class DirectorShotStructureTests(unittest.TestCase):
    def test_outline_keeps_cut_continue_plan_and_forces_first_cut(self):
        rows = normalize_shot_outline(_brief([
            {"title": "A", "beat": "a", "camera": "wide", "link": "continue", "sectionId": "room", "endFrame": "close"},
            {"title": "B", "beat": "b", "camera": "push-in continues", "link": "devam", "sectionId": "room"},
            {"title": "C", "beat": "c", "camera": "side shot", "linkToPrev": "standalone"},
        ]))
        self.assertEqual([r.get("link") for r in rows], ["cut", "continue", "cut"])
        self.assertEqual(rows[0]["sectionId"], "room")
        self.assertEqual(rows[0]["endFrame"], "close")

    def test_generic_cameras_vary_only_on_cuts(self):
        rows = diversify_outline_cameras([
            {"index": 1, "camera": "", "link": "cut"},
            {"index": 2, "camera": "", "link": "continue"},
            {"index": 3, "camera": "", "link": "cut"},
        ])
        self.assertNotEqual(rows[0]["camera"], CONTINUE_CAMERA)
        self.assertEqual(rows[1]["camera"], CONTINUE_CAMERA)
        self.assertNotEqual(rows[2]["camera"], rows[0]["camera"])

    def test_vary_angles_leaves_continue_camera_alone(self):
        rows = diversify_outline_cameras([
            {"index": 1, "camera": "low push-in", "link": "cut"},
            {"index": 2, "camera": "the push-in keeps going", "link": "continue"},
        ], {"varyAngles": True})
        self.assertEqual(rows[1]["camera"], "the push-in keeps going")

    def test_outline_prompt_asks_for_plan_fields(self):
        prompt = outline_generation_user_prompt({"expectedShotCount": 3, "clipDurationSec": 5})
        self.assertIn("SHOT STRUCTURE", prompt)
        self.assertIn('"link": "continue"', prompt)

    def test_shot_prompt_follows_outline_plan(self):
        brief = _brief([])
        prev = {"h3Prompt": "Previous body", "sectionId": "room"}
        cont = single_shot_user_prompt(brief, index=1, need=3, prev_shot=prev, outline_row={
            "title": "B", "beat": "b", "camera": "the push-in continues", "link": "continue", "endFrame": "tight shot"})
        self.assertIn("suggested linkToPrev=continue", cont)
        self.assertIn("CONTINUES the previous shot", cont)
        self.assertIn("sectionId=room", cont)
        self.assertIn("tight shot", cont)
        cut = single_shot_user_prompt(brief, index=2, need=3, prev_shot=prev, outline_row={
            "title": "C", "beat": "c", "camera": "side shot", "link": "cut", "sectionId": "room"})
        self.assertIn("suggested linkToPrev=standalone", cut)
        self.assertIn("is a CUT", cut)

    def test_scene_format_answers(self):
        cases = {
            "tek": "single", "tekli": "single", "tek shot olsun": "single", "single shot": "single",
            "uzun": "long", "uzun bir sahne düşünüyorum": "long", "12 shot": "long", "1 dakika": "long",
            "[proje: clipDurationSec=5 (her shot TAM 5sn), purpose=short_film]\nuzun saçlı bir kız çay içiyor": "",
            "anime bir dövüş sahnesi": "",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(scene_format_from_text(text), want)
        self.assertEqual(scene_format_from_text("10 saniye", clip_sec=10), "single")

    def test_scene_format_addendum_asks_until_chosen(self):
        self.assertIn("NOT CHOSEN", scene_format_addendum(""))
        self.assertIn("expectedShotCount 1", scene_format_addendum("single"))
        self.assertIn("link (cut|continue)", scene_format_addendum("long"))


if __name__ == "__main__":
    unittest.main()
