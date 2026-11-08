# LoRA combinations

Character identity comes only from image references (character cards, face references or Director stills). LoRAs selected in Scene or Director are global style, motion, speed, speech, camera or swap adapters applied to the whole generation.

For structured scene prompts, `Main character:` determines the visual cast. Film-wide voice lists and dialogue addressing someone off screen do not add that person to the cast.

Director resolves the scene's character field into asset bindings before both single-shot and film production. A stale binding to an off-screen character is removed; selected images for the current actor and explicit location/prop references are preserved. Unknown cast names fail before queuing. Each shot receives only its own cast's voice bible and a visual identity instruction. Jobs retain a character manifest with actor IDs, voice and reference source filenames for inspection.

- Duplicate files are loaded once; an explicit zero weight is retained.
- The current maximum is five distinct adapters. An overfull selection is rejected before the batch is added.
- Missing adapters produce an error. Adapters incompatible with the shot graph are filtered out; if none of the requested adapters can be used, production is rejected.
