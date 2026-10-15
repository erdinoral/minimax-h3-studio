"""Pinned Continuum graph contract; native AV chunks, no MP4 last-frame chaining."""
import json
import copy
import re
from pathlib import Path
from .comfy import build_t2v_prompt

SAMPLER = 'H3ContinuumSamplerV39'
SCHEMA = json.loads(Path(__file__).with_name('continuum_schema.json').read_text(encoding='utf-8'))

def extend_prompts(previous, new_prompts, context=''):
    if not new_prompts or any(not str(p).strip() for p in new_prompts):
        raise ValueError('Each Continuum section needs a non-empty prompt')
    if len(previous) + len(new_prompts) > 16:
        raise ValueError('Continuum supports at most 16 chunks per run')
    context = str(context or '').strip()
    if any(line.strip() == '---' for value in [context, *new_prompts] for line in str(value).splitlines()):
        raise ValueError('Use separate section cards instead of --- separators inside a prompt')
    additions = [f"{context}\n\n{str(p).strip()}" if context else str(p).strip() for p in new_prompts]
    return list(previous) + additions


def reference_plan(bindings):
    refs=[]; assignments={}
    for chunk,bound in enumerate(bindings,1):
        for name in bound.get('ref_images') or []:
            if name not in refs:
                refs.append(name)
            assignments.setdefault(name,[])
            if chunk not in assignments[name]: assignments[name].append(chunk)
    if len(refs)>9:
        raise ValueError('A Continuum take supports at most 9 distinct reference images')
    return refs,assignments


def align_reference_labels(text, section_refs, take_refs):
    active=[name for name in take_refs if name in section_refs]
    mapping={i+1:active.index(name)+1 for i,name in enumerate(section_refs)}
    return re.sub(r'<Picture\s+(\d+)>',lambda m:f"<Picture {mapping.get(int(m.group(1)),int(m.group(1)))}>",text)


def has_spectrum(graph):
    return any(n.get('class_type') == 'SpectrumApplyMiniMaxH3' for n in graph.values())


def remove_spectrum(graph):
    # Continuum storage cannot observe Spectrum's mutable runtime binding.
    # Keep native sampling and safe prefix reuse rather than rerendering old chunks.
    for key in list(graph):
        node=graph[key]
        if node.get('class_type') != 'SpectrumApplyMiniMaxH3':
            continue
        source=node['inputs']['model']
        for other in graph.values():
            for name,value in other.get('inputs',{}).items():
                if value == [key,0]:
                    other['inputs'][name]=copy.deepcopy(source)
        del graph[key]
    return graph


def build(job):
    prompts = job.get('continuum_prompts') or [job['prompt']]
    duration = int(job.get('continuum_chunk_seconds') or job['duration'])
    if not 1 <= len(prompts) <= 16:
        raise ValueError('Continuum supports 1–16 chunks per run')
    if not 4 <= duration <= 15:
        raise ValueError('Continuum supports 4–15 second chunks in Studio')
    graph = build_t2v_prompt(text='', width=job['width'], height=job['height'], length=124,
                            seed=job['seed'], steps=job['steps'], models=job['h3_models'],
                            sampler=job.get('sampler') or 'res_multistep',
                            scheduler=job.get('scheduler') or 'simple', sage_attention='disabled',
                            lora_name=job.get('lora_name'), lora_strength=job.get('lora_strength') or 0.75)
    # Preserve the user's acceleration choice for new runs. Spectrum's mutable
    # binding cannot safely participate in persisted prefix reuse (see below).
    # Retain the already-patched native model branch and scheduler.
    model = graph['16']['inputs']['model']
    sigmas = graph['14']['inputs']['sigmas']
    keep = set()
    def visit(key):
        if key in keep: return
        keep.add(key)
        for value in graph[key]['inputs'].values():
            if isinstance(value,list) and len(value)==2 and str(value[0]) in graph:
                visit(str(value[0]))
    for key in (model[0],sigmas[0],'13','11','24','17'): visit(key)
    graph = {k:v for k,v in graph.items() if k in keep}
    if job.get('continuum_base_graph'):
        if has_spectrum(job['continuum_base_graph']):
            raise ValueError('Legacy Spectrum Continuum run cannot be safely resumed; start a new Continuum run')
        graph = copy.deepcopy(job['continuum_base_graph'])
        model = job['continuum_model_link']
        sigmas = job['continuum_sigma_link']
    else:
        job['continuum_base_graph'] = copy.deepcopy(graph)
        job['continuum_model_link'] = model
        job['continuum_sigma_link'] = sigmas
    inputs = {}
    for key, spec in SCHEMA['inputs']['required'].items():
        if len(spec) > 1 and 'default' in spec[1]:
            inputs[key] = spec[1]['default']
    inputs.update(model=model, clip=['13',0], video_vae=['11',0], sampler=['17',0], sigmas=sigmas,
                  sequence_prompt='\n---\n'.join(prompts), prompt_mode='List',
                  chunks=len(prompts), chunk_seconds=duration, base_seed=job['seed'],
                  size_source='Manual', width=job['width'], height=job['height'],
                  run_storage='Off' if has_spectrum(graph) else 'Save + Auto Resume', run_name=job['continuum_run'],
                  project_id=job['continuum_run'], generation_mode='Full Run',
                  audio_continuity=not job.get('silent_audio',False),
                  reference_size=job.setdefault('continuum_reference_size','Max Identity'),
                  continuity=('Strong — 39 frames (Experimental)' if job.get('continuum_continuity')=='strong' else 'Balanced — 22 frames'))
    if job.get('first_frame_name'):
        graph['c_first']=dict(class_type='LoadImage',inputs={'image':job['first_frame_name']})
        inputs['first_frame']=['c_first',0]
    refs=job.get('ref_images') or []
    if refs:
        assignments=job.get('continuum_ref_assignments')
        ri={'reference_use':'Per chunk' if assignments else 'All chunks', **{f'reference_r{i}_chunks':'off' for i in range(1,10)}}
        for i, name in enumerate(refs[:9],1):
            graph[f'c_ref{i}']=dict(class_type='LoadImage',inputs={'image':name})
            ri[f'reference_image_{i}']=[f'c_ref{i}',0]
            if assignments:
                ri[f'reference_r{i}_chunks']=','.join(str(n) for n in assignments.get(name,[])) or 'off'
        graph['c_refs']=dict(class_type='H3ContinuumReferenceImagesV39',inputs=ri)
        inputs['reference_images']=['c_refs',0]
    graph['c_sample']=dict(class_type=SAMPLER,inputs=inputs)
    graph['c_video']=dict(class_type='VAEDecode',inputs={'samples':['c_sample',0],'vae':['11',0]})
    graph['c_audio']=dict(class_type='VAEDecodeAudio',inputs={'samples':['c_sample',1],'vae':['24',0]})
    graph['c_finish']=dict(class_type='H3ContinuumAssembleSeamV35',inputs={
        'images':['c_video',0],'audio':['c_audio',0],'assembly_plan':['c_sample',2],
        'exact_total_duration':True,'audio_seam':'Auto','video_seam':'Analyze Only',
        'buffer_backend':'Auto','diagnostics':'Basic'})
    graph['91']=dict(class_type='CreateVideo',inputs={'images':['c_finish',0],'audio':['c_finish',1],'fps':24})
    graph['92']=dict(class_type='SaveVideo',inputs={'video':['91',0],
        'filename_prefix':f"video/H3_Studio/{job['id'][:8]}",'format':'auto','codec':'auto'})
    return graph
