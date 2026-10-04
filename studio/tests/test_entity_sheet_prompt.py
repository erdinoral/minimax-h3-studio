import unittest

from studio.lib.cinema import build_character_sheet_prompt, build_location_sheet_prompt


class EntitySheetPromptTests(unittest.TestCase):
    def test_shadow_does_not_get_dragon_anatomy(self):
        description = (
            "Never fully shown. An elongated human-like shadow, "
            "kept off-screen or reduced to a silhouette."
        )
        prompt = build_character_sheet_prompt(
            "The Shape", description, force_creature=True
        )
        self.assertIn(description, prompt)
        self.assertIn("follow exactly, do not replace with a generic monster", prompt)
        self.assertIn("Do not add traits absent from the authority text", prompt)
        self.assertNotIn("four legs or true creature anatomy", prompt)
        self.assertNotIn("sharp scale detail", prompt)
        self.assertNotIn("show the real creature body", prompt.lower())

    def test_ghost_or_zombie_can_use_entity_sheet(self):
        for name in ("Ghost", "Zombie", "Hayalet", "Zombi"):
            with self.subTest(name=name):
                prompt = build_character_sheet_prompt(name)
                self.assertIn("ENTITY identity sheet", prompt)
                self.assertIn("Do NOT default to a stock dragon", prompt)
                self.assertNotIn("full non-human creature", prompt)

    def test_location_plate_excludes_cast_even_when_named_in_notes(self):
        prompt = build_location_sheet_prompt(
            "Alex's Attic", "Alex stands near the window beside a dragon",
            has_place_ref=True,
        )
        self.assertIn("EMPTY set only: no people, no characters, no creatures", prompt)
        self.assertIn("Remove any people or creatures from the reference", prompt)
        self.assertIn("this plate is for the empty location only", prompt)


if __name__ == "__main__":
    unittest.main()
