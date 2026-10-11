# Hybrid H3 reference experiment

Source tutorial: https://www.youtube.com/watch?v=tmw2QOFaaPI (20:38–22:34).
The author's 30-second example was one reference-conditioned generation at
approximately 1 MP on a 48 GB GPU. This does not establish the same capacity
or identity fidelity on a 16 GB GPU.

Select **H3 Hybrid** in Video engine. This selects the b25–49 checkpoint for
both existing H3 model slots without changing the encoder or VAEs. MiniMax H3
and Singularity remain selectable.

In Scene, select **Reference** with H3 Hybrid active. The duration menu then
offers an experimental **30 s** option. Continuation, storyboard and batch
limits remain unchanged. The API accepts `duration: 30` only with `mode: ref`
and the hybrid reference checkpoint selected. Supply at least one reference.
H3's valid 17k+5 frame grid rounds 30 seconds to 736 frames at 24 fps (~30.67 s).

Start with 352p, one clear character reference, the Hybrid r48 speed LoRA
(8 steps), and a prompt specifying the same subject across several camera
angles. Keep appearance references distinct from first-frame/composition
anchors. The preset uses res_multistep/simple, verified on the tutorial's
15:06 frame. The full tutorial graph has not been imported, so this is a
controlled local adaptation, not a claim of an identical reproduction. Do
not stack other speed LoRAs for this test.

Use the official six-section Ref2VA prompt format: `subject_definitions`,
`summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`,
`non_diegetic_music`. Refer to the same `<Subject 1>` throughout and describe
each shot explicitly. Review identity, camera changes and motion before
increasing resolution or adding latent refinement.

## Assets

- `diffusion_models/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors`
  (20,970,379,632 bytes):
  https://huggingface.co/smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models
  SHA256: `a629cfea8d89a071b140c6e1935dc9a23e72de6badc18975a2bb9e6d1423d76d`
- `loras/lightx2v_hybrid-4to8step-Turbo_r48.safetensors`
  (943,947,204 bytes):
  https://huggingface.co/TenStrip/MinimaxH3-Turbo_Shenanigans
  SHA256: `c660d2858a4f2914acd84ec01677b48fb6b394f82b6292ca3f315578f79ecb73`

Download to a `.part` file and verify size and SHA256 before renaming. The
standard H3 text encoder, video VAE and audio VAE are reused. Latent upscale
is a separate refinement stage and is not part of the initial identity test.

## Required LoRA compatibility loader

The original r48 adapter has dense 2688-dimensional AdaLN tensors; this
checkpoint uses an 8-dimensional curve. The stock LoRA loader skips those
layers. Studio routes this adapter through `H3StudioHybridLora`, delegating to
`H3PowerLoraStack` with automatic AdaLN porting and quantized-layer handling.
The Studio bridge rejects incomplete adapter reports instead of rendering
with silently skipped layers. Install
https://github.com/cicalooo/ComfyUI-H3-PowerLoraStack in `app/custom_nodes`
(tested commit `55da4ee624a6d730c3853cd7309892ec38257a60`) and restart ComfyUI.
Copy `studio/comfy_nodes/h3_studio_enhancements/__init__.py` to
`app/custom_nodes/h3_studio_enhancements/__init__.py` before restarting;
the Film Tools installer also copies this bridge.

Put `h3_silu_temb_grid.safetensors` in `app/models/h3_adaln` (the compatibility
grid is not a selectable LoRA):
https://huggingface.co/deAPI-ai/minimax-h3-33b-int8/resolve/main/loras/h3_silu_temb_grid.safetensors
(5,510,600 bytes; SHA256
`30eb3c2cc7fb6b470d9717ff840d359313ac27cd64b705e32da1baa10f72d6a8`).
The loader fits this grid to the selected checkpoint's own curve. Do not
substitute an adapter pruned against a different checkpoint's basis.

The initial local test reports all 51 AdaLN pairs ported, basis-fit residual
`1.7e-03`, 160 merged and 150 branched layers. Fifty fused quantized layers
require merging; this is a remaining precision tradeoff. Check the loader
report for dropped, rejected or skipped layers before assessing a render.

## First local result (2026-10-11)

RTX 5060 Ti 16 GB / 32 GB RAM: one reference, 608×352, 8 steps,
res_multistep/simple, seed 20261012, original r48 strength 1, RefMod off.
Job `95f71ab5-0773-431a-9b35-a3822664cb4f` completed in 17m19s.
The output contains 736 video frames at 24 fps (30.667 seconds), with audio.
The request and final job snapshot are saved under `studio/data/research-h3`;
the clip is in Studio's gallery.

Frames sampled through the clip retain the same apparent face, hairstyle,
beard and white polo while framing changes from seated medium views to a
close-up and a standing wider view. This is a visual assessment of one
low-resolution seed, not an identity benchmark. Detected abrupt transitions
at approximately 12.25s and 14.79s do not match the requested cuts at 10s and
20s. Timing adherence and detail refinement remain to be improved; no latent
upscale or corrective Cinema/Film adapters were used in this baseline.

## Direct 736p test (2026-10-11)

Job `c64e7876-5226-4c3e-b867-139f81bfefd3` used the same reference, prompt,
seed, 8-step adapter and settings, changing only quality to 736p (1280×736).
The queue was empty before submission. The verified LoRA loader succeeded,
but `SamplerCustomAdvanced` failed before completing step 1, in the first
attention QKV linear allocation. CUDA reported 8.22 GiB allocated and a new
8.24 GiB allocation against a 15.93 GiB device limit. The prompt ended with
OOM after 33.73 seconds; no video was produced. ComfyUI unloaded the models
and remained available.

This establishes failure of the current direct 30-second 736p graph on this
16 GB GPU, not impossibility under every implementation. Reducing sampling
steps does not remove this per-forward activation allocation. A second H3
refinement pass at the same full duration/resolution also needs a memory
strategy; latent upscale alone does not establish that it will fit. Processing
the existing clip with a separate AI video upscaler is a different route.

## Tested short-shot alternative on 16 GB

Two independently generated 1280×736 shots completed with the same hybrid
checkpoint, r48 strength 1, 8 steps, res_multistep/simple and seed 20261012.
RefMod and prompt rewriting were off. Reference size was max.

- Shot 1: requested 6 seconds, output 158 frames / 6.583 seconds. Job
  `87aa3f2b-83e2-477a-855d-3c8fec989fef`; Comfy execution 14m03s.
- Shot 2: requested 4 seconds, output 107 frames / 4.458 seconds. Job
  `fec35063-5629-448f-849c-eaecd1d9479c`; Comfy execution 9m01s.
- Gallery concat batch `07829154`: 265 video frames at 24 fps, 1280×736;
  container duration 11.104 seconds including AAC timing.

### Reusable procedure for camera cuts

1. Supply the original character photograph as Picture 1. Describe the
   character as Subject 1 in the six-section Ref2VA prompt format.
2. Generate a short establishing shot. Extract one frame for the environment
   and keep this same environment anchor for subsequent shots. This test used
   its frame zero (`studio/data/research-h3/hybrid-short-room.png`).
3. On subsequent shots, use the original photograph as Picture 1 and that
   environment frame as Picture 2. Assign facial identity and clothing to
   Picture 1; room geometry, lighting and props to Picture 2. State that the
   man visible in both pictures is the same subject, not a second person.
4. Describe one action and the requested new composition from frame zero.
   Keep the engine, adapter, aspect ratio and output resolution consistent.
   Seed is recorded for reproducibility; references supply the identity.
5. Select the finished clips in chronological order in Gallery and combine
   them. H3's frame grid pads the requested duration; trim a finished edit if
   an exact total duration is required.

The sampled frames preserve the apparent character and white polo across
these two shots, and the environment remains broadly similar. This is one
visual example, not a guarantee across arbitrary shots. Camera-angle control
is imperfect: shot 2 produces a closer frontal view rather than consistently
following the requested left three-quarter angle. Runtime is still substantial.
These tests validate camera-cut assembly, not seamless last-frame continuation
or audio-driven lip sync. The existing continuation path can combine a previous
last-frame guide with original identity references, but was not rendered in
this pair of tests.

Requests, job snapshots, reference upload and merge response are saved under
`studio/data/research-h3/hybrid-short-*`. The source clips are in Gallery and
the combined file is `studio/data/cinema_finals/07829154_final.mp4`.
Reference prompt guidance: https://github.com/MiniMax-AI/MiniMax-H3

### Last-frame continuation test

After the camera-cut example, a four-second continuation was generated from
shot 1's exact final frame, with the original portrait retained separately.
Job `b8b7ffa2-11c2-49e4-b224-8d9b4d726f18` uses the existing continuation
path, Hybrid b25–49, r48 strength 1, 8 steps, 736p, and seed 20261012.
The graph contains both Ref2VA images (last frame first, portrait second)
and `MiniMaxH3AddGuide` at frame 0. RefMod was disabled for this job and
its previous setting restored immediately after queuing.

The sampled boundary frames preserve the preceding head pose and room
composition much better than the independent second shot. The man then
turns towards the camera and smiles. There is still a small reconstruction
change at the boundary, and later framing drifts; this is not a guarantee
of a seamless shot or continuous motion velocity. Only visual continuation
was inspected; audio continuity and lip sync were not validated.

Gallery concatenation produced `studio/data/cinema_finals/e2659083_final.mp4`,
1280×736, 265 frames at 24 fps, 11.104 seconds including audio timing.
No transition effect was added. Boundary samples and the repeatable extraction
script are under `studio/data/research-h3/`.

An initial attempt (`a1078d01-470d-4b27-99cc-0b2ffa0afc18`) was cancelled:
explicit Picture 1 references in the submitted text were remapped to Picture 2
by asset annotation when the last-frame guide was prepended. The completed
test uses plain descriptions of the previous final-frame guide and additional
identity portrait, leaving numbered reference assignments to the worker.
This avoids the collision in this test; it does not repair the general prompt
numbering behavior.

### Silent stationary-broadcast attempt (failed visual quality)

Job `5b6551a2-cf4d-4f9f-9a45-e71daffdc6fa` requested a four-second
stationary webcam composition, using the establishing shot's frame zero as
guide and the original portrait as identity reference. Hybrid r48 strength 1,
8 steps and 736p were retained. `silent_audio=true` removed the audio decode
and mux branches; ffprobe confirms a video-only 4.458-second output.

Despite a successful runtime status, sampled frames contain severe coloured
noise. This result is a failed visual test and must not be presented as a
working stationary broadcast workflow. Background optical-flow estimates
have only 4–6 affine inliers after frame zero and are unreliable on this noisy
output. Camera stability is therefore not validated. The clean guide image
was inspected; the root cause of the noisy output is unresolved. LoRA,
silence configuration and cached runtime state have not been isolated in an
otherwise identical control render.

The earlier audible clips were generated with `silent_audio=false` despite
text requesting no dialogue. Generated speech was not transcribed or its
language verified. For clips without supplied dialogue/audio, a text-only
"no speech" instruction is not an adequate output-audio guarantee.
