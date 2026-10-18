import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
import server
from lib.diagnostics import render_report


class ReportTests(unittest.IsolatedAsyncioTestCase):
    def test_report_excludes_prompts_reference_files_paths_and_credentials(self):
        job={'id':'x','status':'cancelled','prompt':'PRIVATE PROMPT', 'api_key':'SECRET',
             'local_path':'C:/private/movie.mp4','ref_images':['private-face.png'],
             'h3_models':{'unet':'C:/private/model.safetensors'},'cancel_source':'stop',
             'lora_name':'C:/private/style.safetensors'}
        report=render_report(job)
        encoded=json.dumps(report)
        for excluded in ('PRIVATE PROMPT','SECRET','C:/private','private-face.png'):
            self.assertNotIn(excluded, encoded)
        self.assertEqual(report['models']['unet'],'model.safetensors')
        self.assertEqual(report['job']['cancel_source'],'stop')
        self.assertFalse(report['engine']['history_available'])
        self.assertIsNone(report['engine']['completed'])

    async def test_endpoint_records_engine_success_without_modifying_explicit_cancellation(self):
        job={'id':'x','status':'cancelled','prompt_id':'p','cancel_requested_at':1}
        entry={'status':{'completed':True,'status_str':'success','messages':[['execution_success',{'private':'SECRET'}]]},'outputs':{'video':{}}}
        with patch.object(server,'_jobs',[job]), patch.object(server.comfy,'history',new_callable=AsyncMock,return_value={'p':entry}):
            response=await server.job_diagnostics('x')
        report=json.loads(response.body)
        self.assertTrue(report['engine']['completed'])
        self.assertEqual(report['job']['status'],'cancelled')
        self.assertEqual(job['status'],'cancelled')
        self.assertNotIn('SECRET',response.body.decode())
        self.assertIn('attachment',response.headers['content-disposition'])

    async def test_missing_history_does_not_infer_success_from_local_video(self):
        job={'id':'x','status':'done','prompt_id':'p','local_path':'movie.mp4'}
        with patch.object(server,'_jobs',[job]), patch.object(server.comfy,'history',new_callable=AsyncMock,side_effect=OSError('offline')):
            report=json.loads((await server.job_diagnostics('x')).body)
        self.assertFalse(report['engine']['history_available'])
        self.assertIsNone(report['engine']['completed'])
