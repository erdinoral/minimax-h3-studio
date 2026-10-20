# Optional H3 tools

## LightVAE Lite video decoder

Requires ComfyUI **0.41.0 or later**. Run Pinokio's **Optional Film Tools**
after stopping Studio. It installs the pinned Kijai INT8 ConvRot LightVAE Lite
checkpoint (about 1.04 GB), verifies its SHA-256, and installs ColorAnchor.
Existing files and model selections are preserved.

In Studio, open **Settings → Advanced H3 models → Video decoder** and select
`minimax_h3_lightvae_lite_vae_int8_convrot.safetensors`, then save.
Empty uses the existing video VAE. This is an experimental alternative:
compare detail, colour and decoding time before using it for final work.
It changes only video decode, including native Continuum's final decode.
Reference/keyframe encoding, AudioVAE, model, LoRAs and sampling stay unchanged.
Draft tiny-decoder mode takes precedence. Recorded jobs store the decoder
choice; changing settings does not rewrite queued job snapshots.

## ClipColorAnchor

After restarting, the node is available in ComfyUI under **MiniMax H3/color**.
Example workflows are copied as **H3 Studio Color Anchor - …** into
`app/user/default/workflows`. They require your clip, anchor clip and masks;
placeholder files are not bundled.

This is colour matching, not an identity or anatomy repair. For frame-based
chains, feed the corrected result into the next clip's context. Correcting
only the final export does not prevent accumulated drift. Do not insert this
pixel correction into Continuum's latent prefix: that is a different context
representation. Studio's native Continuum path is unchanged; the colour tool
is currently a separate ComfyUI workflow, not an automatic Studio toggle.

## Spectrum

The launcher pins `806fe498d574a726fecb8818917f00a4b993fd77` (v0.2.29).
No new installation is needed if this is already installed. Enabled settings
are not proof that forecasts executed: measure a matching run and inspect
Spectrum diagnostics before claiming acceleration.

Manual Gallery enhancement processes an existing MP4 through the learned H3
latent upscaler. It requires no prior recording and performs no diffusion
sampling, so Spectrum is not involved. Automatic capture/refinement during
generation is disabled, including stale clients requesting capture.
The legacy Flow API still accepts previously saved trajectories and bypasses
Spectrum because its active-step provenance is incomplete for that integration.

## Meridian — prerequisites, not an installed Studio engine

The official ComfyUI workflow needs **stock FL2VA BF16**, the teacher and turbo
adapters together, frozen embeddings, and a geometric render. Do not load the
adapters on Studio's pruned FL2VA or Hybrid checkpoint and call it compatible.
The generic Comfy adapters alone are about 3.77 GB; the stock base is about
60 GB. The geometry stage additionally needs separately obtained, gated
VGGT-Omega and its environment. Consumer 16 GB GPU support is not established
by the official reference implementation. Its published high-memory GPU
measurements are not measurements on our system.

Meridian is not advertised as ready or automatically downloaded. Its gated
geometry prerequisite and stock base must be resolved before a working camera
tool can be enabled. No unrelated model files are deleted to make space.

Sources:
- https://github.com/Comfy-Org/ComfyUI/pull/17049
- https://huggingface.co/Kijai/MiniMax-H3-experimental
- https://github.com/lovemachine100/ComfyUI-H3-ClipColorAnchor
- https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3/blob/main/RELEASE_NOTES.md
- https://huggingface.co/Viggle/Meridian
