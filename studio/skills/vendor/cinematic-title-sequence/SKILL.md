---
name: cinematic-title-sequence
description: |
  Create one 15-second film or series title sequence, cast sequence, or concept teaser from confirmed story, exact text, visual references, typography, and sound. Not for full trailers or end credits.
trigger-words: [title sequence, opening titles, opening credits, cast sequence, film teaser, series teaser, concept teaser]
---

# Cinematic Title Sequence

Compile the user-confirmed film proposal, exact text, typography system, shots, transitions, visible effects, and a complete 15-second score into one Chinese prompt directly submittable to MiniMax H3. Defaults: `MiniMax-H3 | 15 s | 16:9 | 2K | 24fps | synchronized music and ambience | bilingual Chinese-English screen text`.

Material is optional. Without material you may propose original fictional characters, worlds, cast, and titles, but all original content must first enter a written proposal for user confirmation; never allude to real celebrities, existing films, existing characters, or protected brands.

## 1. Mandatory flow state

Every new task must start from this state machine; states cannot be skipped:

```text
TRAILER_FLOW_STATE=awaiting_scope
→ returned_to_main_agent (user picks over 15 seconds)
or → awaiting_design (user picks the single 15-second piece)
→ awaiting_reference_scope (when reference images exist)
→ awaiting_reference_scope_custom (only when custom scope chosen and not yet provided)
→ awaiting_proposal_confirmation
→ ready_to_compile
→ ready_to_dispatch
```

Never skip a new task's gates with "the user already mentioned 15 seconds", "you decide", "just generate", or "reuse the defaults". Only redos, style changes, or revisions within the same task may reuse that task's explicitly confirmed scope, language, text mode, and material usage; treat anything unprovably same-task as a new task.

When confirmation card is declined, cancelled, errors, returns nothing, or returns something unparseable, hold the current `awaiting_*` state and stop. Never guess defaults, never continue to the final prompt, never call video generation.

## 2. Gate 1: scope routing

At `TRAILER_FLOW_STATE=awaiting_scope`, the first confirmation card always asks scope only, verbatim:

```text
header: Film scope
confirmation card: Should we first make a single 15-second film to try, or produce a full trailer over 15 seconds composed of multiple clips?
options:
- Single 15-second piece (recommended) | One H3 generation containing multiple shots, exact text, and a full score, delivering one film directly.
- Over 15 seconds / multi-clip full trailer | Exit this Skill and return to the main agent to plan multi-segment generation, editing, and assembly.
```

- Picking `over 15 seconds / multi-clip full trailer`: set `TRAILER_FLOW_STATE=returned_to_main_agent`, tell the user the main agent will continue planning, then exit this Skill; do not continue asking style, language, or text, and do not start H3 generation.
- Picking `single 15-second piece`: record `scope_confirmed=true`, set `TRAILER_FLOW_STATE=awaiting_design`, and enter Gate 2.

## 3. Gate 2: three fixed design questions

At `TRAILER_FLOW_STATE=awaiting_design`, submit the following three questions together in one confirmation card call; never rename them, add or remove top-level styles, or rewrite option meanings ad hoc.

When the user's input already contains an explicit art style, medium, or period look outside the four categories, do not add it as a fifth style or a new reference. First choose whichever of the four is closest in production mechanics to how the main imagery is constructed; before Gate 2, remind and recommend in plain text:

```text
The "[keep the user's words]" you described has no dedicated style entry yet; the closest existing one is "[one of the four]". I suggest borrowing its [shots / 2D or spatial organization / title lock-ups / music structure] and adapting the imagery to the [art traits] you asked for; please confirm below whether to adopt this master style.
```

When nothing is highly similar, say plainly "there is no exact match", still recommend exactly one existing style as the structural template — never list multiple alternatives. This recommendation never answers for the user; Gate 2 must still appear. The four master styles keep fixed names, order, and descriptions; place `(recommended)` only on the current recommendation: cinematic narrative when no extra style is requested, otherwise the nearest match.

```text
question 1
header: Master style
confirmation card: Which primary visual vehicle should this 15-second title or teaser use?
options (fixed order; put the "recommended" marker only on the current recommendation):
- Cinematic narrative | A live-action or photoreal film world driven by character action; text enters real negative space such as sky, walls, roads, and car windows.
- Live-action motion-graphics composite | Keeps real people and cities/architecture; multi-window layouts, kinetic type, glass refraction, line particles, and spatial captions carry the main rhythm.
- Constructed-world VFX | Impossible physics, miniature models, or abstract spaces star; giant anomalies, particle media, and epic type form the spectacle.
- Editorial collage packaging | Paper, photos, cutouts, magazines, diaries, maps, or film stock form a high-density kinetic layout that resolves into a movie poster.

question 2
header: Screen language
confirmation card: Which language should the title, character cards, and credits use?
options:
- Bilingual Chinese-English (recommended) | Chinese as the primary layer, English as the secondary; two letterform systems designed separately sharing one layout relationship.
- English only | All readable titles, character cards, and credits use English only.

question 3
header: Text content
confirmation card: Which exact text should appear in this 15-second film?
options:
- Basic film cast (recommended) | Title, director card, 2–3 lead name cards; each name card has a primary title plus a role/English-name/STARRING subtitle.
- Basic cast + one story hook | Adds one short line directly matched to visible story beats on top of the basic cast.
- User-provided exact text | The user supplies titles, names, roles, credits, or lines; until complete, only draft the proposal — never dispatch.
```

Once all three results are valid, record:

```text
design_confirmed=true
PRIMARY_STYLE=[one of four]
SCREEN_LANGUAGE=bilingual_cn_en | english_only
TEXT_CONTENT_MODE=basic_cast | basic_cast_plus_hook | user_exact
```

If the confirmed request contains an art style not covered by existing references, immediately produce an `AD_HOC_STYLE_SUMMARY` serving only the current task — never save it as a new style or new reference:

```text
AD_HOC_STYLE_SUMMARY
user_style_exact=[user's words]
template_style=[the confirmed one of four]
visual_traits=[canvas/material; line/shape; color/light; composition/space]
motion_traits=[how subjects move; how the camera moves; how transitions inherit]
title_traits=[the title's letterforms, material, position, and reveal]
audio_traits=[music mood, 2–4 timbre anchors, ambience/action sounds]
avoid=[the styles, materials, filters, or technical effects most easily mis-generated against the user's request]
```

The summary must convert style names into traits H3 can see and hear — never just repeat "Chinese-style, retro, premium, artistic". Existing references keep supplying prompt structure, rhythm, shots, transitions, type hierarchy, and music completeness; the `AD_HOC_STYLE_SUMMARY` owns only the current project's visual surface and exclusions. When the user re-picks the master style, re-summarize against the new template.

- One or more reference images exist: set `TRAILER_FLOW_STATE=awaiting_reference_scope`, enter Gate 3.
- No reference images: record `REFERENCE_SCOPE_MODE=not_used / reference_scope_confirmed=true / SEQUENCE_MODE=multi_scene`, set `TRAILER_FLOW_STATE=awaiting_proposal_confirmation`.

## 3A. Gate 3: reference-image scope

Whenever the current task has reference images, at `TRAILER_FLOW_STATE=awaiting_reference_scope` you must present a confirmation card once, separately; never choose for the user based on image content, the user saying "just reference it", or historical defaults. Verbatim:

```text
header: Reference usage
confirmation card: How tightly should the reference images constrain this piece?
options:
- Reference the people and grade (recommended) | Lock character identity, wardrobe, color, light, and cinematic texture; the original environment becomes just one scene of the film, with other scenes actively diverging within the same worldview.
- Strictly keep the original scene and people | The whole film uses only the people and the single location in the reference, adding no locations; framing, camera position, action, light, and effects may still vary.
- Custom reference scope | You specify which of people, wardrobe, props, scene, color, and composition must hold and which may diverge.
```

- Picking `reference the people and grade`: record `REFERENCE_SCOPE_MODE=identity_grade_one_scene / reference_scope_confirmed=true / SEQUENCE_MODE=multi_scene`. Character identity, main wardrobe traits, and color grade may run throughout; the original environment must map to one explicit scene used exactly once, with at least two additional distinct locations/action conditions; the original blocking and composition are not auto-locked.
- Picking `strictly keep the original scene and people`: record `REFERENCE_SCOPE_MODE=strict_same_scene_people / reference_scope_confirmed=true / SEQUENCE_MODE=single_scene_locked_reference / single_scene_user_confirmed=true`. Never add locations or replace people, but form at least three distinguishable states via different action phases, framings, camera positions, fore/mid/background, light, and sourced effects — never stretch a static image into a fifteen-second slow push.
- Picking `custom reference scope`: record `REFERENCE_SCOPE_MODE=user_defined`, set `TRAILER_FLOW_STATE=awaiting_reference_scope_custom`, ask in plain text for item-by-item `locked / divergeable` ranges across people, wardrobe, props, scene, color, and composition, then stop. After receiving explicit ranges, restate the mapping first, record `reference_scope_confirmed=true`, then set `SEQUENCE_MODE=multi_scene | single_scene_locked_reference` per whether new locations are allowed.

When reference images are uploaded, replaced, or added after Gate 2, enter or fall back to Gate 3; after the reference scope changes, redo the story confirmation draft. After Gate 3 passes, set `TRAILER_FLOW_STATE=awaiting_proposal_confirmation`.

## 4. Proposal first, generation second

Only after `reference_scope_confirmed=true` may you enter `awaiting_proposal_confirmation`. Here you neither present a confirmation card nor produce the final H3 prompt. Before writing the confirmation draft, determine `OUTPUT_MODE` and the primary route per section 5, and immediately read:

1. [case-calibration-matrix.md](references/case-calibration-matrix.md)
2. one reference for the chosen master style
3. [cinematography-and-transitions.md](references/cinematography-and-transitions.md)

Choose the single `primary_calibration` from validated cases, then write material duties, scene expansion, character actions, and transition landings into the proposal. Never draft a single-scene proposal from one reference image and only read the cases and transition library after the user confirms. How the reference enters the film obeys only Gate 3: by default it is one scene used once, never automatically placed at the opening, ending, or throughout; only strict-original-scene mode may keep the whole piece in one location.

When an `AD_HOC_STYLE_SUMMARY` exists, prepend a `style adaptation` item to the draft: which existing template is recommended, the summarized core visible traits, and which conflicting effects are explicitly excluded. The user confirms the combination of "existing template structure + this task's style summary", not a new style.

Then give the user a short, concrete confirmation draft in plain chat text, which must include:

1. `Material usage`: per image, its Gate 3 choice, the visible anchors to keep, and the allowed expansion; default mode must state which single scene the original environment lands in and which locations diverge; strict mode must state no new locations; custom mode restates the user's boundaries item by item.
2. `15-second story/title plan`: in time order — subject, trigger or character task, action, escalation, ending landing; an Opening Title must also state through what action the characters become known.
3. `All exact on-screen text`: per card — Chinese, English, casing, line breaks, and appearance order; without a story hook, never hard-code a line.
4. `Text hierarchy`: per card — primary title, subtitle, and utility; character cards default to the name as primary with English name, role, or `STARRING` as secondary.
5. `Type direction`: skeleton contrast and main materials for Display A, Display B, and Utility — never just "premium, cinematic, modern".
6. `Scene expansion and transition landings`: `multi_scene` lists at least 3 at-a-glance distinguishable locations/layouts with action/effect conditions, of which the default reference environment takes only one scene with at least two new locations; list at least 2 chains of "visible source in prior shot → cut point → inherited item → new landing in next shot". `single_scene_locked_reference` lists at least 3 action/scale/light states within one location plus 2 internal transitions. These are action-condition counts, not mandated shot counts.
7. `Camera and transition motifs`: 2–4 definite devices that will run through the film, e.g. lateral tracking, match on action, foreground occlusion, shape match, sound bridge; never list alternatives.

Every "new scene" in the draft must simultaneously change the location/layout plus at least one of character task, action outcome, world scale, or effect state. The same seaside boardwalk with a different framing, continued walking, continued eye contact, or only a different sky color is not multi-scene expansion; those serve only as internal states of one scene when the user explicitly chose strict-original-scene.

Titles, character names, director names, roles, story, and lines proposed by the agent are all labeled "original proposal". The user may change anything. On requested changes, update the whole draft and remain in `awaiting_proposal_confirmation`.

Only after the user unambiguously agrees — "confirmed", "OK, start generating", "go with this", "dispatch it" — record `proposal_confirmed=true` and set `TRAILER_FLOW_STATE=ready_to_compile`. Never treat silence, questions, partial approval, a failed confirmation card, or "let me see first" as confirmation.

## 5. Output mode and the four routes

Choose exactly one `OUTPUT_MODE`:

| Mode | Trigger | Core goal |
| --- | --- | --- |
| `opening_title` | opening titles, cast, Opening Title, Opening Credits, Title Sequence, actor-name PV | Film world and visual identity first; cast, typography, spatial relations, and the final title form a complete title sequence |
| `single_clip_trailer` | teaser, concept teaser, pilot teaser, trailer | Causal story and selling points first; viewers can grasp the subject, change, action, escalation, and the unresolved question |

Choose the single primary route per Gate 2's fixed style:

| Master style | Route | Required reading |
| --- | --- | --- |
| Cinematic narrative | `cinematic_narrative` | [cinematic-narrative.md](references/cinematic-narrative.md) |
| Live-action motion-graphics composite | `live_action_graphics` | [live-action-graphics.md](references/live-action-graphics.md) |
| Constructed-world VFX | `constructed_world_vfx` | [constructed-world-vfx.md](references/constructed-world-vfx.md) |
| Editorial collage packaging | `editorial_collage` | [editorial-collage.md](references/editorial-collage.md) |

Subject-matter words never rewrite the primary route. On a style change, hard-lock only the user's actually provided premise, `user_exact` text, uploaded identity/brand assets, and rights boundaries; agent-invented scenes, palettes, type, shots, transitions, and music are rebuilt per the new route, and the proposal is re-sent for confirmation.

## 6. Material and confirmed facts

After detecting attachments, first run read-only analysis with media analysis for content, shots, text, color, and sound. Media-analysis requests must extract verifiable facts only: character identity and wardrobe, location elements, palette, light, existing text, compositional hierarchy, and visible action; never let the analyzer decide the reference scope, design slow pushes / lateral moves / same-scene extension for the whole film, or have its creative suggestions treated as confirmed facts. The reference scope is decided only by Gate 3.

Reference images bind duties per the Gate 3 preset, never a vague "reference everything": default mode allows the three contributions `character identity/wardrobe + color grade + one scene` but forbids locking whole-film composition; strict mode locks the people and the single location; custom mode uses only the user's whitelist. Video and audio still get exactly one `primary_role` each — `motion` or `audio_rhythm` — plus one optional secondary contribution. Prompts use `@image1/@video1/@audio1`, never local paths.

Under `identity_grade_one_scene`, no matter how poster-like the still is, character identity, main wardrobe traits, palette, and light texture may run throughout, but the original environment, blocking, and composition land only in the one scene the story plan designates; other scenes keep the same people and grade while changing location and action conditions. Only `strict_same_scene_people` locks the original scene and people for the whole film; `user_defined` follows the user's item-by-item whitelist strictly.

Build an internal record of the output mode, source assets, reference scope, confirmed premise, identity anchors, style evidence, exact confirmed text, screen language, and audio reference. In the same record, note the selected reference mode, locked anchors, allowed expansion, reference scene and usage, and whether composition is locked.

Without material, use only the user-confirmed original proposal. Never add characters, romance, partings, old letters, secrets, disasters, time spans, place names, numbers, or heavy backstory after confirmation.

## 7. Text content per the chosen mode

- `basic_cast`: 1 title, 1 director card, 2–3 lead name cards; no quota of story lines.
- `basic_cast_plus_hook`: adds exactly 1 confirmed story hook verifiable by the imagery on top of `basic_cast`.
- `user_exact`: uses only the user-confirmed exact text; when it cannot form the requested cast structure, return to the proposal stage to complete it — never guess-write.

Every name card uses a primary/secondary structure: the name as primary; the secondary picks one or two confirmed items from the English name, the role, and `STARRING`. The director card likewise separates the name from a `DIRECTED BY / 导演` secondary. The final title adds no further character names.

Build a `TITLE_BIBLE` and `TEXT LEDGER` internally, locking Chinese, English, casing, line breaks, roles, appearance order, and provenance verbatim. Default bilingual means a Chinese primary + English secondary within one semantic group; English-only keeps English alone. No readable text absent from the confirmation draft may enter the prompt.

## 8. Reference reading discipline

At `awaiting_proposal_confirmation`, before writing the proposal, read:

1. [case-calibration-matrix.md](references/case-calibration-matrix.md)
2. one reference for the chosen master style
3. [cinematography-and-transitions.md](references/cinematography-and-transitions.md)

After user confirmation, at `ready_to_compile`, read:

1. [h3-prompt-contract.md](references/h3-prompt-contract.md)
2. [typography-and-credits.md](references/typography-and-credits.md)

Reuse already-read content within the same task while files are unchanged. After a style or proposal change, re-read only the changed style reference, but the proposal must be re-confirmed.

## 9. Typography and camera compilation hard gates

The final prompt must fully expand the `TYPE PROGRAM` — never just "premium, clean, modern, cinematic type":

```text
Display A / Display B / Utility / Marks
→ each with skeleton, width, weight, tracking, terminals/strokes, counters, material, color, scale, spatial position, motion process
→ every exact text card mapped to exactly one type role
→ scale ladder / COLOR SCRIPT / GRAPHIC KIT / SPACE BINDING / motion cue
```

Every text card spells out `trigger → build/reveal → complete → reading hold → one response → exit or inheritance`. Display A, Display B, and Utility contrast in at least two visible traits; Utility is not a proportional shrink of Display A.

Every main shot must be completed internally and rendered in the final prompt as natural Chinese:

```text
camera_origin | size_and_lens | path_axis | foreground_pass | subject_action | endpoint | story_gain | transition_source | cut_point | inherited_item | next_landing
```

One primary camera move per shot. If the final prompt contains undecided phrasing — "lateral or slow push", "may use", "optional", "suggested", "for example", "and similar" — then `camera_plan_complete=false` and dispatch is forbidden. The film must cover at least three camera functions among establishing reveal, action following, evidence approach, and scale release, and commit to 2–3 transition families among match on action, shape match, foreground occlusion, and sound bridge.

Complete the `TRANSITION SCORE` during camera compilation — no separate validation round. Only when 2–3 definite transition families are actually written in and at least two cross-shot transitions each specify `visible source → covering/action cut point → inherited item in the next shot → new location/new action condition/new subject/title space` may you set `transition_plan_complete=true`. Changing framing on the same background, continued walking, or continued eye contact does not count as a valid transition; naming device families alone does not either.

## 10. Compile, verify, and the dispatch lock

1. Use the latest capability summary to confirm MiniMax H3's legal mode, duration, aspect ratio, 2K, audio, and reference slots.
2. Reuse the pre-confirmed material `reference_scope`, the single `primary_calibration`, `SEQUENCE_MODE`, and the single mothership; inherit the validated case's prompt structure, cinematography, type relations, effect chains, transition seeds, and music completeness. With an `AD_HOC_STYLE_SUMMARY`, fill its visible traits and exclusions into the same template — no separate prompt, no new reference, and never let the case's default surface style override the user's words. Never first choose calibration after confirmation, and never collapse a multi-scene plan back into the reference's single scene.
3. Write the Chinese `final_h3_prompt` per [h3-prompt-contract.md](references/h3-prompt-contract.md). The final prompt keeps only natural language H3 can directly see, hear, and execute.
4. Hard range `5000–7000` characters, target `5600–6500`. Count once after the first full draft; when out of range, exactly one deterministic trim then one recount. No third estimate, no back-and-forth rewriting, no live-streaming counts to the user.
5. Before dispatch, all of the following must hold explicitly:

```text
scope_confirmed=true
design_confirmed=true
reference_scope_confirmed=true
proposal_confirmed=true
prompt_length=5000..7000
type_program_complete=true
camera_plan_complete=true
transition_plan_complete=true
TRAILER_FLOW_STATE=ready_to_dispatch
```

If any item fails: hold or fall back to that state and say which item is missing; never call video generation. This check is a hard precondition of video generation — no exemption for user urgency, the generator accepting short prompts, or a previous successful generation.

6. Keep one internal dispatch check inside this Skill: the seven confirmation/compilation states must be true; record the single `primary_calibration`, reference scope and sequence mode, reference scene and usage, and the draft's distinct visual conditions and transition landings. In default mode, if the reference environment is not mapped to exactly one scene, repeats through the film, or has fewer than two divergent new locations — or in strict mode, if the user did not actively choose it — hold `ready_to_compile` and stop; never enter dispatch.
7. Display the locked single prompt in full, and send it directly through the video generation in the same assistant turn; never route it through a second writer, summary, or temporary file.
8. Keep the confirmed model, duration, aspect ratio, resolution, native sound choice, and ordered material bindings unchanged between the confirmation and execution.
9. For a retryable execution-validation error, complete only the missing capability detail and resend the character-identical prompt with the same material order and settings. Never drop proof items, invent a success signal, or switch routes to bypass the error. While generation is running, tell the user plainly that it has been dispatched and is generating.
10. After completion, verify the effective model, resolution, duration, aspect ratio, audio, and material bindings, then deliver.

## 11. Final quality hard gates

- Did Gate 1 actually appear; on over-15-seconds, did it return to the main agent immediately?
- Did Gate 2 present the fixed four styles, bilingual/English, and the three text modes together at once?
- For out-of-category styles: was the reminder given with exactly one nearest existing style recommended; was a task-specific concrete style summary produced while using the existing prompt template, with no new style or reference?
- With reference images, did Gate 3 actually appear; were default, strict, and custom scopes executed as chosen?
- Was the story-and-exact-text confirmation draft sent first and explicitly confirmed?
- In default mode, does the reference lock only people/wardrobe/grade and occupy exactly one scene while diverging to at least two new locations; was strict mode genuinely user-chosen; were custom boundaries implemented item by item?
- Does screen text strictly follow `TEXT_CONTENT_MODE`, with no story lines, numbers, place names, or relationships hard-coded for density?
- Does every character card have a name primary and a role/English-name/`STARRING` secondary?
- Does cinematic narrative go by complete performances and meaningful scene changes without forced shot counts; do the other three routes have at least 5 distinguishable environments/scales/layouts, with 4–6 primary effects and 8–14 supporting effects?
- Are the TYPE PROGRAM, three-step scale ladder, color script, graphic kit, space binding, and per-card motion fully expanded?
- Does each shot have exactly one definite camera move with origin, path, foreground, action, endpoint, story gain, and transition landing?
- Do at least two cross-shot transitions specify source, cut point, inherited item, and new landing, truly entering a new location, action condition, subject, or title space rather than reframing the same background?
- Does the internal dispatch check match the confirmation draft item by item; when unmet, did execution genuinely stop inside the Skill without starting the generation step?
- Does the music lock only style, mood, 2–4 timbre anchors, and a complete energy arc, letting H3 compose freely, with an opening motif, build, climax, and a definite ending?
- Was `final_h3_prompt` counted at most twice, within 5000–7000, and identical to the string actually dispatched?

## 12. Delivery boundaries

This Skill generates only the current single 15-second film; it creates no Stage Execution Plan, enters no downstream workers, auto-generates no extra versions, auto-edits no long footage, and never auto-restarts Electron. Over-15-second tasks return to the main agent; redos of the same 15-second task reuse confirmed gates, but any change to story, exact text, or master style requires re-sending the confirmation draft and waiting for confirmation.
