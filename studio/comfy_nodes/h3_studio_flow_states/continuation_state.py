"""Bounded native AV tails; delegates sampling semantics to installed Continuum."""
import importlib
import re
import torch
import nodes


def runtime(part='nodes'):
    sampler = nodes.NODE_CLASS_MAPPINGS.get('H3ContinuumSamplerV39')
    if sampler is None or '.v3.' not in sampler.__module__:
        raise RuntimeError('Compatible H3 Continuum V3.9 is required for native tail continuation')
    package = sampler.__module__.split('.v3.', 1)[0]
    return importlib.import_module(package + '.' + part)


def prefix(key):
    if not re.fullmatch(r'[0-9a-f-]{36}', key):
        raise ValueError('Invalid Studio continuation identifier')
    return 'studio_' + key


class H3StudioSaveContinuationTail:
    OUTPUT_NODE = True
    @classmethod
    def IS_CHANGED(cls, **kwargs): return float('nan')

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'samples': ('LATENT',), 'key': ('STRING',),
                             'frames': ('INT', {'min': 39})}}
    RETURN_TYPES = ('LATENT',)
    FUNCTION = 'save'
    CATEGORY = 'H3 Studio/continuation'

    def save(self, samples, key, frames):
        state = runtime('state').capture_state(samples, source_frame_count=frames,
                                               clip_index=1, capacity_frames=39)
        runtime('state_io').save_state(state, prefix=prefix(key), slot=1)
        return (samples,)


class H3StudioLoadContinuationTail:
    @classmethod
    def INPUT_TYPES(cls): return {'required': {'key': ('STRING',)}}
    RETURN_TYPES = ('H3_CONTINUUM_STATE',)
    FUNCTION = 'load'
    CATEGORY = 'H3 Studio/continuation'

    @classmethod
    def IS_CHANGED(cls, key):
        return runtime('state_io').state_mtime(prefix=prefix(key), slot=1)

    def load(self, key):
        return (runtime('state_io').load_state(prefix=prefix(key), slot=1),)


class H3StudioNativeJoin:
    @classmethod
    def INPUT_TYPES(cls): return runtime().H3ContinuumJoin.INPUT_TYPES()
    RETURN_TYPES = ('MODEL', 'CONDITIONING', 'LATENT', 'H3_CONTINUUM_PLAN', 'STRING')
    FUNCTION = 'join'
    CATEGORY = 'H3 Studio/continuation'

    def join(self, **kwargs): return runtime().H3ContinuumJoin().join(**kwargs)


class H3StudioNativeFinish:
    @classmethod
    def INPUT_TYPES(cls): return runtime().H3ContinuumFinish.INPUT_TYPES()
    RETURN_TYPES = ('IMAGE', 'AUDIO', 'H3_CONTINUUM_STATE', 'STRING')
    FUNCTION = 'finish'
    CATEGORY = 'H3 Studio/continuation'

    def finish(self, **kwargs): return runtime().H3ContinuumFinish().finish(**kwargs)


class H3StudioContinuationWindow:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'context_frames': ([22, 39],),
                             'seconds': ('FLOAT', {'min': 4, 'max': 15, 'default': 5})}}
    RETURN_TYPES = ('INT',)
    FUNCTION = 'window'
    CATEGORY = 'H3 Studio/continuation'

    def window(self, context_frames, seconds):
        return (runtime('temporal').make_extension_shape(context_frames, seconds).total_frames,)


class H3StudioSaveContinuationResult:
    OUTPUT_NODE = True
    @classmethod
    def IS_CHANGED(cls, **kwargs): return float('nan')

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'state': ('H3_CONTINUUM_STATE',), 'clips': ('H3_STUDIO_AV_CLIPS',),
                             'key': ('STRING',)}}
    RETURN_TYPES = ('IMAGE', 'AUDIO')
    FUNCTION = 'save'
    CATEGORY = 'H3 Studio/continuation'

    def save(self, state, clips, key):
        rate = clips[0][1]['sample_rate']
        if any(audio['sample_rate'] != rate for _, audio in clips):
            raise ValueError('Continuation audio sample rates differ')
        if len(clips) == 1:
            images, audio = clips[0]
        else:
            images = torch.cat([images.cpu() for images, _ in clips], dim=0)
            audio = {'sample_rate': rate, 'waveform': torch.cat(
                [audio['waveform'].cpu() for _, audio in clips], dim=-1)}
        runtime('state_io').save_state(state, prefix=prefix(key), slot=1)
        return images, audio


class H3StudioAppendContinuationAV:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'images': ('IMAGE',), 'audio': ('AUDIO',)},
                'optional': {'previous': ('H3_STUDIO_AV_CLIPS',)}}
    RETURN_TYPES = ('H3_STUDIO_AV_CLIPS',)
    FUNCTION = 'append'
    CATEGORY = 'H3 Studio/continuation'

    def append(self, images, audio, previous=None):
        # Keep references until one final concat; never allocate every prefix.
        return ([*(previous or []), (images, audio)],)


NODE_CLASS_MAPPINGS = {c.__name__: c for c in (
    H3StudioSaveContinuationTail, H3StudioLoadContinuationTail, H3StudioNativeJoin,
    H3StudioNativeFinish, H3StudioSaveContinuationResult, H3StudioAppendContinuationAV,
    H3StudioContinuationWindow)}
