"""Local H3 two-pass output at the user's requested final dimensions.

Only newly submitted jobs opt in. Graph construction is CPU-only. GPU execution
and dependency validation remain owned by ComfyUI's ordinary job queue.
"""
from pathlib import Path

VERSION = 1
UPSCALER = 'minimax_h3_latent_upscaler_3d_bf16.safetensors'


def apply(graph, job):
    if job.get('local_quality_version') != VERSION or 'studio_quality_refine' in graph:
        return graph
    target_w, target_h = int(job['width']), int(job['height'])
    if min(target_w, target_h) <= 768 or job.get('fast_preview') or job.get('sheet_job'):
        return graph
    if job.get('continuation_source_key'):
        job['local_quality'] = {'enabled': False, 'reason': 'native_tail_uses_target_geometry'}
        return graph
    continuum = graph.get('c_sample')
    native = graph.get('14', {}).get('class_type') == 'SamplerCustomAdvanced'
    if not continuum and not native:
        job['local_quality'] = {'enabled': False, 'reason': 'custom_sampler_uses_target_geometry'}
        return graph
    model_file = Path(__file__).resolve().parents[2] / 'app/models/latent_upscale_models' / UPSCALER
    if not model_file.is_file():
        raise RuntimeError('Local H3 quality pass requires the installed 3D latent upscaler model')
    scale = 768 / min(target_w, target_h)
    base_w = max(32, round(target_w * scale / 32) * 32)
    base_h = max(32, round(target_h * scale / 32) * 32)
    job['local_quality'] = dict(enabled=True, version=VERSION, source_width=base_w,
                               source_height=base_h, target_width=target_w, target_height=target_h,
                               model=UPSCALER, audio='first_pass_locked', refine_steps=4,
                               refine_denoise=.15)
    # Keep the first pass and original audio intact. Reuse its prompt/reference
    # conditioning at target geometry rather than constructing a second brief.
    inputs = continuum['inputs'] if continuum else graph['104']['inputs']
    inputs.update(width=base_w, height=base_h)
    model = inputs['model'] if continuum else graph['16']['inputs']['model']
    sampler = inputs['sampler'] if continuum else graph['14']['inputs']['sampler']
    graph['studio_quality_sigmas'] = dict(class_type='BasicScheduler', inputs=dict(
        model=model, scheduler=job.get('scheduler') or 'simple', steps=4, denoise=.15))
    if continuum:
        # V39 publishes captured per-physical-group context on output 5.
        graph['studio_quality_upscale'] = dict(class_type='MinimaxH3LatentUpscaler3D', inputs={
            'latent': ['c_sample', 0], 'model_name': UPSCALER, 'mode': 'target dimensions',
            'mode.width': target_w, 'mode.height': target_h, 'align': 32,
            'keep_proportion': False, 'device': 'cuda', 'precision': 'bf16',
            'offload_after_upscale': True})
        graph['studio_quality_refine'] = dict(class_type='H3ContinuumSecondPassV35', inputs={
            'model': model, 'clip': inputs['clip'], 'sampler': sampler,
            'sigmas': ['studio_quality_sigmas', 0], 'video_latents': ['studio_quality_upscale', 0],
            'audio_latents': ['c_sample', 1], 'assembly_plan': ['c_sample', 2],
            'refine_context': ['c_sample', 5], 'video_vae': inputs['video_vae'],
            'refine_seed': int(job['seed'])})
        # Rewire both decode and seam assembly, including pre-decode offload
        # nodes. Never make the refinement depend on its own output.
        replacements = {('c_sample', 0): ['studio_quality_refine', 0],
                        ('c_sample', 1): ['studio_quality_refine', 1],
                        ('c_sample', 2): ['studio_quality_refine', 2]}
        for key, node in graph.items():
            if key.startswith('studio_quality_'):
                continue
            for name, value in node.get('inputs', {}).items():
                if isinstance(value, list) and len(value) == 2:
                    replacement = replacements.get(tuple(value))
                    if replacement:
                        node['inputs'][name] = replacement.copy()
    else:
        graph['studio_quality_noise'] = dict(class_type='RandomNoise', inputs={'noise_seed': int(job['seed'])})
        graph['studio_quality_refine'] = dict(class_type='MinimaxH3LatentUpscaler3DRefineHandoff', inputs={
            'latent': ['14', 0], 'noise': ['studio_quality_noise', 0], 'sampler': sampler,
            'sigmas': ['studio_quality_sigmas', 0], 'model_name': UPSCALER,
            'mode': 'target dimensions', 'scale': 1.5, 'width': target_w, 'height': target_h,
            'megapixels': target_w * target_h / 1048576, 'align': 32,
            'keep_proportion': False, 'lock_audio': True, 'cfg': 1.,
            'device': 'cuda', 'precision': 'bf16', 'offload_after_upscale': True,
            'model': model, 'positive': graph['16']['inputs']['conditioning']})
        for node in graph.values():
            if node.get('class_type') in ('VAEDecode', 'VAEDecodeTiled', 'H3TAEDecode', 'VAEDecodeAudio'):
                if node['inputs'].get('samples') == ['14', 0]:
                    node['inputs']['samples'] = ['studio_quality_refine', 0]
            elif node.get('class_type') == 'LTXVSeparateAVLatent':
                if node['inputs'].get('av_latent') == ['14', 0]:
                    node['inputs']['av_latent'] = ['studio_quality_refine', 0]
    # Bound final decode work spatially and temporally. Audio uses its own VAE.
    for node in graph.values():
        if node.get('class_type') == 'VAEDecode':
            node['class_type'] = 'VAEDecodeTiled'
            node['inputs'].update(tile_size=512, overlap=64,
                                  temporal_size=32, temporal_overlap=8)
    job['local_quality']['decode'] = 'tiled_512_frames32'
    return graph
