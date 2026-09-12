---
name: handdrawn-live-video-generator
description: |
  Create a surreal 15-second 16:9 short blending rough glowing hand-drawn animation with live action. Clarify the contact object or hand, mood, language, and style; design continuous morphing, an escape route, and delayed handheld pursuit; then write the prompt in the user's language and generate with H3 after approval. Check contact realism, camera delay, rough stroke texture, and a non-horror tone. Use for single scenes, not polished CG, jump scares, plush characters, or multi-scene cuts.
trigger-words: [hand-drawn glowing animation fusion, 15-second morphing chase video prompt, H3 video generation, video prompt, hand-drawn animation touching real objects, crayon-chalk texture, multilingual video prompts]
allowed-tools: [question, hub_generate_video, hub_analyse_media, hub_save_file_to_session]
---

# Handdrawn Live-Action Fusion Video Generator

Use this Skill when the user wants a **finished 15-second, 16:9 live-action-and-hand-drawn fusion video**. The output must preserve the structure: a flat hand-drawn luminous animation appears in a real space, clearly contacts live-action hands or objects in the first 0-3 seconds, continuously morphs as one single entity, escapes, and a handheld phone camera follows slightly late.

This Skill **organizes the prompt in the user input language and recommends MiniMax H3 as the confirmed generation step**. Do not generate video until the user explicitly confirms H3 generation. Do not route to planner or executor for prompt-writing. The final prompt language must follow the dominant language of the user input: Chinese input produces Chinese, English input produces English, Japanese input produces Japanese; for mixed input, use the dominant language; when unclear, use the current conversation language. Only user-required proper nouns, model names, or literal parameters may remain unchanged.

## Step 1: Understand the user intent as same-language constraints

When the user provides any language, understand it as the following workflow requirements and express the final prompt in the dominant language of the user input:

- Create a brand-new 15-second video-generation prompt from the reference prompt, without superficially imitating its wording.
- Preserve the image structure: a flat hand-drawn glowing animation appears in a live-action space; it touches a real hand or real object; the same entity continuously morphs and escapes; the camera always chases slightly late.
- The hand-drawn animation must feel like crayon, chalk, colored pencil, pastel, or rough brushwork; lines should wobble slightly with uneven smears, rough edges, and frame-by-frame redraw feel.
- Ban 3DCG, plush-toy feeling, even vector lines, smooth neon, horror monsters, giant eyes, gashes, teeth, intimidation, lunging bites, sudden black screens, and jump scares.
- 0-3s must show clear contact between the live-action hand and the hand-drawn animation, such as wrapping around fingers, landing in a palm, fleeing when grabbed, or being born from a fingertip.
- The animation must continuously morph as the same entity, changing among lines, creatures, symbols, plants, vehicles, or everyday objects while preserving traces of the prior form.
- Do not suddenly introduce a second new character.
- The whole piece must unfold continuously within one space or adjacent connected areas, without cutting to another location, as if the camera operator is really walking and chasing it.
- Each interval, 0-3s, 3-6s, 6-10s, 10-13s, and 13-15s, must introduce a new morph, move, contact, discovery, prank, or surprise.
- The camera operator must also participate: reaching, grabbing, chasing, opening a door or box, catching, stepping back, or being pranked.
- The tone should be cute, everyday, nostalgic, gentle, and slightly bittersweet, not horror comedy.
- 13-15s must include a space-scale transformation: the earlier line spreads to the wall, floor, ceiling, window, sink, or corridor and becomes a giant flower, starry sky, sunset, cloud, ribbon, or doodled little town; end with a warm emotional afterglow and a small cute joke.

## Step 2: Invent all creative content fresh

For every run, create a new combination. Do not reuse the reference prompt's dark room, PC, fridge, stars, hearts, blue vortex, butterfly, snake, octopus, hamburger, giant eye, teeth, or dark ending.

Choose new values for all of these:

1. A live-action space that still feels everyday and stays within adjacent areas that can be tracked continuously;
2. The hand-drawn entity or initial form;
3. The core color;
4. The continuous morphing chain;
5. The contact method with the real hand or object;
6. The chase route through the space;
7. The camera operator reaction;
8. The final space-scale transformation and cute joke.

Good example directions include: rainy kitchen sink, old balcony clothesline corner, morning entryway, small bookstore hallway, train-window table, bathroom mirror cabinet, craft table, greenhouse corridor, laundromat bench, old dining table. Use only one or adjacent connected areas.

## Step 3: Required output format

The final prompt must begin with a sentence pattern matching the dominant language of the user input. For Chinese input, use this pattern:

`15 seconds, 16:9 landscape video. Blend the live-action scene with hand-drawn glowing animation.`

Replace “〇〇” with the newly invented live-action space or everyday scene. For non-Chinese input, use an equivalent opening in the same language and include duration, 16:9 landscape format, live-action space, and hand-drawn glowing animation fusion.

Do not add titles, auxiliary headings such as stage setup or color tone, or explanatory notes. Keep this paragraph order:

1. opening line；
2. live-action space and phone-shot feel；
3. 0-3s；
4. 3-6s；
5. 6-10s；
6. 10-13s；
7. 13-15s；
8. hand-drawn texture；
9. camera follow style；
10. prohibitions；
11. ambient sound。

## Step 4: Prompt writing rules

- Keep the prompt executable as a video-generation prompt, not an essay.
- Unless the user asks for explanation, the final answer should contain the prompt text in the dominant language of the user input first, followed by one short next-step recommendation in the same language.
- The recommendation must invite the user, in the same language, to use MiniMax H3 to generate a 15-second 16:9 video from this prompt. Chinese example: `Next step: if you confirm this prompt, I can continue with H3 video generation for a 15-second 16:9 video.`
- Do not generate a video, image, audio, storyboard, or intermediate asset until the user explicitly confirms MiniMax-H3 or another model they have explicitly specified.
- The default model is MiniMax-H3. If the user explicitly specifies another model, follow the user's choice after a capability check. Do not add model parameters inside the creative prompt unless requested. If the user-specified model fails, allow at most one targeted retry, then switch to MiniMax-H3 or another available model instead of repeatedly retrying the same model.
- The first 0-3 seconds must make real/hand-drawn fusion obvious through contact.
- The camera must not neatly center the animation. It should lag behind, pan/tilt/advance after the entity already leaves the frame edge.
- The entity should remain traceable: each new form preserves a line, tail, color smear, body curve, or motif from the previous form.
- Use soft, emotional, comic, cute beats: tiny stumbles, shy gestures, a dot falling behind, a petal sticking to lens, a star dropping into a palm, confetti sneeze, one small creature lagging behind.
- Avoid any horror-coded anatomy or threatening motion.
- The final prompt must not randomly mix in vocabulary, transition sentences, or writing systems from outside the user input language; when the user input language is Japanese, natural Japanese is allowed.

## Step 5: Delivery

Output the final prompt in the dominant language of the user input first. After the prompt, add exactly one short same-language recommendation line inviting the user to continue with MiniMax H3 video generation. Do not include a title, checklist, model call summary, filename, or canvas delivery note. If the user later confirms H3 generation, generate the 15-second 16:9 video with MiniMax H3 and check that the result preserves contact, continuous morphing, delayed camera chase, and non-horror hand-drawn texture.
