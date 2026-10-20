"""Normal Director sampling plus bounded, native Continuum AV-tail handoff."""
import copy
import re
from pathlib import Path
from .comfy import build_t2v_prompt, build_ref2va_prompt

REQUIRED_NODES = ('H3StudioSaveContinuationTail', 'H3StudioLoadContinuationTail',
                  'H3StudioNativeJoin', 'H3StudioNativeFinish', 'H3StudioSaveContinuationResult',
                  'H3StudioAppendContinuationAV', 'H3StudioContinuationWindow')


def state_path(comfy_root, key):
    if not re.fullmatch(r'[0-9a-f-]{36}', str(key)):
        raise ValueError('Invalid continuation state key')
    return Path(comfy_root) / 'output' / 'h3_continuum_states' / ('studio_' + key + '_slot0001.safetensors')


def capture(graph, job, frames):
    if '14' not in graph:
        raise ValueError('Native tail capture requires a normal H3 sampler')
    graph['studio_tail'] = {'class_type': 'H3StudioSaveContinuationTail', 'inputs': {
        'samples': ['14', 0], 'key': job['id'], 'frames': frames}}
    for key, node in graph.items():
        if key == 'studio_tail': continue
        if node.get('class_type') in ('VAEDecode', 'VAEDecodeAudio', 'H3TAEDecode', 'VAEDecodeTiled'):
            if node['inputs'].get('samples') == ['14', 0]:
                node['inputs']['samples'] = ['studio_tail', 0]
    job['continuation_state_key'] = job['id']
    job['continuation_state_frames'] = 39
    return graph


def prepare(job, parent, comfy_root):
    """A declared state must exist and match; never silently degrade a new chain."""
    key = (parent or {}).get('continuation_state_key')
    if not key: return False  # Explicit legacy last-frame fallback only.
    if parent.get('status', 'done') != 'done':
        raise ValueError('Native continuation parent is not finished')
    if not state_path(comfy_root, key).is_file():
        raise ValueError('Native continuation state is missing; regenerate the New clip to restore it')
    if (job['width'], job['height']) != (parent['width'], parent['height']):
        raise ValueError('Native continuation must keep its parent resolution')
    if (job.get('h3_models') or {}).get('vae') != (parent.get('h3_models') or {}).get('vae'):
        raise ValueError('Native continuation must keep its parent video VAE')
    if (job.get('h3_models') or {}).get('audio_vae') != (parent.get('h3_models') or {}).get('audio_vae'):
        raise ValueError('Native continuation must keep its parent audio VAE')
    job.update(continuation_source_key=key, first_frame_name=None,
               continuity_method='native_latent_tail', continuation_context_frames=22)
    return True


def build(job):
    prompts = job.get('continuum_prompts') or [job['prompt']]
    if not 1 <= len(prompts) <= 16: raise ValueError('Native continuation supports 1–16 sections')
    if not 4 <= job['duration'] <= 15: raise ValueError('Native continuation needs 4–15 second sections')
    graph = {'tail_load': {'class_type': 'H3StudioLoadContinuationTail',
                           'inputs': {'key': job['continuation_source_key']}}}
    state = ['tail_load', 0]
    clips = None
    refs = job.get('ref_images') or []
    assignments = job.get('continuum_ref_assignments')
    context = int(job.get('continuation_context_frames') or 22)
    for index, text in enumerate(prompts):
        active = [name for name in refs if not assignments or index + 1 in assignments.get(name, [])]
        def reference(match):
            number = int(match.group(1))
            if not 1 <= number <= len(refs) or refs[number - 1] not in active:
                raise ValueError('Continuation prompt refers to an unassigned reference')
            return '<Picture ' + str(active.index(refs[number - 1]) + 1) + '>'
        text = re.sub(r'@R(\d+)\b', reference, text)
        kwargs = dict(text=text, width=job['width'], height=job['height'], length=124,
                      seed=int(job['seed']) + index, steps=job['steps'],
                      sampler=job.get('sampler') or 'res_multistep', scheduler=job.get('scheduler') or 'simple',
                      models=job['h3_models'], silent_audio=False, sage_attention='disabled',
                      lora_name=job.get('lora_name'), lora_strength=job.get('lora_strength') or 0.75)
        local = (build_ref2va_prompt(**kwargs, ref_image_names=active)
                 if active else build_t2v_prompt(**kwargs))
        local.pop('91', None); local.pop('92', None)
        local['window'] = {'class_type': 'H3StudioContinuationWindow', 'inputs': {
            'context_frames': context, 'seconds': job['duration']}}
        local['104']['inputs']['length'] = ['window', 0]
        local['join'] = {'class_type': 'H3StudioNativeJoin', 'inputs': {
            'model': copy.deepcopy(local['16']['inputs']['model']),
            'conditioning': ['104', 0], 'latent': ['104', 1],
            'continuity': 'Balanced — 22 frames' if context == 22 else 'Strong — 39 frames (Experimental)',
            'extend_seconds': job['duration'], 'audio_continuity': not job.get('silent_audio', False),
            'first_frame_policy': 'Use Continuum context; keep visual identity tokens (Recommended)',
            'preserve_last_frame': False, 'strict_compatibility': True, 'debug': False}}
        local['16']['inputs'].update(model=['join', 0], conditioning=['join', 1])
        local['14']['inputs']['latent_image'] = ['join', 2]
        local['9']['inputs']['model'] = ['join', 0]
        local['finish'] = {'class_type': 'H3StudioNativeFinish', 'inputs': {
            'samples': ['14', 0], 'images': ['10', 0], 'audio': ['23', 0], 'plan': ['join', 3]}}
        prefix = 'n' + str(index) + '_'
        for key, node in local.items():
            node = copy.deepcopy(node)
            for name, value in node['inputs'].items():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) in local:
                    node['inputs'][name] = [prefix + str(value[0]), value[1]]
            graph[prefix + key] = node
        graph[prefix + 'join']['inputs']['previous_state'] = state
        state = [prefix + 'finish', 2]
        graph[prefix + 'append'] = {'class_type': 'H3StudioAppendContinuationAV', 'inputs': {
            'images': [prefix + 'finish', 0], 'audio': [prefix + 'finish', 1]}}
        if clips: graph[prefix + 'append']['inputs']['previous'] = clips
        clips = [prefix + 'append', 0]
    graph['tail_save'] = {'class_type': 'H3StudioSaveContinuationResult', 'inputs': {
        'state': state, 'clips': clips, 'key': job['id']}}
    graph['91'] = {'class_type': 'CreateVideo', 'inputs': {'images': ['tail_save', 0], 'fps': 24}}
    if not job.get('silent_audio'): graph['91']['inputs']['audio'] = ['tail_save', 1]
    graph['92'] = {'class_type': 'SaveVideo', 'inputs': {'video': ['91', 0],
        'filename_prefix': 'video/H3_Studio/' + job['id'][:8], 'format': 'auto', 'codec': 'auto'}}
    job.update(continuity_method='native_latent_tail', native_context_chunks=len(prompts),
               continuation_state_key=job['id'], continuation_state_frames=39)
    return graph
