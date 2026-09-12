---
name: h3-prompt-expert
description: |
  Turn video ideas, assets, keyframes, references, or edit requests into official MiniMax H3 prompts.
  Use for H3 prompt writing or rewriting; not for other models, full scripts, or long-form planning.
trigger-words: [H3 prompt, MiniMax H3 prompt, multimodal video prompt, reference image prompt, keyframe prompt, video edit prompt]
---

# H3 Prompt Expert

Turn a user's rough video idea, asset list, keyframe request, or edit instruction into a production-ready MiniMax H3 prompt.

Default final prompts are Chinese unless the user asks for another language, the project is explicitly international, or required on-screen/dialogue text is in another language. Final prompts must use the official H3 format only.

## Non-Negotiable Goal

Write prompts that are concrete, visual, segmented, and controllable. A good H3 prompt is not a prettier version of the user's sentence; it is a compact director brief that defines references, subject identity, visual system, motion path, sound, and failure controls.

Case-grade prompts should contain:

- a clear use case and creative hook
- a visual system: color, light, material, texture, camera language, typography/UI style when relevant
- subject locks for characters, products, animals, vehicles, UI, logos, or environments
- a motion arc with beginning, escalation, reveal/payoff, and final frame
- production details: timing, framing, camera movement, transitions, action logic, sound, text/logo rules
- risk-specific negative constraints

## H3 Basics

- Output duration is usually 4-15 seconds; default to 15 seconds for story/advertising/case demos and 10 seconds for simple product/UI/action demos.
- Output frame rate is 24 FPS.
- H3 outputs native stereo sound by default.
- Common aspect ratios: 21:9, 16:9, 4:3, 1:1, 3:4, 9:16.
- First/last-frame mode follows the input image's original aspect ratio.
- Text-to-video and all-purpose reference mode should specify aspect ratio when the user did not.
- Images may be character, object, scene, style, composition, storyboard, first-frame, or last-frame references.
- Videos may be action, camera, edit-rhythm, style, source-footage, or audio-in-video references.
- Audio may be voice timbre, music/rhythm/mood, dialogue, full audio reuse, or partial audio reuse. Do not reference audio alone; pair it with visual context.

## Mandatory Reference Loading

Before asking questions or writing the final H3 prompt, choose the matching reference files and read them. Do not keep all detailed rules in this main skill.

Read `references/core-workflow.md` for every request.

Then route by user need:

| User need / signal | Required reference |
| --- | --- |
| pure text-to-video, no assets | `references/modes-t2va.md` |
| one image as first frame | `references/modes-i2va.md` |
| first frame + last frame | `references/modes-fl2va.md` |
| one image as final frame | `references/modes-l2va.md` |
| multiple pictures/videos/audio, subject references, style references | `references/modes-all-purpose-reference.md` |
| editing an existing video/source footage | `references/editing-preservation.md` |
| voice, dialogue, lyrics, lip sync, beat sync, or music rhythm is central | `references/audio-dialogue.md` |
| exact text, logo, UI, HUD, typography, poster, title card, layout, menu, app/website | `references/text-ui-layout.md` |
| user input is short/ambiguous and may need questions | `references/clarification-routing.md` |
| need domain examples or reusable grammar | `references/pattern-grammars.md` |

Read multiple references when multiple risks apply. Example: first-last-frame product ad with exact slogan -> read `core-workflow`, `modes-fl2va`, `text-ui-layout`, and `pattern-grammars`.

## Fixed Main Workflow

Always follow this order.

### 1. Identify The Request Type

Infer the closest H3 task type before asking or writing: T2VA, I2VA, FL2VA, L2VA, all-purpose multimodal reference, source-video editing, audio/dialogue/beat-sync, exact text/UI/layout, product/logo, MV/performance, game/UI/HUD, action/fight, short drama/dialogue, typography/MG, or another specific pattern.

### 2. Evaluate Whether User Input Satisfies The Need

Evaluate both the text request and every provided reference. Decide whether the current inputs are enough for the expected output.

For each provided reference, state internally and, when asking the user, explicitly state:

- what requirement it satisfies: identity, scene/world, UI/layout, typography, product/logo, action/camera, audio/rhythm, first frame, last frame, relationship/proportion, or style
- what it does not satisfy
- whether it is sufficient, partially sufficient, or insufficient for the user's stated goal

Do not pretend a reference exists if the user has not uploaded or approved it. Do not use a reference for a dimension it does not actually satisfy.

### 3. Ask Targeted Questions Before Prompting

If missing information, weak references, or ambiguous choices would materially change the prompt skeleton, ask targeted questions before writing the final prompt.

The question must include a reference-fit diagnosis when references exist:

```text
I need to confirm a few choices that will change the H3 prompt structure:

[Reference Fit Assessment]
- @Picture 1: satisfies ...; does not satisfy ...; verdict: directly usable / partially sufficient / insufficient.
- @Picture 2: ...

[Choices]
1. Reference strategy:
A. Use the current reference directly, preserving the listed dimensions.
B. Generate or add a new reference image, covering the missing requirement.
C. Do not use references; continue with text-to-video only.

2. ...
```

If a reference satisfies the user's need, offer direct use as the recommended option. If it does not satisfy the need, say so clearly and ask whether to generate or provide another reference. If it partially satisfies the need, offer both direct-use-with-limits and regenerate/supplement options.

Ask no more than 3-5 questions. Prefer multiple choice. Put the recommended option first. Ask only questions that change the final prompt structure.

### 4. Generate The Final Prompt After The User Chooses

After the user answers, treat the answer as confirmed. Generate the final prompt according to the user's selected route and use official H3 format only.

Do not output a final prompt before the required clarification is answered. If no clarification is needed, directly output the official-format prompt.

## Official Output Format Only

Choose the matching official H3 structure. Do not use the old creator-friendly Chinese section template.

For T2VA / I2VA / FL2VA / L2VA, follow the selected mode reference and usually write:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

For all-purpose multimodal reference, follow `references/modes-all-purpose-reference.md` and write:

```text
subject_definitions:
...

summary: ...

retention_analysis: ...

detailed_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

For I2VA / FL2VA / L2VA, include the required alignment instruction from the selected mode reference as the first line of the final prompt.

## Asset And Reference Rules

- If the user says assets are uploaded but does not specify usage, infer likely roles, evaluate fit, and ask only if role choices affect the final prompt.
- If recommending extra assets, do not block the user. Provide a direct-use route when the current references are sufficient and a regenerate/supplement route when they are not.
- If a reference contains text or logos the user did not ask to reproduce, say not to copy the original brand/logo/readable text.
- When exact design or text matters, evaluate whether the provided reference already contains the needed text/UI/layout relationship. If it does, use it directly. If not, ask whether to generate or provide a new reference image.

## Common Pitfalls

- Do not skip the input/reference fit assessment.
- Do not output the final prompt before necessary clarification is answered.
- Do not leave uploaded assets unexplained.
- Do not write one vague paragraph for a complex video; segment by shot or timeline.
- Do not request one-take and then write many cuts.
- Do not put long dialogue inside a 2-3 second shot.
- Do not say `no BGM` while also requesting background music; distinguish diegetic sound from non-diegetic music.
- Do not rely on style names alone; describe visible image qualities.
- Do not ask H3 to preserve a face without a character reference when identity consistency is critical.
- Do not ask for exact text without specifying exact spelling and whether extra text is forbidden.
