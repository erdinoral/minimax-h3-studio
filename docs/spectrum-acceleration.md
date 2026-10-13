# Optional Spectrum acceleration

## Local performance results

Test system: NVIDIA RTX 5060 Ti 16 GB, AMD Ryzen 5 5600X (6 cores), 32 GB RAM,
Windows, native H3 Ref2VA INT8, PyTorch 2.10.0+cu130 and ComfyUI 0.36.0.
No additional speed LoRA; SageAttention disabled.

A matched 1056×608, 14-step, approximately 10-second test took 1575.058 seconds
without Spectrum and 966.344 seconds with Spectrum: **38.65% less total time**
(about 1.63× throughput). Both Spectrum passes are included.

Recent 1920×1088, five-second, 17-step presenter jobs took around 35 minutes.
A recalled one-hour baseline would imply roughly 42% less time, but that baseline
was not verified in a matched 1088p comparison. Do not present it as a measured
1088p speedup. See the [announcement draft](spectrum-update-post.md).

With offline smoothing replay enabled, a 17-step job may show 34 progress units:
capture plus replay. This is not an upscaling or face-refinement pass. Spectrum
does not solve continuation drift or guarantee that longer videos fit in VRAM.

## Usage and integration

Spectrum is installed as a separate ComfyUI custom node. SageAttention remains
disabled. Native CUDA kernels, DynamicVRAM and async offloading are unchanged.

In Scene or Studio settings, under Video engine, use the **Spectrum** ON/OFF
switch marked **Experimental**. The control supports English and Turkish.
The default is off. It applies to newly built native MiniMax H3 graphs, after
LoRAs, before the guider and scheduler. Non-H3 graphs and the custom multishot
sampler are left unchanged. Video blend weight is fixed at 0.50; audio blend
weight is 0.0. Motion and speech can differ from unpatched output.

The switch is persisted in `studio/data/h3_acceleration.json`:

```json
{"spectrum_enabled": false}
```

Restart ComfyUI after installing the custom node; restart Studio after updating
its Python integration. Enabling is rejected if the node is not loaded.

Local API:

```sh
curl http://127.0.0.1:42003/api/h3-acceleration
curl -X POST http://127.0.0.1:42003/api/h3-acceleration -H "Content-Type: application/json" -d '{"spectrum_enabled":true}'
```

```python
import requests
requests.post("http://127.0.0.1:42003/api/h3-acceleration",
              json={"spectrum_enabled": False}).raise_for_status()
```

```javascript
await fetch('/api/h3-acceleration', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({spectrum_enabled: false})
});
```

Matched A/B tests must keep reference images, prompt, seed, dimensions, frame
count, sampler, schedule and LoRAs identical. Test speech and gestures as well
as wall time. This uses feature forecasts and can change the generated video.
One comparison is evidence for that workload, not a universal speed guarantee.

Installed revision for the first benchmark: Spectrum v0.2.29,
`806fe498d574a726fecb8818917f00a4b993fd77`.
Source: https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3

To revert, turn the switch off. This restores the native graph without a
Spectrum node; installation does not replace model files or PyTorch packages.
