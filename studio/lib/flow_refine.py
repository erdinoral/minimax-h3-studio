"""Flow capture/refinement graphs; only recorded native single-clip jobs qualify."""
import copy
import json
from pathlib import Path

STORE = Path(__file__).resolve().parents[1] / 'data' / 'flow_graphs'


def without_spectrum(graph):
    """Use actual model evaluations for Flow's durable trajectory contract.

    Spectrum 0.2.29 does not supply the complete active-step provenance required
    by the installed Flow runtime. Do not invent provenance or disable its guard.
    Global acceleration settings and ordinary generation graphs are untouched.
    """
    for key, node in list(graph.items()):
        if node.get('class_type') != 'SpectrumApplyMiniMaxH3':
            continue
        source = node['inputs']['model']
        for consumer in graph.values():
            for name, value in consumer.get('inputs', {}).items():
                if value == [key, 0]:
                    consumer['inputs'][name] = copy.deepcopy(source)
        del graph[key]
    return graph


def capture(graph, job):
    if '14' not in graph or '16' not in graph:
        raise ValueError('Flow recording requires a native single-clip sampler')
    without_spectrum(graph)
    STORE.mkdir(parents=True, exist_ok=True)
    target = STORE / (job['id'] + '.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(graph), encoding='utf-8')
    temporary.replace(target)
    model = graph['16']['inputs']['model']
    graph['flow_handle'] = {'class_type':'H3FlowTrajectory', 'inputs':{'storage':'system_ram','max_runs':1}}
    graph['flow_capture'] = {'class_type':'H3TrajectoryCapture', 'inputs':{
        'model':model,'trajectory':['flow_handle',0],'capture_forecasts':False}}
    graph['16']['inputs']['model'] = ['flow_capture',0]
    # Decoder dependency makes state saving occur after the complete sampler.
    for node in graph.values():
        if node['class_type'] in ('VAEDecode', 'VAEDecodeAudio', 'H3TAEDecode'):
            if node['inputs'].get('samples') == ['14',0]:
                node['inputs']['samples'] = ['flow_save',0]
    graph['flow_save'] = {'class_type':'H3StudioSaveFlowState', 'inputs':{
        'samples':['14',0], 'trajectory':['flow_handle',0], 'key':job['id']}}
    return graph


def build(job):
    source = json.loads((STORE / (job['refine_source_id'] + '.json')).read_text(encoding='utf-8'))
    graph = without_spectrum(copy.deepcopy(source))
    # Preserve original low-resolution conditioning for trajectory matching.
    needed = set()
    def visit(key):
        if key in needed: return
        needed.add(key)
        for value in source[key]['inputs'].values():
            if isinstance(value,list) and len(value)==2 and str(value[0]) in source:
                visit(str(value[0]))
    visit(str(source['16']['inputs']['conditioning'][0]))
    for key in needed:
        node = source[key]
        inputs = copy.deepcopy(node['inputs'])
        for name, value in inputs.items():
            if isinstance(value,list) and len(value)==2 and str(value[0]) in source:
                inputs[name] = ['src_' + str(value[0]),value[1]]
        graph['src_' + key] = {'class_type':node['class_type'],'inputs':inputs}
    for key, node in graph.items():
        if key.startswith('src_'): continue
        for name in ('width','height'):
            if name in node['inputs']: node['inputs'][name] = job[name]
    graph['flow_upscaler'] = {'class_type':'MinimaxH3LatentUpscaler3DProvider','inputs':{
        'model_name':'minimax_h3_latent_upscaler_3d_bf16.safetensors',
        'device':'cuda','precision':'bf16','offload_after_upscale':True}}
    graph['flow_load'] = {'class_type':'H3StudioLoadFlowState','inputs':{
        'key':job['refine_source_id'],'width':job['width'],'height':job['height'],
        'learned_upscaler':['flow_upscaler',0]}}
    graph['flow_guidance'] = {'class_type':'H3FlowAlignedRegenerate','inputs':{
        'model':graph['16']['inputs']['model'],'trajectory':['flow_load',0],
        'guidance_mode':'direction','direction_weight':0.15,
        'acceleration_weight':0.0,'consistency_weight':0.0,
        'low_frequency_cutoff':0.25,'temporal_weight':0.0,
        'source_conditioning':['src_' + source['16']['inputs']['conditioning'][0],0]}}
    graph['16']['inputs']['model'] = ['flow_guidance',0]
    graph['14']['inputs']['latent_image'] = ['flow_load',1]
    graph['9']['inputs']['model'] = ['flow_guidance',0]
    graph['9']['inputs']['denoise'] = 0.20
    graph['92']['inputs']['filename_prefix'] = 'video/H3_Studio/' + job['id'][:8]
    return graph
