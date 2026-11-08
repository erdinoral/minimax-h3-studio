"""Repeat a recorded Director render without consulting the current film settings."""
import copy
import time
import uuid


# Output/cache state belongs to the original clip, never to its new attempt.
OUTPUT_KEYS = {
    'id', 'status', 'progress', 'progress_label', 'error', 'output', 'prompt_id',
    'local_path', 'last_frame_path', 'last_frame_url', 'last_frame_error', 'last_frame_upload_error', 'url', 'download_name', 'created_at',
    'started_at', 'done_at', 'render_sec', 'retried_at', 'retry_count',
    'cancel_requested_at', 'cancel_source', 'recovered_from_status', '_reattach',
    'comfy_step', 'comfy_step_max', 'progress_source', '_ws_progress_at',
    'render_control_token', 'render_control_ready', 'render_pause_requested',
    'render_paused', 'continuation_state_key', 'continuation_state_frames',
    'refine_state_key', 'reproduction_snapshot', 'sheet_attached',
    'audio_stripped', 'audio_strip_error', 'original_audio_applied', 'short_clip_trimmed',
    'queue_position',
}


def snapshot(job):
    return copy.deepcopy({k: v for k, v in job.items() if k not in OUTPUT_KEYS})


def recover_settings(source, graph):
    """Recover missing legacy provenance from its actual Comfy graph, never globals."""
    result = copy.deepcopy(source)
    if not graph:
        return result
    # After completion the old runner reused last_frame_name for its OUTPUT
    # frame. Recover the actual input guide from the original graph instead.
    last = graph.get('201', {})
    result['last_frame_name'] = last.get('inputs', {}).get('image') if last.get('class_type') == 'LoadImage' else None
    spectrum = next((n['inputs'] for n in graph.values() if n.get('class_type') == 'SpectrumApplyMiniMaxH3'), {})
    result.setdefault('acceleration_settings', {
        'spectrum_enabled': spectrum.get('enabled') is True,
        'spectrum_blend_weight': spectrum.get('blend_weight', .5),
        'spectrum_preset': 'custom',
        'sparse_enabled': any(n.get('class_type') == 'BlockSparseAttention' for n in graph.values()),
    })
    if not result.get('h3_models'):
        models = {}
        for key, kind, field in [('unet', 'UNETLoader', 'unet_name'), ('clip', 'CLIPLoader', 'clip_name')]:
            names = {n['inputs'][field] for n in graph.values() if n.get('class_type') == kind and field in n.get('inputs', {})}
            if len(names) == 1:
                models[key] = names.pop()
        # These are the native H3 builders' video/audio VAE nodes.
        for key, node_id in [('vae', '11'), ('audio_vae', '24')]:
            node = graph.get(node_id, graph.get('n0_' + node_id, {}))
            if node.get('class_type') == 'VAELoader':
                models[key] = node['inputs']['vae_name']
        if len(models) == 4:
            result['h3_models'] = models
    result.setdefault('refmod_enabled', any(n.get('class_type') == 'SkebaCachedMiniMaxH3ReferenceToVideo' for n in graph.values()))
    result.setdefault('save_continuation_tail', any(n.get('class_type') == 'H3StudioSaveContinuationTail' for n in graph.values()))
    return result


def clone(source):
    """One source render -> one fresh job. Never overwrite its completed video."""
    original = source.get('reproduction_snapshot') or source
    if source.get('status', 'done') not in ('done', 'error', 'cancelled'):
        raise ValueError('This scene is already queued or rendering.')
    if len(original.get('continuum_scene_ids') or []) > 1:
        raise ValueError('This older clip contains more than one scene; it cannot be repeated exactly as a single scene.')
    required = ('prompt', 'duration', 'width', 'height', 'seed', 'steps', 'sampler', 'scheduler', 'h3_models')
    if any(original.get(k) is None for k in required) or not original.get('prompt'):
        raise ValueError('The previous render has no settings record; it cannot be rendered again with the same settings.')
    if any(not (original.get('h3_models') or {}).get(k) for k in ('unet', 'clip', 'vae', 'audio_vae')):
        raise ValueError('The previous render has no model record; it was not swapped for the current models.')
    if original.get('mode') not in ('t2v', 'ref', 'face', 'continue', 'face_continue', 'continuum'):
        raise ValueError('This render type does not support repeating a single scene.')
    if not original.get('acceleration_settings'):
        raise ValueError('The older render did not save its acceleration settings; it cannot be repeated exactly.')
    job = snapshot(original)
    job.update(id=str(uuid.uuid4()), status='queued', progress=0,
               progress_label='queued again with the same settings', error=None, output=None,
               created_at=time.time(), reproduce_of=source['id'], lane='director',
               batch_index=1, batch_total=1, cinema_batch=str(uuid.uuid4())[:8])
    if job.get('continuum_run'):
        job['continuum_run'] = 'studio_' + uuid.uuid4().hex
    if job.get('director_chain_role') == 'new':
        job['director_root_id'] = job['id']
    # Pin the actual stack, including automatic continuation adapters.
    if 'effective_lora_name' in original:
        job['lora_name'] = original['effective_lora_name']
        job['lora_strength'] = copy.deepcopy(original.get('effective_lora_strength'))
    return job
