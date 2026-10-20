from .flow_state import NODE_CLASS_MAPPINGS
from .continuation_state import NODE_CLASS_MAPPINGS as CONTINUATION_NODES
NODE_CLASS_MAPPINGS.update(CONTINUATION_NODES)
NODE_DISPLAY_NAME_MAPPINGS = {
    'H3StudioSaveFlowState': 'H3 Studio Save Refine State',
    'H3StudioLoadFlowState': 'H3 Studio Load Refine State',
}
