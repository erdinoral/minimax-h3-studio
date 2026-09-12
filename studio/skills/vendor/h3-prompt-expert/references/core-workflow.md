# Core Workflow / 核心流程

Use this reference for every H3 prompt request.

## Diagnose The Hard Part

Identify the main risks before writing:

- Identity risk: multiple characters, face/body consistency, role swapping, duplicated or missing subjects.
- Product risk: exact product geometry, material, brand color, package text, logo, small structure.
- Text/UI risk: readable words, menus, HUD, subtitles, posters, app screens, title cards, logos, dashboards.
- Layout risk: composition, hierarchy, grid, poster, packaging, typography, game interface.
- Motion risk: precise camera path, one-take, action, transformation, mechanical timing.
- Edit-preservation risk: source video must keep camera, timing, occlusion, lighting, and unedited regions stable.
- Audio/dialogue risk: lip sync, exact lines, dialect, timbre, lyrics, rhythm.

The higher the risk, the more the prompt needs anchors: reference images, asset-role statements, exact text ledger, timeline, negative constraints, and preservation clauses.

## Build The Creative Spine

Every final prompt should visibly contain these layers, even if section names differ:

1. Concept: premise, target format, use case, genre, mood.
2. Design system: colors, materials, typography/UI style, lighting, texture, visual motifs.
3. Subject lock: character/product/object identity, differences between similar subjects, positions, no-drift rules.
4. Motion: timeline, camera path, action beats, transitions, interaction or transformation logic.
5. Failure control: exact text ledger, preservation clauses, negative constraints.

## Stable Creative Defaults

- Plan story, advertising, and case-demo deliverables around 15 seconds; use roughly 10 seconds for simple product, UI, or action demonstrations unless the user confirms another duration.
- Use 16:9 for cinematic, brand, UI, or game demonstrations; 9:16 for short drama and social advertising; reserve 1:1 for feed- or poster-like delivery.
- Prefer realistic cinematic treatment for real-world scenes unless anime, MG, or illustration is requested.
- Use realistic ambience and restrained sound design; add background music only when it supports the concept.
- End with a clear final beat, product or logo frame, title card, emotional reaction, or transformation payoff.

## Self-Check

Before responding, fix the prompt if any of these are weak:

- Does it preserve the user's original intent?
- Does it have a distinctive creative hook?
- Is the visual system concrete rather than just a style label?
- Are subjects/products/text/UI locked clearly enough?
- Is the first shot clear and the final shot a strong payoff?
- Is the timeline realistic for 4-15 seconds?
- Are camera moves and transitions physically/logically connected?
- If text/UI appears, is there one exact text ledger or reference-image anchor?
- If multiple subjects appear, are role, position, visual identity, and anti-swap rules clear?
- If editing source video, are preservation and edit boundaries clear?
- Does the sound design support the scene?
- Are negative constraints targeted to actual risks?
