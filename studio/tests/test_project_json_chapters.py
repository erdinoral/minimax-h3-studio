import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio.lib import cinema, continuum


def _section(chapter, mode, title):
    return {"chapter": chapter, "mode": mode, "title": title, "location": "Harbor",
            "character": "Kael", "action": f"{title}: Kael braces in the cockpit."}


class ProjectJsonChapters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(cinema, "CINEMA_FILE", root / "film.json"),
                        patch.object(cinema, "LIBRARY_FILE", root / "library.json"),
                        patch.object(cinema, "_archive_film")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_section_round_trip_keeps_chapter_and_take(self):
        section = dict(_section("Part 2", "continue", "Bite"), take_index=3, take_title="Harbor fight")
        shot = cinema._shot_from_section(section, 1)
        self.assertEqual((shot["chapter"], shot["take_index"]), ("Part 2", 3))
        row = cinema._section_from_shot(shot)
        self.assertEqual((row["chapter"], row["take_index"], row["take_title"]),
                         ("Part 2", 3, "Harbor fight"))

    def test_import_keeps_chapters_so_continuum_splits_chains(self):
        result = cinema.import_project_json({"characters": [{"name": "Kael"}], "sections": [
            _section("Part 1", "t2v", "Boarding"), _section("Part 1", "continue", "Lock"),
            _section("Part 1", "continue", "Pain"), _section("Part 2", "continue", "Rise")]}, new_film=True)
        film = result["cinema"]
        chapters = ["Part 1", "Part 1", "Part 1", "Part 2"]
        self.assertEqual([s["chapter"] for s in film["shots"]], chapters)
        self.assertEqual(film["chapters"], ["Part 1", "Part 2"])
        groups = continuum.director_chain_groups(film["shots"], [s["text"] for s in film["shots"]])
        self.assertEqual([(g["kind"], g["chapter"], len(g["shots"])) for g in groups],
                         [("new", "Part 1", 1), ("continue", "Part 1", 2), ("continue", "Part 2", 1)])
        exported = cinema.export_project_json()["sections"]
        self.assertEqual([s["chapter"] for s in exported], chapters)

    def test_take_block_chapter_applies_to_its_sections(self):
        result = cinema.import_project_json({"takes": [
            {"title": "Sahne 1", "chapter": "Act I", "sections": [_section("", "t2v", "A")]},
            {"title": "Sahne 2", "sections": [_section("Act II", "t2v", "B")]}]}, new_film=True)
        self.assertEqual([s["chapter"] for s in result["cinema"]["shots"]], ["Act I", "Act II"])

    def test_merge_into_empty_tail_card_keeps_json_chapter(self):
        cinema.save({"shots": [{"id": "blank", "chapter": "Bölüm 1", "text": "", "mode": "t2v"}],
                     "chapters": ["Bölüm 1"]})
        result = cinema.import_project_json({"sections": [_section("Part 3", "t2v", "Fall")]},
                                            mode="merge", new_film=False)
        shot = result["cinema"]["shots"][0]
        self.assertEqual((shot["id"], shot["chapter"]), ("blank", "Part 3"))


if __name__ == "__main__":
    unittest.main()
