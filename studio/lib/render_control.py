"""Optional, job-scoped Comfy cooperative pause bridge."""
import uuid
import httpx


def supports_graph(graph):
    # Keep the graph/model completely unchanged: native prefix contracts
    # fingerprint model wrappers and upstream nodes, including their state.
    return any('sampler' in node.get('class_type', '').lower() for node in graph.values())


async def prepare(base_url, graph, job):
    job.pop('render_control_token', None)
    job.update(render_pause_requested=False, render_paused=False)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(base_url + '/h3studio/render-control')
            if response.status_code != 200 or response.json().get('version') != 1:
                return
        token = uuid.uuid4().hex
        if supports_graph(graph):
            job['render_control_token'] = token
    except (httpx.HTTPError, ValueError):
        pass  # Older Comfy installations still generate normally.


async def command(base_url, token, paused=None):
    async with httpx.AsyncClient(timeout=5) as client:
        url = base_url + '/h3studio/render-control/' + token
        response = await (client.get(url) if paused is None else client.post(url, json={'paused': paused}))
        response.raise_for_status()
        return response.json()
