"""Optional H3 reference and sampler patches; ordinary graphs stay unchanged."""
import json
from pathlib import Path
from .loras import find_spec

STORE = Path(__file__).resolve().parents[1] / 'data' / 'h3_enhancements.json'


def settings():
    try:
        data = json.loads(STORE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    return {'refmod_enabled': data.get('refmod_enabled') is True}


def save_settings(enabled):
    data = {'refmod_enabled': bool(enabled)}
    STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    temporary.replace(STORE)
    return data


def selected_presets(names, graph):
    specs = [find_spec(file=name) for name in str(names or '').split('|') if name]
    specs = [s for s in specs if s and s.get('preset') and graph in s.get('graphs', []) and s.get('file')]
    if len(specs) > 1:
        raise ValueError('Select only one speed LoRA at a time')
    return specs


def preset(names, steps, sampler, scheduler, graph):
    specs = selected_presets(names, graph)
    if not specs:
        return steps, sampler, scheduler
    spec = specs[0]
    return spec.get('steps') or steps, spec.get('sampler') or sampler, spec.get('scheduler') or scheduler


def patch_graph(graph, job):
    if job.get('refmod_enabled') and not job.get('sheet_job'):
        for nid, node in list(graph.items()):
            if node.get('class_type') != 'MiniMaxH3ReferenceToVideo':
                continue
            node['class_type'] = 'SkebaCachedMiniMaxH3ReferenceToVideo'
            node['inputs']['cache_mode'] = 'auto'
            patch_id = 'studio_refmods_' + nid
            # Preserve reference numbering and every existing guide/keyframe.
            for other in graph.values():
                for key, value in other.get('inputs', {}).items():
                    if value == [nid, 0]:
                        other['inputs'][key] = [patch_id, 0]
            owners = {row.get('file'): (row.get('asset') or {}).get('name')
                      for row in job.get('reference_manifest') or []}
            labels = []
            for key, link in node['inputs'].items():
                if key.startswith('ref_images.') and isinstance(link, list):
                    filename = graph.get(link[0], {}).get('inputs', {}).get('image', '')
                    labels.append(owners.get(filename) or filename or 'Reference')
            graph[patch_id] = {'class_type': 'H3StudioRefMods', 'inputs': {
                'conditioning': [nid, 0], 'retention': 1.0,
                'reference_names': json.dumps(labels, ensure_ascii=False)}}
    return graph
