import unittest

from studio.lib import cinema


def _lib(shots):
    return {"audio": {"mode": "film", "voice_lang": "English"}, "characters": [{"name": "Kael"}],
            "shots": shots}


class DialogueLanguage(unittest.TestCase):
    def test_language_code_becomes_h3_language_name(self):
        prompt = cinema.compose_h3_prompt({"character": "Kael", "action": "Kael grits his teeth.",
                                           "dialogue": "Kilitle beni.", "dialogue_lang": "tr"})
        self.assertIn("<d>[Turkish] Kilitle beni.</d>", prompt)

    def test_chosen_scene_language_is_not_flagged(self):
        shot = cinema._shot_from_section({"character": "Kael", "action": "Kael grits his teeth.",
                                          "dialogue": "Kilitle beni.", "dialogue_lang": "tr"}, 0)
        codes = [i["code"] for i in cinema.lint_shots([shot], _lib([shot]))["issues"]]
        self.assertNotIn("lang_mismatch", codes)

    def test_hand_written_tag_still_flagged(self):
        shot = {"id": "s1", "text": "Kael (S1) says: <d>[Turkish] Kilitle beni.</d>", "mode": "t2v"}
        codes = [i["code"] for i in cinema.lint_shots([shot], _lib([shot]))["issues"]]
        self.assertIn("lang_mismatch", codes)

    def test_preamble_lets_each_tag_choose_its_language(self):
        text = cinema.film_audio_preamble({"mode": "film", "voice_lang": "English"})
        self.assertIn("Speak each tag in the language named at its start", text)
        self.assertIn("tags without a language are in English", text)


if __name__ == "__main__":
    unittest.main()
