# Optional Spectrum acceleration

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
