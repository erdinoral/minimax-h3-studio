import unittest
from lib import backdrop, cinema, director_identity


class BackdropTests(unittest.TestCase):
    def film(self):
        return {"characters":[{"id":"ainz","kind":"character","name":"Ainz","images":[{"file":"ainz.png"}]}],
                "locations":[{"id":"throne","kind":"location","name":"Throne Room","images":[{"file":"throne.png"}]}]}

    def test_instruction_stays_in_the_visual_field(self):
        prompt = "integrated_multimodal_description: A man talks.\n\noverall_soundscape: Room tone.\n\nnon_diegetic_music: N/A"
        keyed = backdrop.apply(prompt, "green")
        visual, audio = keyed.split("\n\noverall_soundscape:")
        self.assertIn("flat pure green screen", visual)
        self.assertNotIn("green", audio)
        self.assertEqual(backdrop.apply(keyed, "green"), keyed)
        self.assertEqual(backdrop.apply("A man talks.", "blue"), "A man talks.\n\n" + backdrop.instruction("blue"))
        self.assertEqual(backdrop.apply(prompt, "purple"), prompt)

    def test_keyed_shot_drops_set_text_but_keeps_it_stored(self):
        structured = {"location": "Throne Room at night", "reference_environment": "Throne Room: layout",
                      "action": "Ainz raises his staff.", "backdrop": "green"}
        text = cinema.compose_h3_prompt(structured)
        self.assertNotIn("Throne Room", text)
        self.assertIn("Ainz raises his staff.", text)
        self.assertEqual(cinema._clean_structured(structured)["location"], "Throne Room at night")
        self.assertEqual(cinema._clean_structured({"backdrop": "purple"})["backdrop"], "")
        self.assertIn("Throne Room", cinema.compose_h3_prompt({**structured, "backdrop": ""}))

    def test_keyed_shot_sends_no_location_plate(self):
        lib = self.film()
        for bindings in (None, [{"asset_id":"ainz"}, {"asset_id":"throne"}]):
            raw = {"text": "Ainz stands in the Throne Room.", "bindings": bindings,
                   "structured": {"character": "Ainz", "backdrop": "blue"}}
            prepared = director_identity.prepare_shot(raw, lib)
            self.assertEqual([b["asset_id"] for b in prepared["bindings"]], ["ainz"])
            self.assertIn("flat pure blue screen", director_identity.prompt_for_shot(prepared, lib))
        unkeyed = director_identity.prepare_shot({"text": "Ainz stands in the Throne Room.",
                                                  "structured": {"character": "Ainz"}}, lib)
        self.assertIn("throne", {b["asset_id"] for b in unkeyed["bindings"]})


if __name__ == "__main__":
    unittest.main()
