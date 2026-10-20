# Director native AV-tail continuation

New Director clips still use ordinary H3 sampling. When the Studio continuation
bridge is installed, clips of at least four seconds save a bounded 39-frame
native video/audio latent tail. This is not Flow trajectory capture, refinement,
upscaling, or another diffusion pass. Generation settings remain unchanged.

At the first Continue boundary, Studio loads that state and uses the installed
Continuum Join/Finish core with a 22-frame AV guide. Each prompt receives its own
scoped identity/location references. The native temporal-grid helper determines
the sampling window, Finish removes the hidden overlap and aligns audio, and the
last section saves the next state. The original main clip is not rerendered.

The V3.9 public integrated Sampler has no external initial-state input in the
installed build. This bridge therefore delegates directly to that package's
existing Join/Finish implementation; it does not patch V3.9 storage or fabricate
saved Take records. An existing saved V3.9 run retains its original resume path.

Children remain grouped beneath their New parent. To bound decoded host memory,
native children contain at most two sections below 736p, or one at 736p and above.
More sections create additional children with native AV-state handoffs. Temporal
grid alignment means a requested five-second extension can contain 119 new frames
(4.958 seconds at 24 fps).

States are saved under ComfyUI output/h3_continuum_states using UUID-derived
filenames and the package's atomic safetensors/JSON storage. Missing declared
state or incompatible resolution/VAE stops the continuation. Older clips without
state retain the explicitly reported last-frame fallback. No exact identity or
seamless-motion guarantee is made.

The adapter source lives in studio/comfy_nodes/h3_studio_flow_states and is copied
by the existing Optional Film Tools installer. Restart Studio/ComfyUI afterward.
GET /api/video-workflows reports native_tail_ready. Generation details distinguish
native_latent_tail from last_frame_handoff and native_prefix.
