"""Job-scoped sampling pause for graphs explicitly submitted by H3 Studio."""
from aiohttp import web
from server import PromptServer
import comfy.model_management as mm
import execution
from comfy_execution.progress import ProgressHandler, add_progress_handler
from .control import gate_for, GATES, REGISTRY_LOCK


def running_tokens():
    running, _ = PromptServer.instance.prompt_queue.get_current_queue()
    return {item[3].get('h3_studio_render_token') for item in running if len(item) > 3
            and isinstance(item[3], dict) and item[3].get('h3_studio_render_token')}


@PromptServer.instance.routes.get('/h3studio/render-control')
async def capabilities(request):
    return web.json_response({'version': 1, 'sampling_pause': True, 'releases_vram': False})


@PromptServer.instance.routes.get('/h3studio/render-control/{token}')
@PromptServer.instance.routes.post('/h3studio/render-control/{token}')
async def control(request):
    token = request.match_info['token']
    active = running_tokens()
    if token not in active:
        raise web.HTTPConflict(text='This Studio render is not running')
    with REGISTRY_LOCK:
        for old in list(GATES):
            if old not in active:
                GATES.pop(old, None)
    gate = gate_for(token)
    if request.method == 'POST':
        body = await request.json()
        if type(body.get('paused')) is not bool:
            raise web.HTTPBadRequest(text='paused must be a boolean')
        state = gate.request(body['paused'])
    else:
        state = gate.state()
    return web.json_response({**state, 'releases_vram': False})


class StudioPauseProgress(ProgressHandler):
    def __init__(self, token, dynprompt):
        super().__init__('h3_studio_pause')
        self.gate = gate_for(token)
        self.dynprompt = dynprompt

    def update_handler(self, node_id, value, max_value, state, prompt_id, image=None):
        try:
            kind = self.dynprompt.get_node(node_id).get('class_type', '')
        except (KeyError, ValueError):
            return
        if 'sampler' not in kind.lower():
            return
        def synchronize():
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
        self.gate.checkpoint(mm.throw_exception_if_processing_interrupted, synchronize)

    def reset(self):
        self.gate.request(False)


_reset_progress_state = execution.reset_progress_state


def reset_studio_progress(prompt_id, dynprompt):
    _reset_progress_state(prompt_id, dynprompt)
    running, _ = PromptServer.instance.prompt_queue.get_current_queue()
    for item in running:
        if item[1] == prompt_id and len(item) > 3 and isinstance(item[3], dict):
            token = item[3].get('h3_studio_render_token')
            if token:
                add_progress_handler(StudioPauseProgress(token, dynprompt))
            break


# Register before the WebUI progress handler at each prompt reset. No graph,
# model wrapper, RNG, tensor or native saved-prefix signature is modified.
execution.reset_progress_state = reset_studio_progress
NODE_CLASS_MAPPINGS = {}
