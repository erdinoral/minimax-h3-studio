# Clarification Routing

Use when the user's request is short, broad, ambiguous, or missing information that would materially change the H3 prompt skeleton.

## Fixed Intake Order

1. Identify the request type.
2. Evaluate whether the text input and provided references satisfy the need.
3. Ask targeted questions, including reference-fit diagnosis and route choices.
4. After the user chooses, write the final prompt in official H3 format only.

## Ask Before Writing When Missing Answers Affect

- subject identity/count/relationship: solo, duo, group, product, logo, scene, recurring character
- reference plan: existing references, generate anchors first, or pure text-to-video
- text layer: no text, title, slogan, lyrics, typography packaging, UI/HUD/menu/exact words
- shot structure: one-take, multi-shot, hard cuts, beat cuts, fixed camera, third-person camera, trailer montage
- rhythm and sound: ambient only, music, beat-sync, rap/lip-sync, dialogue, voice-over
- transformation logic: before-after, outfit change, equipment activation, world loading, reveal, logo morph
- delivery: duration, aspect ratio, platform, cinematic/game/product/short-drama context

If the request is simple, low-risk, and already satisfies the need, skip questions and write the official-format prompt directly.

## Reference-Fit Diagnosis

When references exist, every clarification question must include a concise reference-fit diagnosis:

- sufficient: the reference contains the required identity/layout/UI/text/style/action relationship; recommend direct use.
- partially sufficient: the reference satisfies some dimensions but not all; offer direct-use-with-limits and regenerate/supplement options.
- insufficient: the reference does not contain the required relationship or design; clearly say it does not satisfy the need and ask whether to generate/provide another reference.

Do not use a reference for a role it does not satisfy. Do not pretend missing references exist.

## Question Style

Ask at most 3-5 targeted questions. Prefer multiple choice. Put the recommended option first. Ask only questions that change the prompt structure. If clarification is required, output only the questions and wait; do not include the final prompt yet.

## Type-Specific Menus

- MV/Rap/K-pop/Trap: protagonist count, visual direction, typography level, edit rhythm, music/beat reference.
- Game/UI/HUD: emphasis, exact UI text, character references, camera structure, transformation/world-loading logic.
- Action/Wuxia/Fight: fight scale, action style, weapon, camera, protagonist/action reference.
- Product/Brand/Logo: product reference, selling point, visual direction, logo/slogan text, shot structure.
- Short drama/dialogue: role count, exact dialogue, acting tone, aspect ratio, subtitles, camera style.
- Typography/MG: exact text, text role, style, motion, whether text may occlude the subject.

After the user answers, treat answers as confirmed constraints and write the final prompt in official H3 format only.
