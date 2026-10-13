"""Studio-owned durable Flow state. Load only local UUID-keyed tensor records."""
import importlib
import re
from dataclasses import asdict
from pathlib import Path

import folder_paths
import nodes
import torch
from comfy.nested_tensor import NestedTensor


def state_path(key):
    if not re.fullmatch(r'[0-9a-f-]{36}', key):
        raise ValueError('Invalid Studio state identifier')
    folder = Path(folder_paths.get_output_directory()) / 'H3_Studio_Flow'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (key + '.pt')


class H3StudioSaveFlowState:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'samples': ('LATENT',), 'trajectory': ('H3_FLOW_TRAJECTORY',),
                             'key': ('STRING',)}}
    RETURN_TYPES = ('LATENT',)
    FUNCTION = 'save'
    CATEGORY = 'H3 Studio/refine'

    def save(self, samples, trajectory, key):
        run = trajectory.latest
        if not run.complete:
            raise ValueError('Cannot save incomplete Flow state')
        # Primitive metadata and CPU tensors, never serialized Python objects.
        data = asdict(run)
        for sample in data['samples']:
            sample['video_x0'] = sample['video_x0'].detach().cpu()
        tensors = samples['samples'].unbind()
        target = state_path(key)
        temporary = target.with_suffix('.tmp')
        try:
            torch.save({'version': 1, 'run': data,
                        'latent': [t.detach().cpu() for t in tensors]}, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return (samples,)


class H3StudioLoadFlowState:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'key': ('STRING',), 'width': ('INT', {'min':32, 'step':32}),
                             'height': ('INT', {'min':32, 'step':32}),
                             'learned_upscaler': ('H3_LATENT_UPSCALER',)}}
    RETURN_TYPES = ('H3_FLOW_TRAJECTORY', 'LATENT')
    FUNCTION = 'load'
    CATEGORY = 'H3 Studio/refine'

    def load(self, key, width, height, learned_upscaler):
        capture = nodes.NODE_CLASS_MAPPINGS['H3TrajectoryCapture']
        package = capture.__module__.rsplit('.', 1)[0]
        contracts = importlib.import_module(package + '.contracts')
        geometry = importlib.import_module(package + '.geometry')
        data = torch.load(state_path(key), map_location='cpu', weights_only=True)
        if data['version'] != 1:
            raise ValueError('Unsupported Flow state version')
        run = data['run']
        run['geometry'] = geometry.H3Geometry(**run['geometry'])
        run['samples'] = tuple(contracts.TrajectorySample(**s) for s in run['samples'])
        trajectory = contracts.H3FlowTrajectory(storage='system_ram', max_runs=1)
        trajectory._runs = (contracts.TrajectoryRun(**run),)
        video, audio = data['latent']
        # The H3-trained provider owns normalization, precision and offloading.
        video = learned_upscaler.upscale_clean_video(video, target_h=height // 16, target_w=width // 16)
        return trajectory, {'samples': NestedTensor((video, audio)),
                            'noise_mask': NestedTensor((torch.ones_like(video),torch.zeros_like(audio)))}


NODE_CLASS_MAPPINGS = {'H3StudioSaveFlowState': H3StudioSaveFlowState,
                       'H3StudioLoadFlowState': H3StudioLoadFlowState}
