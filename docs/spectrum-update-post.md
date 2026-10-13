# Spectrum update — announcement

Spectrum acceleration is available in H3 Studio under **Settings → Video engine** and in Scene settings. Turn the **Spectrum** switch ON before starting a new generation. It is optional, marked Experimental, and is not a LoRA. Turn it OFF to return to native sampling.

On my local system, a matched 608p test (1056×608, 14 steps, approximately 10 seconds) dropped from **26 minutes 15 seconds to 16 minutes 6 seconds**: **38.65% less total render time**, or about **1.63× throughput**. Reference, prompt, seed and generation settings were kept the same. This timing includes Spectrum's capture and replay passes.

Recent 1088p presenter clips at 1920×1088, five seconds and 17 steps rendered in around **35 minutes** with Spectrum. Compared with my recalled roughly one-hour render time, that would be approximately **42% less time**, saving about 25 minutes per clip. The one-hour baseline has not been verified in a matched 1088p A/B test, so this is an approximate observation, not a benchmark claim.

**Test system:** NVIDIA GeForce RTX 5060 Ti with 16 GB VRAM, AMD Ryzen 5 5600X (6 cores), 32 GB RAM, Windows. Native H3 Ref2VA INT8, PyTorch 2.10.0 with CUDA 13.0, ComfyUI 0.36.0; SageAttention disabled. No additional speed LoRA was used.

Current Studio defaults use video blend weight **0.50**, audio blend weight **0.0**, and offline smoothing replay enabled. Replay runs a capture pass and a replay pass, so a 17-step job can display 34 progress units. That is not a resolution upscaler or a separate face-refinement pass.

Spectrum can change motion, speech and output quality. It does not fix identity drift, camera consistency or VRAM limitations. Try one short clip before queuing a whole project. Speed gains depend on the workload and hardware; they are not guaranteed for every generation.

After installing or updating Spectrum, restart ComfyUI/Studio when the production queue is idle, then refresh the browser. Toggling an already installed Spectrum does not require a restart, but does not alter a generation already running. The switch affects native single-clip H3 graphs, not the custom multishot sampler.

Source: [Spectrum for MiniMax H3](https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3). Integration and comparison details: [Spectrum guide](spectrum-acceleration.md).
