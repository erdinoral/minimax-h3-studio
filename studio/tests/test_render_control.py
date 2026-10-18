import asyncio
import copy
import importlib.util
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import server
from lib import render_control

spec = importlib.util.spec_from_file_location('sampling_gate_tests', Path(__file__).resolve().parents[1] / 'comfy_nodes/h3_studio_render_control/control.py')
gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gates)


class GateTests(unittest.TestCase):
    def test_pause_acknowledges_only_at_checkpoint_and_resumes_same_execution(self):
        gate = gates.SamplingGate()
        output = []
        gate.request(True)
        self.assertFalse(gate.state()['paused'])
        worker = threading.Thread(target=lambda: (gate.checkpoint(lambda: None), output.append('same execution')))
        worker.start()
        try:
            deadline = time.monotonic() + 2
            while not gate.state()['paused'] and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(gate.state()['paused'])
            self.assertEqual(output, [])
        finally:
            gate.request(False)
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output, ['same execution'])

    def test_expired_controller_lease_fails_open(self):
        clock = [0.0]
        gate = gates.SamplingGate(clock=lambda: clock[0])
        gate.request(True)
        clock[0] = 31
        gate.checkpoint(lambda: self.fail('expired pause should not wait'))
        self.assertFalse(gate.state()['requested'])

    def test_stop_is_checked_during_pause_and_wait_state_is_cleared(self):
        gate = gates.SamplingGate()
        gate.request(True)
        def stop():
            raise RuntimeError('engine interrupted')
        with self.assertRaisesRegex(RuntimeError, 'engine interrupted'):
            gate.checkpoint(stop)
        self.assertFalse(gate.state()['paused'])

    def test_job_tokens_do_not_share_pause_state(self):
        a, b = gates.gate_for('a'), gates.gate_for('b')
        a.request(True)
        self.assertFalse(b.state()['requested'])
        a.request(False)


class GraphTests(unittest.TestCase):
    def test_pause_support_detection_does_not_change_native_cache_contract_or_seed(self):
        graph = {'1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'x'}},
                 '2': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['1', 0]}},
                 '3': {'class_type': 'BasicGuider', 'inputs': {'model': ['2', 0]}},
                 '4': {'class_type': 'BasicScheduler', 'inputs': {'model': ['2', 0]}},
                 '5': {'class_type': 'H3ContinuumSamplerV39', 'inputs': {'model': ['2', 0], 'base_seed': 42}}}
        original = copy.deepcopy(graph)
        self.assertTrue(render_control.supports_graph(graph))
        self.assertEqual(graph, original)


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_only_targets_the_requested_running_job_and_preserves_status(self):
        a = {'id': 'a', 'status': 'running', 'render_control_token': 'a-token', 'render_control_ready': True}
        b = {'id': 'b', 'status': 'queued'}
        with patch.object(server, '_jobs', [a,b]), patch.object(server, '_lock', asyncio.Lock()), patch.object(server, '_save_jobs'), patch.object(render_control, 'command', new_callable=AsyncMock, return_value={'requested':True,'paused':False}) as call:
            result = await server.pause_render('a', server.QueuePauseBody(paused=True))
            self.assertEqual(result['status'], 'running')
            self.assertFalse(result['render_paused'])
            self.assertTrue(result['render_pause_requested'])
            call.assert_awaited_once_with(server.COMFY_URL, 'a-token', True)
            with self.assertRaises(server.HTTPException):
                await server.pause_render('b', server.QueuePauseBody(paused=True))
            self.assertEqual(b['status'], 'queued')

    async def test_completion_wins_pause_request_race(self):
        job = {'id':'a','status':'running','render_control_token':'token','render_control_ready':True}
        async def completed(*args):
            job['status'] = 'done'
            return {'requested':True,'paused':False}
        with patch.object(server, '_jobs', [job]), patch.object(server, '_lock', asyncio.Lock()), patch.object(render_control, 'command', side_effect=completed):
            result = await server.pause_render('a', server.QueuePauseBody(paused=True))
        self.assertEqual(result['status'], 'done')
        self.assertNotIn('render_pause_requested', result)

    async def test_expired_engine_pause_clears_stale_ui_state_instead_of_repausing(self):
        job = {'id':'a','status':'running','render_control_token':'token','render_pause_requested':True}
        with patch.object(server, '_lock', asyncio.Lock()), patch.object(render_control, 'command', new_callable=AsyncMock, return_value={'requested':False,'paused':False}) as call:
            await server._sync_render_pause(job)
            self.assertFalse(job['render_pause_requested'])
            self.assertEqual(call.await_count, 1)


if __name__ == '__main__':
    unittest.main()
