# Optional film LoRAs and workflows

Pinokio now provides **Optional Film LoRAs** and **Optional Film Tools**. These are separate from the default installation. Studio Settings links to the installed ComfyUI tools.

The adapter catalog includes Fyre and AI30 (characters), Mara Whitlock and Albedo's H3 versions, Natural Face & Speech v2, Camera Motion, FaceSwap REF2VA, Character Swap, Focus Slider and Detail Slider. The installer compares existing SHA256 hashes, reuses matching files, and validates the downloaded container, size and published hash before activation. It does not overwrite a valid file with an HTML error response.

Some Civitai files require authentication. Enter a Civitai API key under **Settings → H3 LoRAs**, then download the desired catalog entry. The key is stored only in local runtime data, is never returned by the API, and is only attached to requests to civitai.com. No key is bundled with the app.

## Adapter usage

- **Fyre:** trigger `Fyre`; **AI30:** trigger `ai30`. Both are offered for FL2VA; Ref2VA performance has not been established.
- **Mara:** trigger `marawhitlock`; **Albedo:** trigger `lbd0c1tr0n`. Only the MiniMax H3 versions belong in this app's catalog.
- **Natural Face & Speech v2:** no trained trigger; recommended starting strength 0.6–0.8, 15–30 steps, T2V/I2V. Published speech examples concern English; Turkish output needs testing.
- **Camera Motion:** `camera motion` is placed first in the actual model prompt, even after reference/continuation instructions are assembled. Starting strength 0.8; describe the desired movement.
- **FaceSwap / Character Swap:** provide a source video and target-character image in Reference or Motion Transfer. Character Swap has no trained trigger. Name the person to replace, especially with multiple people in frame. These are experimental edits, not guarantees of timing or expression preservation.
- **Focus Slider:** negative for shallower focus, positive for deeper focus; creator suggests roughly -4 to +4. **Detail Slider:** creator range -2 to +2; may introduce extra details. Explicit zero is retained. Small valid safetensors files are accepted.

## Outfit sheets

The library has an iOS-style **H3 / Qwen** switch. Uploading a reference never changes the selected engine. H3 uses its existing short-video still workflow. Qwen uses text-to-image without a source and **Qwen Image Edit 2511** with one; each referenced view has its own sampler and saved output, conditioned on the original image. Referenced Qwen outputs are never split into panels. The separate Sheet option was removed; older saved Sheet selections display as H3. Existing Look Sheets jobs can still finish.

**Generate from reference** uploads and previews a source, then waits for **Generate images**. **Remove reference** clears the staged selection. Regeneration keeps the original source and follows the currently selected method. Qwen Edit requires `qwen_image_edit_2511_fp8mixed.safetensors`, the Qwen image encoder and VAE. ComfyUI's configured shared model folders can provide the Edit weight without duplicating its download.

Character/creature cards request five views; vehicles request front, rear, right and left views; locations request four viewpoints. Selected frames are saved separately, plus a contact sheet available through **View sheet**. Selection clusters generated frames; it does not prove that every requested angle or identity detail was generated correctly. Inspect the results before video production. The source photo is retained separately from generated card references.

Existing automatically generated sheets are replaced. Manually uploaded card images are preserved; a full card must free enough slots before queuing. LoRA-enabled characters cannot generate or attach sheets. The optional API request accepts a second clothing reference for characters; the Studio card action takes one source image.

The standalone **H3 Studio Look Sheets - Basic API.json** workflow remains available in ComfyUI for person/outfit experiments. The creator's more elaborate two-stage workflow can require additional utility nodes. Install **Film Tools** in Pinokio and restart ComfyUI if the Look Sheets nodes are unavailable. No extra sheet model is downloaded by the card action.

## Video/audio latent continuation

Use the **H3 Studio Native AV** Start workflow for the initial clip, then Continue with the saved AV latent. Choose a unique chain name/index to avoid overwriting another sequence. The stitch workflows assemble the saved chain. These workflows use Herrgott's native masked AV nodes; they retain video/audio latent context rather than passing only the final image.

They are a separate ComfyUI workflow path. Studio's existing Continue button does not silently change to native masked AV. New nodes require a ComfyUI restart. The suite validates actual native H3 mask support and requires a compatible ComfyUI build.

Sources: [Look Sheets](https://github.com/shisa84/ComfyUI-H3LookSheets), [Native Masked AV suite](https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite), and each adapter's `source` in `studio/lib/film_lora_catalog.json`. Model weights stay outside Git. Download/integration checks are not video-quality benchmarks.
