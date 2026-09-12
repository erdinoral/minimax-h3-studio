---
name: 3d-animation-short-generator
description: |
  Create 3D animated shorts from one-line ideas through briefs, cards, shot tables, storyboards, clips, BGM, and final assembly. Use for stylized story-to-video workflows with audio-safe lip-sync.
trigger-words: [3d animation short, animated short, pixar-style short, story-to-video, cartoon short, lip-sync safe]
---

# 3D Animation Short Generator

Use this Skill when the user wants a complete story-driven 3D animated short workflow, especially a Pixar / Disney / Q-version / motion-graphics style short, from a rough idea to a finished film. Keep durable outputs in production order and pause at creative or high-cost decisions with structured choices for approvals, revisions, model choices, resolution choices, and proceed-or-revise gates.

Video generation defaults to MiniMax-H3. If the user explicitly selects another model, check that model's support for the requested duration, aspect ratio, resolution, references, audio, and motion before following the selection. If generation fails, diagnose the cause, retry once with a targeted correction, then switch to another available compatible model or a post-production route; do not keep retrying the same model. Do not preconfigure or promote a named alternative model.

## STEP 1: Intake and Lock the Core Brief

Confirm the premise, target length, aspect ratio, and audio mode before creating assets. The default 3D-animation audio modes are **silent** and **dialogue-led**; use **narration-led** only when the user explicitly wants a rare first-person narration-driven short and understands it is not the usual 3D-animation pattern.

Capture the story goal, intended mood, platform target, and any required constraints that affect the whole workflow.

## STEP 2: Write the Story Brief and Outline

Turn the idea into a concise project brief.

Then write a story outline that states:
- protagonist goal
- central conflict
- key beats
- emotional turn
- ending payoff

Keep the outline short enough to guide production, but specific enough to support all later shot decisions.

## STEP 3: Build Character and Scene Cards

Create the reusable visual anchors for the film:
- main character card
- supporting character card(s), if any
- transformation before / after cards when the story changes form
- scene cards for each important environment

Character cards should lock identity, silhouette, wardrobe, and any form-changing details. Scene cards should stay environment-only and not mix in character actions.

## STEP 4: Build the Shot Table

Create the fixed shot table after the cards are locked.

The shot table must be written as an actual table, not prose. Shot-table rows must follow one canonical 7-column schema, and the cell order is fixed. Do not rename, merge, or omit columns. Use the following content contract for every row:
- `Shot ID & Duration`: `1 / 0-8s` style only; shot number followed by the total duration window.
- `Continuity Handoff`: the bridge state from the previous shot, then the continuity summary in one compact sentence.
- `Reference Anchors (Spatial + Identity)`: the locked character card(s) + scene card(s) used for this shot.
- `Hook Type`: a short functional label such as hook, reveal, pursuit, reaction, payoff, or emotional beat.
- `Shot Description (Per-Second Directives)`: time-sliced sub-beats such as `0-3s`, `3-5s`, `5-8s`.
- `Audio & Dialogue Track`: the final approved dialogue, speaker binding, and mouth-state note.
- `Audio Mode`: `silent`, `dialogue`, `mixed`, or `SFX`.

Do not convert the shot table into narrative paragraphs, bullet-only notes, or mixed prose. Every shot row must remain table-shaped.

Preferred row serialization example (use this exact table-style row structure):
- `Shot ID & Duration`: `1 / 0-8s`
- `Continuity Handoff`: `金球不在手中；公主从花园入口走向池边并停下；青蛙声线稳定不变；C1 right-side fountain remains the space anchor; C2 no exits; C3 afternoon slanted light from upper right; C4 same afternoon; C5 warm green and rose pink; C6 princess visually stronger than the frog; C7 weak-frame alignment`
- `Reference Anchors (Spatial + Identity)`: `公主角色卡 + 王宫花园场景卡`
- `Hook Type`: `设定钩子`
- `Shot Description (Per-Second Directives)`: `0-3s: ... 3-5s: ... 5-8s: ...`
- `Audio & Dialogue Track`: `公主：... / 青蛙王子：... / Bridge beat: ... / Mouth state: ...`
- `Audio Mode`: `dialogue`


Each shot should include:
- shot number
- duration
- hook / purpose
- scene and character anchor
- spatial continuity note
- final dialogue or action beat
- audio mode
- mouth state or lip-sync note
- prop state
- bridge beat from the previous shot
- voice lock or speaker identity note
- time / light / color continuity note

Rules for the shot table:
- keep a single shot within **5–15 seconds** when possible, but do not force every shot to have the same duration; let the story beat decide the exact length
- if a beat needs more than 15 seconds, split it into multiple shots
- for dialogue shots, use **one speaker per shot**
- if two speakers are needed, split the moment into a reaction-cut sequence instead of putting both into one shot
- lock continuity before generation: prop position, handoff state, stance, voice, form, light, time, and color flow
- budget duration at the shot-table stage first: each row should have enough action, emotion, or information to naturally fill 5–15 seconds; if a row cannot sustain at least 5 seconds, merge it with an adjacent shot or split the beat instead of leaving the fix to later stages.

## STEP 5: Write the Text Storyboards

Expand each shot into a text storyboard section. The storyboard should preserve the same duration plan: each panel must carry enough visible action, emotional change, or dialogue progress to support the planned 5–15 second shot, and any panel that feels too thin should be merged or rewritten before video rendering.

For each shot, rewrite the dialogue verbatim and add:
- the visible action
- the smallest bridge motion from the previous shot
- who is holding what
- where each character starts and ends in frame
- the mouth state and speaker binding
- any reveal, reaction, or transformation beat
- C1 space anchor
- C2 exit state
- C3 light inheritance
- C4 timeline
- C5 color tone
- C6 protagonist-vs-supporting intensity
- C7 weak-frame vs strong-frame choice

Format the storyboard section so these C1–C7 fields are visible in every shot.

Required per-shot storyboard block format:
- `Shot 1 — 0-8s`
- `Character / Scene binding:` the locked character card(s) + scene card(s) used for the shot
- `Purpose:` the shot's story job or hook
- `Final dialogue:` the final approved spoken line(s), if any
- `Bridge beat:` the smallest visible motion that connects from the previous shot
- `Continuity:` then list C1 through C7 explicitly, one line each
- `Panel beats:` 0–3s / 3–5s / 5–8s or equivalent sub-beat timing for the shot's internal action flow
- `Mouth state:` who is closed, who speaks, and when
- `Story function:` the narrative function of the shot

The single text storyboard document must repeat this block format for every shot. Do not collapse the fields into prose or omit the Continuity block.

If the story includes a transformation, keep the before-form and after-form readable as separate identity anchors.

Optional visual storyboard images may be added only when the user wants them.

## STEP 6: Self-Check the Shot Plan

Review the shot table and storyboard for:
- shots over 15 seconds that should be split
- more than one speaker in a single dialogue shot
- missing speaker identity or mouth-state consistency
- broken prop continuity
- missing bridge beats
- form-change continuity errors
- time, light, or color drift

Fix problems before any clip generation.

## STEP 7: Generate Single-Shot Clips

Use MiniMax-H3 by default, or a different model only after the user explicitly selects it and the capability check passes. Generate clips one shot at a time.

Keep the prompt aligned to the locked storyboard and reuse the approved dialogue exactly. Do not invent new lines during clip generation. Make sure the audio mode drives the visual treatment:
- silent: visual storytelling, music, and effects only
- dialogue-led: visible in-scene conversation with lip-sync safety
- narration-led: rare opt-in, used only when explicitly requested

## STEP 8: Assemble and Finish

Assemble the approved shots in order.

Preserve the full approved duration of each shot. During final assembly, do not trim or compress shots just to shorten the film; keep every shot完整 and intact. Add BGM, check smoothness, and confirm that the final cut still matches the locked story, speaker identities, mouth states, props, and continuity chain.

## STEP 9: Final Review

Run a final review for:
- speaker identity correctness
- mouth-state correctness
- prop and handoff continuity
- transformation continuity
- timing continuity
- final audio-mode consistency

Deliver the finished 3D animated short only after the final review passes.
