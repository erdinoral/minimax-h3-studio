# Experimental video workflows

Scene offers Standard H3 and Continuum. Director offers Existing Multishot and
Continuum in its Seamless engine selector. Existing Multishot remains the default
until the new workflow has passed real continuity/quality validation.

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
