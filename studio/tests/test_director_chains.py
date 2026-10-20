import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException
from lib import continuum


class DirectorChains(unittest.IsolatedAsyncioTestCase):
    def environment(self):
        tree = ast.parse((Path(__file__).parents[1] / 'server.py').read_text(encoding='utf-8'))
        names = {'BatchBody', 'CinemaProduceBody', '_queue_director_chains',
                 '_cinema_previous_clip', '_cinema_shot_already_produced'}
        nodes = [n for n in tree.body if getattr(n, 'name', '') in names]
        calls = []
        async def batch(body):
            calls.append(('normal', body))
            return {'jobs': [dict(id='new-' + str(len(calls)), mode='ref', status='queued')]}
        async def seamless(**kw):
            calls.append(('continuum', kw))
            return {'jobs': [dict(id='cont-' + str(len(calls)), mode='continuum', status='queued',
                                  continue_from=kw['parent_job_ids'][0], shot_id=kw['parsed'][0]['id'],
                                  shot_index=1, continuum_scene_ids=[s['id'] for s in kw['parsed']])]}
        async def capabilities(): return {'continuum_ready': True, 'native_tail_ready': True}
        ns = dict(BaseModel=BaseModel, Field=Field, field_validator=field_validator,
                  Any=Any, Optional=Optional, Literal=Literal, HTTPException=HTTPException,
                  continuum=continuum, batch=batch, _queue_cinema_seamless=seamless,
                  workflow_capabilities=capabilities, _sage_mode=lambda b: 'disabled',
                  cinema=SimpleNamespace(uses_lora=lambda a: bool(a.get('use_lora'))),
                  _clip_record=lambda id: {'id': id, 'director_root_id': 'old-root'},
                  _save_jobs=lambda: None, _jobs=[], _gallery=[])
        ns['normalize_quality'] = lambda value: value
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'director-chains', 'exec'), ns)
        return ns, calls

    async def queue(self, shots, parents=None, plans=None):
        ns, calls = self.environment()
        result = await ns['_queue_director_chains'](
            body=ns['CinemaProduceBody'](quality='480', steps=18), parsed=shots,
            prompts=[s['id'] for s in shots], lib={'film_id': 'film', 'shots': shots},
            audio={}, cinema_batch='batch', silent=False, purpose='short_film',
            reference_plans=plans or [{'hits': [], 'ref_images': []} for s in shots],
            parent_job_ids=parents or [None] * len(shots))
        return ns, calls, result

    async def test_new_is_normal_and_only_following_continues_use_continuum(self):
        shots = [dict(id=str(i), mode=m, text='Action') for i, m in enumerate(['t2v', 'continue', 'continue', 't2v', 'continue'])]
        ns, calls, result = await self.queue(shots)
        self.assertEqual([c[0] for c in calls], ['normal', 'continuum', 'normal', 'continuum'])
        root, child, other, second = result['jobs']
        self.assertEqual(child['continue_from'], root['id'])
        self.assertEqual(child['director_parent_id'], root['id'])
        self.assertEqual(second['director_parent_id'], other['id'])
        self.assertEqual(calls[1][1]['prompts'], ['1', '2'])
        self.assertEqual(calls[0][1].steps, 18)
        self.assertTrue(root['save_continuation_tail'])
        self.assertEqual(calls[1][1]['body'].continuum_max_chunks, 2)
        self.assertEqual([j['batch_index'] for j in result['jobs']], [1, 2, 3, 4])
        ns['_jobs'] = result['jobs']
        self.assertTrue(ns['_cinema_shot_already_produced'](shots[2]))
        self.assertEqual(ns['_cinema_previous_clip'](shots, '3'), child['id'])
        with self.assertRaises(HTTPException) as rejected:
            ns['_cinema_previous_clip'](shots, '2')
        self.assertEqual(rejected.exception.status_code, 409)

    async def test_continue_only_attaches_to_existing_root(self):
        _, calls, result = await self.queue([dict(id='next', mode='continue')], parents=['previous'])
        child = result['jobs'][0]
        self.assertEqual(child['continue_from'], 'previous')
        self.assertEqual(child['director_parent_id'], 'old-root')
        self.assertEqual(len(calls), 1)

    async def test_invalid_continuation_is_rejected_before_any_root_is_queued(self):
        ns, calls = self.environment()
        shots = [dict(id='new', mode='t2v'), dict(id='bad', mode='continue', first_frame_name='wrong.png')]
        with self.assertRaises(HTTPException):
            await ns['_queue_director_chains'](
                body=ns['CinemaProduceBody'](), parsed=shots, prompts=['new', 'bad'],
                lib={}, audio={}, cinema_batch='b', silent=True, purpose='',
                reference_plans=[{}, {}], parent_job_ids=[None, None])
        self.assertEqual(calls, [])

    def test_chapters_split_continuation_context_without_dropping_prompts(self):
        shots = [dict(id='a', mode='t2v', chapter='One'), dict(id='b', mode='continue', chapter='One'),
                 dict(id='c', mode='continue', chapter='Two')]
        groups = continuum.director_chain_groups(shots, ['A', 'B', 'C'])
        self.assertEqual([g['prompts'] for g in groups], [['A'], ['B'], ['C']])
