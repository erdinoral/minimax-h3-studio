import ast
import unittest
from pathlib import Path
from typing import Any, Optional
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]

def function_from(file, name, env):
    tree=ast.parse((ROOT/file).read_text(encoding="utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),name,"exec"),env)
    return env[name]

class IndependentWeights(unittest.TestCase):
    def test_model_loaders_receive_different_weights_and_zero(self):
        apply=function_from("lib/comfy.py","apply_lora",dict(Any=Any,Optional=Optional,Path=Path))
        graph={"6":{"inputs":{}},"guider":{"inputs":{"model":["6",0]}}}
        apply(graph,"a.safetensors|b.safetensors|c.safetensors",{"a.safetensors":1.0,"b.safetensors":0.4,"c.safetensors":0.0})
        self.assertEqual([graph[n]["inputs"]["strength_model"] for n in ("7","lora_stack_2","lora_stack_3")],[1.0,0.4,0.0])
        self.assertEqual(graph["guider"]["inputs"]["model"],["lora_stack_3",0])
    def test_legacy_scalar_still_applies(self):
        apply=function_from("lib/comfy.py","apply_lora",dict(Any=Any,Optional=Optional,Path=Path))
        graph={"6":{"inputs":{}}}
        apply(graph,"a.safetensors|b.safetensors",0.6)
        self.assertEqual(graph["7"]["inputs"]["strength_model"],0.6)
        self.assertEqual(graph["lora_stack_2"]["inputs"]["strength_model"],0.6)
    def test_graph_filter_keeps_file_weight_association(self):
        lookup=lambda **kw: {"graphs":["ref2va"] if kw["file"]=="ref.safetensors" else ["fl2va"],"strength":0.8}
        select=function_from("server.py","_lora_for_graph",dict(Optional=Optional,find_spec=lookup,is_still_lora=lambda s:False,slog=SimpleNamespace(info=lambda *a,**k:None)))
        names, weights=select(dict(mode="t2v",lora_name="ref.safetensors|actor.safetensors",lora_strength=.7,lora_strengths={"ref.safetensors":1.0,"actor.safetensors":0.0}))
        self.assertEqual(names,"actor.safetensors")
        self.assertEqual(weights,{"actor.safetensors":0.0})
