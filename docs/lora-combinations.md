# Character LoRA combinations

In both Scene and Director, a selected film actor with **Use LoRA** enabled contributes its adapter to the shot. Compatible global style or motion selections are added alongside it, rather than replacing the character adapter.

Mentioning the film card's name in a shot also adds that actor's enabled LoRA, even when the shot has an explicit or empty image selection. For example, a card named Albedo with the H3 Albedo adapter supplies `lbd0c1tr0n` automatically in every matching new or continuation shot. The card name remains the screenplay name; no manual trigger entry is required. Other image references remain explicitly selected. Unmentioned actors are not inferred from earlier shots.

For structured scene prompts, `Main character:` determines the visual cast. Film-wide voice lists, dialogue addressing someone off screen, and copied learned-identity notes do not add that person to the cast. A globally selected character adapter is also skipped when the structured cast excludes it, unless it was explicitly bound to the shot. Free-text global adapter selections still apply to the whole generation.

Director resolves the scene's character field into asset bindings before both single-shot and film production. A stale binding to an off-screen character is removed; selected images for the current actor and explicit location/prop references are preserved. Unknown cast names fail before queuing. Each shot receives only its own cast's voice bible and a visual identity instruction. Jobs retain a character manifest with actor IDs, voice, LoRA choices and reference source filenames for inspection.

Films with character LoRAs use per-shot production rather than one Multishot adapter stack shared by the entire film. New/Continue choices are preserved. This prevents adapters from being intentionally shared across unrelated shots; it does not guarantee rendered face consistency or isolate two character adapters spatially within one frame.

- Character adapters are loaded first. Their card weights take priority if the same file is also selected globally; an explicit zero is retained.
- Duplicate files are loaded once. Multiple actors can contribute adapters, but this does not guarantee correct separation of identities in the rendered video.
- The current maximum is three distinct adapters, including character adapters. An overfull selection is rejected before the batch is added; remove a global adapter or reduce the cast's adapter selection.
- Missing character adapters or incompatible character adapters produce an error. Global adapters incompatible with the shot graph are filtered out; if none of the requested adapters can be used and there is no character adapter, production is rejected.
- The character's old card images remain excluded while Use LoRA is enabled. Disabling it restores the normal image-reference path.

No new model download is needed for these selection fixes. Restart Studio after changing the backend and refresh the browser to load the updated error translations.
