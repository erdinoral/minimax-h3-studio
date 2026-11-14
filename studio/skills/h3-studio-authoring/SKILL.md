---
name: h3-studio-authoring
description: Plan cinematic shots, craft videos, and other H3 Studio productions and author importable Cinema JSON for individual shots or Continuum sequences.
---

# H3 Studio authoring

Read the user's brief and selected production purpose. Preserve supplied assets, runtime, language and camera choices. Draft only the fields needed by the chosen Studio workflow.

- For Cinema imports, use the [standard JSON template](../../schemas/h3-cinema-v1.example.json) or [seamless JSON template](../../schemas/h3-cinema-seamless-v1.example.json). Follow that template's section and mode contract. Remove its authoring instructions and input placeholders from the final JSON.
- For Director chat, use the [Director brief contract](../../prompts/director_system.md). For Scene Continuum, write one finished English prompt per card and preserve their order.
- Set the production purpose and render settings in Studio. The portable templates describe creative content. Use model-specific prompt structure from the [bundled MiniMax H3 guide](../../prompts/h3_skill/SKILL.md).

## Production purposes

- `short_film` builds a story through visible action, reactions and consequences.
- `music_video` plans visuals against the song structure and follows Studio's audio policy.
- `ad` gives the product a clear introduction, demonstration and final view.
- `trailer` opens with a hook, escalates through selected beats and ends on a memorable image.
- `social` shows the central action or payoff early and keeps the framing readable.
- `documentary` observes specific actions and places with motivated light and local sound.
- `explainer` shows one mechanism per shot with a visible cause and effect. Use labels when requested.
- `handmade` starts with hands at work, advances the material each section and shows the finished object. Maintain the workbench, tools and light. Default to workshop ASMR. In Scene, the draft starts with six five-second Continuum cards unless the user requests a different length.
- `intro` establishes the title or visual identity with a short reveal.
- `outro` closes the story or presents a requested final card.

## Cinematic techniques

Describe the shot size, camera height and side, subject placement and intended movement. Use the structured camera fields when available. A static shot can hold an important expression or item. A physical push-in changes perspective, a zoom changes the lens framing, and a lateral tracking shot follows a moving subject. Choose a move that reveals a specific detail.

For suspense or discovery, consider a sequence of physical detail, held reaction, clue and wide or over-the-shoulder reveal. Keep the final information outside the earlier frames. Give each shot a reason to hold or cut. Use small observable actions and sounds that match their source and distance.

Carry prop positions, wardrobe, screen direction and motivated lighting across angles. Use `t2v` for an intended cut and `continue` when the same shot rolls on. For a continuation, the next opening frame describes the preceding ending frame and the action progresses from that state.

In the storyboard, check framing, identity and continuity before rendering. After rendering, compare the output to the intended action and inspect transitions. Camera wording guides generation and should be evaluated on the resulting clip.
