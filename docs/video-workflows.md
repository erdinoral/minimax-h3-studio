# Experimental video workflows

Scene offers Standard H3 and Continuum. Director uses a Continuum ON/OFF switch.
ON creates native combined takes with visual asset references; OFF uses independent
scene production. The old Multishot selector is removed from the interface.

## Continuum

Native V3.9 sampler with persistent Save + Auto Resume storage, 4–15 second
chunks and up to 16 logical chunks per run/take. Start a run from an image or
prompt, then select its Gallery record in Continue. Standard MP4 records cannot
be converted into native Continuum state. Reuse retains the original seed,
dimensions, model, sampler, steps, references and chunk duration.

Each result is a new Gallery video containing the complete sequence. It does
not overwrite its predecessor. More than 16 Director scenes are separate takes;
continuity across takes is not claimed. Duration/resolution remain subject to
available RAM/VRAM. Test at 480p before larger runs.

## H3 Refine

Enable **Prepare H3 Refine recording** before a standard single-clip render.
Preview and post-pass must be off. After completion, the player action at the
right opens a target-resolution dialog. Only targets above the source short edge
are offered; the API independently enforces this. Refinement creates a separate
Gallery entry with `refine_source_id`; the source stays untouched.

The integration captures a real H3 Flow trajectory plus joint AV latent and saves
primitive metadata/CPU tensors atomically. Loading uses `weights_only=True` and
UUID-keyed files restricted to Comfy's output directory. Original graph inputs
are stored separately to reproduce source conditioning. Existing MP4s have no
trajectory and are unavailable for native refinement.

This version uses the H3-trained 3D latent upscaler followed by conservative
Flow-guided resampling (denoise 0.20, direction 0.15; temporal blending off).
Temporal geometry is preserved; the saved audio latent is masked out
of resampling. Appearance/motion can change. Audio quality still needs listening
tests; no speed or fidelity guarantee is implied.

Recording is opt-in because trajectory history requires additional RAM/disk.
Files live in `app/output/H3_Studio_Flow` and `studio/data/flow_graphs`. Keep those
records with the corresponding Gallery videos if future refinement is required.

## Installation

The existing Film tools installer installs missing packages without resetting
existing custom-node directories, and copies Studio's state bridge. Restart
Studio/Comfy after the production queue finishes. Runtime readiness checks disable
unavailable controls and reject unsupported requests before queueing.

Pinned source revisions (upstream licenses retained):

- Continuum: `ukr8b3g-cmyk/ComfyUI-H3-Continuum`, MIT,
  `e9b1294ccd08dfce972cd8e5a11703b3f616ee54`.
- Flow: `xmarre/MiniMax-H3-Flow-Aligned-Regenerate`, Apache-2.0,
  `2bc8247810f99ccf5f580bfab985b7defe26a620`.
- Learned upscaler: `xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus`,
  `1ddcc33e9b674aaabbccc3808fe36e1a47bdd36d`; checkpoint from
  `LBH-123-AI/Minimax_h3_latent_Upscaler` at
  `3f941d5d182014dd5c0a5e16330420ee2d4aa0c6` (690.6 MB).

## Scene Continuum controls

Continuum uses an ON/OFF switch. Single prompt repeats the main prompt for the selected section count. Per section accepts one prompt card per new section; the server validates 1–16 non-empty cards, and existing sections count toward the 16-section run limit. New video starts a new run; Continue adds to the selected run. Duration and quality are selected once in the top Scene controls; Seed and Steps share a row.

### Shared context and transition presets

Optional Continuity settings include a shared character/setting prompt and Balanced (22 prior frames) or Strong (39 prior frames, experimental) context. Shared context is prepended to each newly added section. Continuations inherit the original shared context and preset; saved prefix prompts are never rewritten. Strong context is not an identity guarantee and may cost extra memory or affect motion. Balanced remains the default pending visual comparisons.

### Spectrum and saved-run compatibility

New Continuum runs honor the Spectrum switch. Spectrum's mutable runtime binding is not observable by the pinned native storage contract, so these runs use storage Off; saved-prefix continuation is unavailable. Legacy Continuum prefixes containing Spectrum are rejected instead of silently rerendering earlier sections. Use a new run with Spectrum off when saved-prefix reuse is required. Independent Director takes can still pass a previous last frame; this is a visual handoff, not native latent-prefix reuse.

Spectrum video prediction blend is configurable in engine settings: Light 0.25, Balanced 0.50 (the existing default), Strong 0.75, or Custom 0–1. This controls the video spectral/replay blend ceiling, not the percentage of skipped evaluations; presets do not change the scheduler, warmup, or protected tail. Audio blend remains 0.00 and smoothing replay stays enabled. Partial settings updates preserve the switch and manual value. Settings affect graphs built afterward; an already submitted graph keeps its captured values.

### Director visual references

Director Continuum uses the resolved visual references from each scene, including explicit asset bindings. Unique images are collected per take (maximum 9) and assigned only to their relevant native chunks. Section-local reference labels are mapped to fixed V39 `@R` slots; the native sampler accounts for first-frame offsets and active subsets. Ref2VA is selected when visual references exist. Character portraits no longer force the ordinary per-shot fallback for Continuum; Multishot retains that fallback. A first-frame guide is supported at the start of a New take. A new guide on a Continue scene or a separate character LoRA stack is rejected rather than silently changing the requested method.

### Director mode and reference detail defaults

The Director Continuum switch replaces the old Seamless/Multishot selector in the interface. Visual asset cards remain accessible through the library. New native Continuum runs use Match Output reference preprocessing to bound reference area by output area. The Director API accepts `continuum_reference_size: "Max Identity"` for an explicit higher-detail choice. Continuations preserve their source setting; older runs fall back to their original Match Output setting so saved sections remain compatible. The legacy explicit Multishot API is retained for old integrations.

### Director story order and take handoffs

Director keeps the imported JSON scene order, take metadata, structured action beats and explicit new/continue choices. Each scene has its own prompt; a shared look or character description does not replace its action. Prompts are sent as a JSON list so formatting separators inside a scene cannot create unintended chunks.

AI Director receives the selected production mode and plans the same chronological sections JSON for Continuum. Each clip advances one achievable action; the plan must preserve geography, props, injuries and direction of travel. For AI-generated Continue sections, the opening frame is linked to the preceding section's ending frame before import. Explicit New scenes retain their separate opening composition. Imported user-authored JSON is not rewritten by this planner rule.

A native Continuum run contains at most 16 chunks. New-scene cuts, take boundaries and the chunk limit split the run. A following scene marked Continue depends on the previous take's completed clip and starts from its last frame; a scene marked New starts independently. Missing or failed predecessor clips stop the continuation rather than silently starting a new unrelated shot. Selecting an individual continuation uses its own previous Director scene, not the global most recent video.

Across separate takes this is a last-frame visual handoff, not shared native latent/audio history. Within a run, Continuum handles native continuity. This fixes queue linkage; narrative action, motion and identity quality still require visual validation of generated output.
