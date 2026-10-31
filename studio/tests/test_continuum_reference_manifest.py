import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from lib import cinema, continuum, native_continuation


SPIDER = {'id': 's', 'name': 'Spider-Man', 'kind': 'character', 'notes': 'Red and gold suit.'}
WOLVERINE = {'id': 'w', 'name': 'Wolverine', 'kind': 'character', 'notes': 'Yellow and blue suit.'}


class ContinuumReferenceManifest(unittest.IsolatedAsyncioTestCase):
    def environment(self):
        tree = ast.parse((Path(__file__).parents[1] / 'server.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if getattr(n, 'name', '') == '_queue_cinema_seamless']
        async def capabilities(): return {'continuum_ready': True}
        ns = dict(Any=Any, Optional=Optional, HTTPException=HTTPException, continuum=continuum,
                  cinema=cinema, workflow_capabilities=capabilities, detect_multishot_pack=lambda r: True,
                  COMFY_ROOT='.', MULTISHOT_MAX_SHOTS=4, resolve_size=lambda a, q: (864, 480),
                  normalize_quality=lambda q: q, _lora_src_for_shot=lambda b, h, m: (None, None),
                  _with_lora_preset=lambda src, st, sa, sc, graph: (st, sa, sc), _lora_fields=lambda src: {},
                  apply_selected_triggers=lambda t, **k: t, _sage_mode=lambda b: 'disabled',
                  _normalize_post_pass=lambda p: '', _voice_refs_from_hits=lambda h: [],
                  h3_models=SimpleNamespace(resolve=lambda kind: {'vae': 'v', 'audio_vae': 'a'}),
                  _lock=_AsyncNull(), _jobs=[], _save_jobs=lambda: None, CinemaProduceBody=object,
                  slog=SimpleNamespace(info=lambda *a, **k: None), time=__import__('time'),
                  uuid=__import__('uuid'))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'seamless', 'exec'), ns)
        return ns

    async def test_continuum_take_keeps_asset_ownership_for_each_reference(self):
        ns = self.environment()
        body = SimpleNamespace(seamless_backend='continuum', duration=5, continuum_max_chunks=4,
                               continuum_grouping='chapter', aspect='16:9', quality='480', steps=20,
                               sampler=None, scheduler=None, seed=7, post_pass='')
        plans = [
            {'prompt': 'Spider-Man lands.', 'hits': [SPIDER], 'ref_images': ['spider.png'],
             'rows': [{'file': 'spider.png', 'asset': SPIDER}]},
            {'prompt': 'Wolverine strikes Spider-Man.', 'hits': [SPIDER, WOLVERINE],
             'ref_images': ['spider.png', 'wolverine.png'],
             'rows': [{'file': 'spider.png', 'asset': SPIDER}, {'file': 'wolverine.png', 'asset': WOLVERINE}]},
        ]
        shots = [dict(id='a', mode='continue'), dict(id='b', mode='continue')]
        result = await ns['_queue_cinema_seamless'](
            body=body, parsed=shots, prompts=['Spider-Man lands.', 'Wolverine strikes Spider-Man.'],
            lib={'film_id': 'f'}, audio={}, cinema_batch='b', silent=False, purpose='short_film',
            reference_plans=plans, parent_job_ids=['root', None])
        job = result['jobs'][0]
        self.assertEqual(job['ref_images'], ['spider.png', 'wolverine.png'])
        self.assertEqual([r['asset']['name'] for r in job['reference_manifest']], ['Spider-Man', 'Wolverine'])

        job.update(continuation_source_key='x', h3_models={'vae': 'v', 'audio_vae': 'a'})
        graph = native_continuation.build(job)
        texts = [n['inputs']['prompt'] for k, n in graph.items() if k.endswith('_104')]
        self.assertIn('Spider-Man', texts[0])
        self.assertNotIn('Wolverine', texts[0].split('Spider-Man lands.')[-1])
        self.assertRegex(texts[1], r'<Picture 2>[^\n]*Wolverine')


class _AsyncNull:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


class CastUnboundLint(unittest.TestCase):
    def lib(self):
        return {'characters': [dict(SPIDER, images=[{'file': 'spider.png', 'name': 'spider'}]),
                               dict(WOLVERINE, images=[{'file': 'wolverine.png', 'name': 'wolverine'}])],
                'audio': {'mode': 'silent'}, 'shots': []}

    def codes(self, shot):
        return [(i['code'], i['params'].get('name')) for i in cinema.lint_shots([shot], self.lib())['issues']
                if i['code'] == 'cast_unbound']

    def test_named_actor_outside_explicit_selection_is_flagged(self):
        text = 'Wolverine slashes at Spider-Man on the wet rooftop while rain pours down in heavy sheets around them.'
        shot = {'id': '1', 'text': text, 'mode': 't2v', 'bindings': [{'asset_id': 's'}]}
        self.assertEqual(self.codes(shot), [('cast_unbound', 'Wolverine')])

    def test_automatic_matching_and_cast_field_are_not_flagged(self):
        text = 'Wolverine slashes at Spider-Man on the wet rooftop while rain pours down in heavy sheets around them.'
        self.assertEqual(self.codes({'id': '1', 'text': text, 'mode': 't2v'}), [])
        shot = {'id': '1', 'text': text, 'mode': 't2v', 'bindings': [{'asset_id': 's'}],
                'structured': {'character': 'Spider-Man, Wolverine'}}
        self.assertEqual(self.codes(shot), [])


if __name__ == '__main__':
    unittest.main()
