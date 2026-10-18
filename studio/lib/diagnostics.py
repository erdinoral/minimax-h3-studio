"""Minimal shareable render evidence, excluding prompts, paths and secrets."""
def basename(value):
    return str(value or '').replace('\\', '/').rsplit('/', 1)[-1]


def render_report(job, entry=None):
    fields = ('id','status','mode','width','height','duration','steps','seed','sampler','scheduler',
              'created_at','started_at','done_at','prompt_id','cancel_requested_at','cancel_source',
              'recovered_from_status','effective_spectrum','native_context_chunks','continuity_method',
              'continuum_chunk_seconds','continuum_reference_size','continuum_grouping')
    status = (entry or {}).get('status') or {}
    return {'schema':'h3-studio-render-diagnostics/v1',
            'job':{key:job[key] for key in fields if key in job},
            'models':{key:basename(value) for key,value in (job.get('h3_models') or {}).items()},
            'loras':[basename(name) for name in str(job.get('effective_lora_name') or job.get('lora_name') or '').split('|') if name],
            'reference_count':len(job.get('ref_images') or []),
            'has_starting_image':bool(job.get('first_frame_name')),
            'local_video_recorded':bool(job.get('local_path')),
            'engine':{'history_available':entry is not None,
                      'completed':status.get('completed'), 'status':status.get('status_str'),
                      'events':[str(m[0]) for m in status.get('messages',[]) if isinstance(m,(list,tuple)) and m],
                      'output_node_count':len((entry or {}).get('outputs') or {})},
            'privacy':'No prompt text, reference images, local paths, API keys or raw logs included.'}
