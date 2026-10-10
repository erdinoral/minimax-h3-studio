"""Bridge ordinary numbered H3 references into reusable full-reference RefMods.

Uses the installed SKEBA RefMod runtime; no model training or identity guarantee.
"""
import hashlib
import json
import sys
from pathlib import Path
import folder_paths
from safetensors.torch import save_file


class H3StudioRefMods:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'conditioning': ('CONDITIONING',),
                             'retention': ('FLOAT', {'default': 1.0, 'min': 0.01, 'max': 1.0}),
                             'reference_names': ('STRING', {'default': '[]'})}}

    RETURN_TYPES = ('CONDITIONING',)
    FUNCTION = 'apply'
    CATEGORY = 'H3 Studio/references'

    def apply(self, conditioning, retention=1.0, reference_names="[]"):
        labels = json.loads(reference_names)
        runtime = next((m for name, m in list(sys.modules.items())
                        if name.endswith('.refmod_runtime') and hasattr(m, 'H3RefMod')), None)
        if runtime is None:
            raise RuntimeError('Install the H3 reference tools and restart ComfyUI before using RefMod')
        output = []
        for tokens, metadata in conditioning:
            blocks = []
            for index, block in enumerate(metadata.get('minimax_refs', [])):
                latent = block.get('latent')
                if block.get('kind') not in ('image', 'video') or latent is None:
                    blocks.append(block)
                    continue
                mod = runtime.H3RefMod(name=str(labels[index] if index < len(labels) else f'Reference {index + 1}'), kind=block['kind'],
                                       latent=latent, mode='encode')
                replacement = mod.ref_block(float(retention))
                if replacement is None:
                    raise ValueError('A numbered reference cannot be removed in RefMod mode')
                blocks.append({**block, **replacement, 'refmod': True})
                # The content-derived filename never overwrites another actor's reference.
                cpu = latent.detach().cpu().contiguous()
                key = hashlib.sha256(str((cpu.shape, cpu.dtype)).encode() + cpu.view(-1).view(__import__('torch').uint8).numpy().tobytes()).hexdigest()
                target = Path(folder_paths.models_dir) / 'refmods' / 'h3-studio' / (key + '.safetensors')
                if not target.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix('.tmp')
                    try:
                        save_file({'latent': cpu}, str(temporary), metadata={'refmod_meta': json.dumps({
                            'name': mod.name, 'kind': mod.kind, 'mode': 'encode',
                            'latent_h': mod.latent_h, 'latent_w': mod.latent_w,
                            'latent_t': mod.latent_t, 'fps': 24, 'source': 'H3 Studio asset reference'})})
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
            output.append([tokens, {**metadata, 'minimax_refs': blocks}])
        return (output,)


NODE_CLASS_MAPPINGS = {'H3StudioRefMods': H3StudioRefMods}
NODE_DISPLAY_NAME_MAPPINGS = {'H3StudioRefMods': 'H3 Studio RefMod References'}
