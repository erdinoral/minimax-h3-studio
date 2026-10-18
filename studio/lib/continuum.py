"""Native AV context within a run; explicit last-frame handoff across Director runs."""
import json
import copy
import re
from pathlib import Path
from .comfy import build_t2v_prompt

SAMPLER = 'H3ContinuumSamplerV39'
SCHEMA = json.loads(Path(__file__).with_name('continuum_schema.json').read_text(encoding='utf-8'))

def director_takes(shots, prompts, pack=16):
    """Keep JSON story order; cuts/take boundaries start a separate sampler run."""
    if len(shots) != len(prompts) or any(not str(p).strip() for p in prompts):
        raise ValueError('Each Director scene needs its own non-empty Continuum prompt')
    groups = []
    rows, texts = [], []
    for shot, prompt in zip(shots, prompts):
        cut = shot.get('mode') == 't2v'
        take_changed = rows and shot.get('take_index') != rows[-1].get('take_index')
        if rows and (cut or take_changed or len(rows) >= pack):
            groups.append((rows, texts))
            rows, texts = [], []
        rows.append(shot)
        texts.append(prompt)
    if rows:
        groups.append((rows, texts))
    return groups


async def prepare_director_handoff(job, resolve_first_frame):
    """Independent Continuum runs need an explicit visual handoff to continue."""
    if job.get('mode') != 'continuum' or not job.get('continue_from'):
        return
    if job.get('continuum_resume'):
        # Saved-prefix continuation must retain its original keyframe. Replacing
        # it with the parent MP4's last frame changes the native run contract.
        return
    first = await resolve_first_frame(job)
    if not first:
        raise RuntimeError('Continuum continuation requires the previous clip last frame')
    job['first_frame_name'] = first

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
    """Map section-local references to fixed V39 slots, not Qwen pictures.

    First/last frames and each chunk's active reference subset change Picture
    numbering. The native sampler resolves @R slots after those inputs exist.
    """
    mapping={i+1:take_refs.index(name)+1 for i,name in enumerate(section_refs)}
    def replace(match):
        number=int(match.group(1) or match.group(2))
        return f'@R{mapping[number]}' if number in mapping else match.group(0)
    return re.sub(r'<Picture\s+(\d+)>|@R(\d+)\b',replace,text)


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
    job['native_context_chunks'] = len(prompts)
    job['continuity_method'] = ('native_prefix' if job.get('continuum_resume')
                                else 'last_frame_handoff' if job.get('continue_from')
                                else 'first_frame' if job.get('first_frame_name') else 'new_shot')
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
                  sequence_prompt=json.dumps(prompts, ensure_ascii=False), prompt_mode='List',
                  chunks=len(prompts), chunk_seconds=duration, base_seed=job['seed'],
                  size_source='Manual', width=job['width'], height=job['height'],
                  run_storage='Off' if has_spectrum(graph) else 'Save + Auto Resume', run_name=job['continuum_run'],
                  project_id=job['continuum_run'], generation_mode='Full Run',
                  audio_continuity=not job.get('silent_audio',False),
                  reference_size=job.setdefault('continuum_reference_size','Match Output'),
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
