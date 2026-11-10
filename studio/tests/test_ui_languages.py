import unittest

from lib.director import fallback_director_reply, normalize_ui_lang, ready_shots_reply, ui_lang_addendum


class UiLanguageTests(unittest.TestCase):
    def test_new_languages_are_recognised_and_unknown_ones_get_english(self):
        self.assertEqual(normalize_ui_lang(None), "tr")
        self.assertEqual(normalize_ui_lang("fr-FR"), "fr")
        self.assertEqual(normalize_ui_lang("es"), "es")
        self.assertEqual(normalize_ui_lang("DE"), "de")
        self.assertEqual(normalize_ui_lang("it"), "en")

    def test_director_speaks_the_ui_language_but_keeps_english_prompts(self):
        addendum = ui_lang_addendum("de")
        self.assertIn("Speak to the user in **German**", addendum)
        self.assertIn("MUST stay English", addendum)
        self.assertIn("**English**", ui_lang_addendum("en"))
        self.assertIn("Türkçe", ui_lang_addendum("tr"))

    def test_canned_director_messages_use_english_outside_turkish(self):
        self.assertIn("ready", ready_shots_reply(2, None, "fr"))
        self.assertIn("hazır", ready_shots_reply(2, None, "tr"))
        self.assertIn("connection dropped", fallback_director_reply({}, "", "es"))


if __name__ == "__main__":
    unittest.main()
