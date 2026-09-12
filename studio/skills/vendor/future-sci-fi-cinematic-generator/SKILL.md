---
name: future-sci-fi-cinematic-generator
description: |
  Create a realistic future-sci-fi short from a brief and references: continuity-safe assets, storyboards, segmented video, and final assembly. MiniMax-H3 is default; check explicit alternatives first.
trigger-words: [future sci-fi cinematic generator, future sci-fi film, realistic sci-fi short, live-action sci-fi, 未来科幻质感影视生成器, 未来科技感短片, 未来科幻写实短片, 超写实科幻电影]
---

# Future Sci-Fi Cinematic Generator

Use this Skill for a single ultra-realistic live-action future science-fiction short film. Every visual output in this Skill—including character assets, species assets, prop assets, scene anchors, four-view sheets, storyboard grids, shot references, and final video—must use a realistic Hollywood science-fiction blockbuster visual language unless the user explicitly requests another treatment. It coordinates creative development, reusable character/scene/prop assets, asset-bound storyboards, segmented video generation, and ordered assembly. Treat every user-confirmed story, character, scene, and reference as authoritative; preserve anything the user has not asked to change.

## STEP 1: LOCK THE CREATIVE BRIEF

1. Capture the story premise, protagonist, core event, world logic, tone, ending, language, duration, paragraph count, aspect ratio, and physical medium.
2. If the user gave a visual direction, translate it into executable rules for lighting, color, space, materials, atmosphere, and scale. Otherwise offer four cards: hard-science deep-space exploration, epic space opera, wasteland relic sci-fi, and alien organic ecology.
3. If the user does not choose a direction, use restrained ultra-realistic science-fiction cinema rather than silently selecting one of the four themes.
4. Lock the confirmed direction, non-cyberpunk baseline, 16:9 landscape format, duration, paragraph count, narrative language, and physical medium. Default missing duration to 60–90 seconds and 4–6 paragraphs, each 10–15 seconds.
5. Confirm the story synopsis and whether the ending needs a twist. The opening three seconds must enter through conflict, anomaly, or suspense; the synopsis must establish protagonist, event, world logic, tone, and paragraph count.

## STEP 2: IDENTIFY REFERENCES AND CHARACTERS

1. Classify supplied media as character, scene, prop, storyboard, reference video, or reference audio. Extract only observable facts: facial features, hair, clothing, proportions; spatial structure, materials, furnishings, light source, weather; or motion, camera, rhythm, and sound.
2. Build an exhaustive cast inventory from the confirmed script before asset generation. Include every human, android, robot, alien, creature, intelligent species, animal-like organism, and other species that appears on screen, is seen in a reference, or drives the story through an off-screen relationship or event. No appearing character or species may be omitted.
3. For every inventory entry, record name/code, species or body type, narrative role, relationship, power/emotional state, conflict/common goal, scenes/paragraphs, and cross-paragraph appearance requirements. Get user confirmation of this complete inventory before creating character assets.
4. Bind user-provided character or species references directly to the matching element and preserve core identity and design. Do not redesign them unless explicitly requested.
5. Generate a separate standalone character asset for every confirmed inventory entry, including non-human species and alien lifeforms. Do not merge distinct characters or species into one sheet merely for convenience. Each new character as a standalone white-background asset. The base portrait is a front-facing waist-up 9:16 image with a concise appearance description; do not add a scene, extra people, story action, or decorative environment. User-provided references may retain their original background unless a clean white-background version is explicitly requested.
6. After all character and species base assets are confirmed, generate one 16:9 four-view character sheet in the fixed left-to-right order: chest-up close view, full-body front, full-body side, full-body back. Keep identity, clothing, facial features, and proportions identical.
7. Create separate white-background assets for props and other single-subject elements with a complete silhouette, believable material, and stable proportions.

## STEP 3: BUILD SCENE ANCHORS

1. Confirm scene settings only after the character/four-view assets are accepted.
2. For each scene element, first make one empty 16:9 scene concept image. Without a scene reference use text-to-image; with one use image-to-image. This image is the review anchor for spatial structure, materials, weather/ecology, color, light direction, and style.
3. Use Midjourney V7 only for this scene concept image. Its prompt body must be one continuous positive English description, with Chinese field headings only, and no negative prompt or separate prohibition block.
4. After the user approves the scene concept, generate one 16:9 4K 2x2 scene four-view sheet from that approved image. The four views are: centered front axis, left-front 45 degrees, right-front 45 degrees, and deepest/rear view looking outward; for an exterior-only landscape, replace the fourth with a distant-to-foreground centered view.
5. All four views must depict the same empty location, time, weather/ecology, light direction, proportions, materials, colors, and style. No people, silhouettes, reflections, shadows, screens with people, events, or activity may appear in a scene sheet.
6. Bind the approved four-view sheet as the final scene asset. Do not proceed to asset-bound storyboards until it is confirmed.

## STEP 4: WRITE THE STORYBOARD AND OPTIONAL DRAFTS

1. Write a 100–200 word core synopsis, then a strict timeline. For projects up to 60 seconds use 4–5 paragraphs; for 90 seconds use 6–10. Each paragraph is one shot and one video segment, 10–15 seconds maximum. Total duration, paragraph count, shot count, and video-segment count must match.
2. Keep each paragraph as one generation task. Internal 3–4 second beats may organize action and emotion, but must not become additional shots.
3. Favor medium shots, close shots, and close-ups. Use wide or extreme-wide views only when deep-space scale, monumental architecture, wasteland isolation, or alien ecology is narratively necessary.
4. Reference bound elements explicitly in every paragraph. Describe environment, sourced light, physical medium, visible action, emotion, plot event, effects, and the transition into the next paragraph. Preserve the approved event order exactly.
5. For a six-paragraph short, create one recommended storyboard image for each paragraph using a 12-panel grid, preferably a 3x4 or 4x3 layout with clearly numbered panels. The twelve panels should show the paragraph's internal visual beats, continuity cues, character actions, camera progression, and transition into the next paragraph. Render all storyboard panels with the same ultra-realistic Hollywood science-fiction blockbuster visual language as the short film: live-action photographic realism, cinematic production design, physically plausible materials, sourced lighting, controlled color, and feature-film-grade composition. Do not default to black-and-white pencil, rough sketch, cartoon, anime, game CG, or unfinished concept-art treatment. Do not add dialogue subtitles. The twelve-panel display improves continuity review but never changes the one-paragraph/one-shot/one-video-segment relationship. For projects with a different paragraph count, use the storyboard grid size explicitly required by the current brief or workflow.
6. Present the storyboard for confirmation before expensive video generation. If the user requests changes, revise only the affected assets or paragraphs and keep all other confirmed modules fixed.

## STEP 5: COMPILE PROMPTS AND GENERATE VIDEO

1. Before final video generation, ask the user to choose either a shot 1 preview or generation of all video segments. If preview is chosen, generate only shot 1 and wait for approval.
2. Use MiniMax-H3 by default through the standard video generation path, with each segment at its storyboard duration, 16:9, and the workflow's locked resolution. If the user explicitly selects another model, check its capabilities first and follow that choice when compatible. Pass the character, approved scene four-view, and necessary prop assets in their bound roles; use no more than nine reference images per shot.
3. Use the previous final shot as a video reference only when continuity genuinely depends on its prior action, framing, or camera motion. It never replaces character or scene references.
4. Write prompts in this order: subject/assets, scene/space, visible action and emotion, camera/composition, sourced light and physical medium, locked style, constraints. Use `<<<image_N>>>` placeholders for image references.
5. All non-scene-concept prompts include: no subtitles, no watermark, no text, no cartoon, no anime, no game CG, and no plastic 3D-rendered look. Every video prompt includes no background music and no subtitles, but must not prohibit dialogue by default. When dialogue exists, write the speaking character and exact line while leaving room for performance, lip sync, and environmental sound.
6. Keep the selected style coherent. Do not use neon, high-saturation purple/pink/magenta/blue light pollution, holographic interfaces, cybernetic bodies, or rain-soaked cyberpunk streets as default shortcuts. Alien bioluminescence must be localized, soft, biologically sourced, and limited to its visible organism.
7. If generation fails, retry only the failed segment with a substantive correction for the diagnosed cause, preserving confirmed identity, scene, duration, aspect ratio, and event order. Then switch to another compatible available model if needed; do not repeatedly force the same model or regenerate successful segments.

## STEP 6: ASSEMBLE AND PRESENT

1. Assemble final shots in approved timeline order. Keep paragraph-end and next-paragraph-start continuity through action, gaze, light direction, color, or environmental medium.
2. Use direct cuts, action matches, light continuity, or short environmental sound bridges; avoid unmotivated effect transitions.
3. Grade and sound-design the final piece according to the locked style: mechanical and controlled for deep space, solemn for space opera, dusty and wind-carved for wasteland, or wet and organic for alien ecology. Independent audio may support rhythm and emotion but must not conflict with dialogue or environmental sound.
4. Never add post-production neon pollution, holographic UI effects, cybernetic-body imagery, or rain-night street atmosphere unless explicitly requested.
5. Present the final assembled film and any explicitly requested intermediate assets. Never claim completion until each required output is usable and available in the project canvas.

## STYLE RULES

- Hard-science deep-space exploration: maintainable aerospace structures, practical cabin point lights, worn titanium, reflective spacesuits, instrument displays, cold controlled contrast, and physically plausible floating dust.
- Epic space opera: monumental minimalist/brutalist architecture, vast negative space, solemn natural light, weathered stone, heavy matte metal, protective fabrics, and dry drifting dust.
- Wasteland relic sci-fi: eroded technological ruins, harsh daylight, sand-scattered particles, rusted steel, weathered armor, worn leather, cracked surfaces, and restrained dusty earth tones.
- Alien organic ecology: internally consistent organic architecture, plants/fungi, wet surfaces, translucent veins, water droplets, keratin scales, refraction, and localized biological light.
- Default or custom direction: use the user's confirmed visible rules with realistic materials, sourced lighting, deep blacks, controlled saturation, and legible narrative space. Avoid treating cyberpunk signals as the default definition of future science fiction.

## OUTPUT CONTRACT

Use Markdown headings and fixed module order; do not use tables. User-facing descriptions and all generation prompt bodies are Chinese except the Midjourney V7 scene-concept prompt body, which is English. Keep model names, tool names, asset identifiers, and `<<<image_N>>>` literal. Do not add creator or existing-film names as execution instructions. All decisions are confirmed incrementally; never run the full pipeline automatically after an intermediate checkpoint.
