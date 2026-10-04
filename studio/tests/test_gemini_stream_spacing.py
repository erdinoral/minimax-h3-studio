import ast
import json
import unittest
from pathlib import Path

source=ast.parse((Path(__file__).parents[1]/"lib"/"llm.py").read_text(encoding="utf-8"))
method=next(node for node in ast.walk(source) if isinstance(node,ast.FunctionDef) and node.name=="_gemini_chunk_parts")
method.decorator_list=[]
from typing import Any
namespace={"Any":Any}
exec(compile(ast.Module(body=[method],type_ignores=[]),"gemini_spacing","exec"),namespace)
parts=namespace["_gemini_chunk_parts"]

def chunk(text,thought=False):return {"candidates":[{"content":{"parts":[{"text":text,"thought":thought}]}}]}

class StreamSpacing(unittest.TestCase):
    def test_scene_asset_name_survives_delta_boundaries(self):
        deltas=['{"location":"Abandoned', ' ', 'Metro ', 'Station", "action":"NEA ', 'turns her head."}']
        value=json.loads(''.join(parts(chunk(delta))[1] for delta in deltas))
        self.assertEqual(value["location"],"Abandoned Metro Station")
        self.assertEqual(value["action"],"NEA turns her head.")
    def test_thoughts_do_not_enter_json_answer(self):
        data=chunk('thinking ',True)
        data['candidates'][0]['content']['parts'].append({'text':' {"ok":true} ','thought':False})
        thought,answer=parts(data)
        self.assertEqual(thought,'thinking ')
        self.assertEqual(answer,' {"ok":true} ')
