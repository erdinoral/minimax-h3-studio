import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import cinema, plan_review
from lib.review_api import create_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeLlm:
    def __init__(self):
        self.response = {"text": "A opens the door and steps through it."}
        self.callback = None
    async def resolve_model(self, _):
        return "test"
    async def chat(self, *args, **kwargs):
        if self.callback:
            self.callback()
        return json.dumps(self.response)


class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        self.film = {"film_id": "film1", "shots": [
            {"id": "a", "text": "A opens the door.", "review": "approved", "mode": "t2v", "seed": 11},
            {"id": "b", "text": "A opens the door.", "review": "draft", "mode": "continue", "bindings": [{"asset_id": "face"}]}]}

    def test_selective_patch_preserves_every_other_shot_and_settings(self):
        before = copy.deepcopy(self.film)
        result = plan_review.apply_patches(self.film, plan_review.fingerprint(self.film), {"b": "A steps through the open door."})
        self.assertEqual(result["shots"][0], before["shots"][0])
        self.assertEqual(result["shots"][1]["bindings"], before["shots"][1]["bindings"])
        self.assertEqual(self.film, before)

    def test_approved_patch_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            plan_review.apply_patches(self.film, plan_review.fingerprint(self.film), {"a": "Changed"})

    def test_malformed_ai_identifiers_are_rejected(self):
        for row in [{"shot_id": [], "code": "omission"}, {"shot_id": "b", "code": {}}]:
            with self.assertRaises(ValueError):
                plan_review.normalize_ai_issues({"issues": [row]}, self.film)

    def test_reference_change_invalidates_checkpoint(self):
        signature = plan_review.fingerprint(self.film)
        self.film["shots"][1]["bindings"].append({"asset_id": "other"})
        with self.assertRaisesRegex(ValueError, "stale"):
            plan_review.apply_patches(self.film, signature, {"b": "Changed"})

    def test_dialogue_removal_or_translation_rejected(self):
        self.film["shots"][1]["text"] = '<d>[A] Merhaba.</d> A waves.'
        for text in ['A waves.', '<d>[A] Hello.</d> A waves.']:
            with self.assertRaisesRegex(ValueError, "dialogueChanged"):
                plan_review.apply_patches(self.film, plan_review.fingerprint(self.film), {"b": text})

    def test_disable_and_new_scene_continuity(self):
        self.film["shots"][0]["enabled"] = False
        issues = plan_review.basic_review(self.film)
        self.assertEqual(issues[0]["message"], "review.noPrevious")
        self.assertFalse(issues[0]["repairable"])

    def test_reference_tags_cannot_be_rebound_or_removed(self):
        self.film["shots"][1]["text"] = '<Picture 1> is A. A waves.'
        for text in ['A waves.', '<Picture 2> is A. A waves.']:
            with self.assertRaisesRegex(ValueError, 'referencesChanged'):
                plan_review.apply_patches(self.film, plan_review.fingerprint(self.film), {'b':text})

    def test_ai_cannot_invent_evidence_or_shot_id(self):
        for row in [{"shot_id": "missing", "evidence": "A", "code": "omission", "message": "Bad"},
                    {"shot_id": "b", "evidence": "not in prompt", "code": "omission", "message": "Bad"}]:
            with self.assertRaises(ValueError):
                plan_review.normalize_ai_issues({"issues": [row]}, self.film)


class ReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.storage = patch.multiple(cinema, CINEMA_FILE=root / "cinema.json", FILMS_DIR=root / "films")
        self.storage.start()
        self.film = cinema.save({"film_id": "f", "shots": [
            {"id": "a", "text": "A opens the door.", "review": "approved", "selected_job": "old", "approved_signature": "sig"},
            {"id": "b", "text": "A opens the door.", "mode": "continue", "durationSec": 5, "bindings": []}]})
        self.jobs = []
        self.llm = FakeLlm()
        app = FastAPI()
        app.include_router(create_router(self.llm, lambda: self.jobs))
        self.client = TestClient(app)
    def tearDown(self):
        self.client.close()
        self.storage.stop()
        self.temp.cleanup()
    def report(self):
        response = self.client.post('/api/cinema/review', json={"film_id": "f"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()
    def test_preview_is_read_only_and_apply_changes_only_selected_shot(self):
        before = cinema.load()
        report = self.report()
        request = {"checkpoint": report["checkpoint"], "shot_ids": ["b"]}
        draft = self.client.post('/api/cinema/review/draft', json=request)
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(cinema.load(), before)
        applied = self.client.post('/api/cinema/review/apply', json=request)
        self.assertEqual(applied.status_code, 200, applied.text)
        after = applied.json()["cinema"]
        self.assertEqual(before["shots"][0], after["shots"][0])
        self.assertNotEqual(before["shots"][1]["text"], after["shots"][1]["text"])
        for key in ("mode", "durationSec", "bindings"):
            self.assertEqual(before["shots"][1][key], after["shots"][1][key])
        self.assertEqual(self.client.post('/api/cinema/review/apply', json=request).status_code, 409)
    def test_busy_or_approved_selection_never_repaired(self):
        report = self.report()
        request = {"checkpoint": report["checkpoint"], "shot_ids": ["a"]}
        self.assertEqual(self.client.post('/api/cinema/review/draft', json=request).status_code, 400)
        self.jobs.append({"shot_id": "b", "status": "running", "film_id": "f"})
        request["shot_ids"] = ["b"]
        self.assertEqual(self.client.post('/api/cinema/review/draft', json=request).status_code, 409)
    def test_edit_during_llm_call_discards_draft(self):
        report = self.report()
        self.llm.callback = lambda: cinema.save({**cinema.load(), "title": "New title"})
        response = self.client.post('/api/cinema/review/draft', json={"checkpoint": report["checkpoint"], "shot_ids": ["b"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(cinema.load()["title"], "New title")
    def test_malformed_semantic_reply_is_not_reported_as_clear(self):
        self.llm.response = {"wrong": []}
        response = self.client.post('/api/cinema/review', json={"film_id": "f", "semantic": True})
        self.assertEqual(response.status_code, 502)


if __name__ == '__main__':
    unittest.main()
