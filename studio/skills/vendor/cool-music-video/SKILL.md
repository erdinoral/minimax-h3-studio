---
name: cool-music-video
description: |
  Create one 16:9 music-driven short up to 15 seconds from a song, performer reference, lyrics, or style direction. Best for collage, rap, and fashion performance; not full-song or multi-part MVs.
trigger-words: [short MV, music video, rap MV, fashion performance video, collage music video, 15-second MV]
---

# Cool music video

## Entry scope gate

Handle scope before any reference, character, music, or prompt work:

- User explicitly wants a full MV, over 15 seconds, a specific long duration, a full song, multi-segment storyboards, music analysis, or final-cut assembly: exit this Skill immediately and hand over to the MV workflow.
- User explicitly wants an MV / music video of 15 seconds or less: write `scope_confirmed=true` and continue.
- User only says MV / music video generically, or says single piece without a scope: present one confirmation card asking whether to plan a full MV over 15 seconds or a single test piece within 15 seconds. The first choice exits to the MV workflow; the second keeps this Skill for one high-energy short.

If the user picks full MV, exit immediately without reading this Skill's references or asking about characters or music. If they pick the 15-second piece, continue. If the confirmation is cancelled, errors, or cannot be parsed, stop at this gate — never guess a default.

## Style reminder gate

Check style only after `scope_confirmed=true`. The directly executable master template of this Skill is "retro trend collage / zine / rap / fashion performance". Whenever the request mentions any other visual style direction (e.g. Y2K, cyber, futuristic, dark, clean, luxury, vaporwave, lo-fi, editorial) and the user has not already said "fuse it into the retro trend collage" or "just do retro trend collage", add this sub-question to the configuration question flow. Do not ask about anime here — the "visual medium" gate below owns it.

If style handling is the only gap, use one confirmation card; if visual medium, character source, or music content is also missing, make style handling the first item in the same configuration flow. Offer: fuse the user's style into the retro collage skeleton (recommended), use the flagship retro collage look, or insist on a pure external style learned on the fly.

If the user picks "fuse it in", write `style_mode=fusion`; subsequent prompts keep retro trend collage as the skeleton, writing the external style only as localized visual language, without claiming a dedicated style knowledge base. If the user picks the flagship template, write `style_mode=retro_collage_primary` and ignore external style words afterwards. If the user picks pure external style, or before/after the question clearly rejects the template ("no fusion / no retro collage / no papercut collage / pure Y2K only / pure cyber"), write `style_mode=external_pure`, stay in this Skill without switching to the MV workflow — but state that the style is learned on the fly and less stable than the first two options. When the question is cancelled, errors, or the return is unparseable, stop at this gate — never guess a default.

### Writing external-style fusion

With `style_mode=fusion`, never rewrite the external style into a new master template, and never write it as "pure Y2K / pure cyber". Treat it as "retro papercut collage is the structure, the user's style is the surface language":

- Color: convert the user's style into 2–3 dominant colors or light qualities, then land them on paper cuts, overprints, background zones, and type layers. Y2K may use silver-blue, pink-purple, and clear-plastic highlights; dark styles may use black-red, dirty-white paper edges, and desaturated glints.
- Material: keep torn paper, photocopy, halftone dots, overprint, tape, and scan misregistration; the external style only changes the paper surfaces — metallic film, digital screens, glass and plastic, magazine coated stock, or matte black paper.
- Typography: still build readable big English words, action type, and lyric type per Typography Layers A/B/C; the external style only shapes the letterform mood, e.g. Y2K bubble / chrome type, cyber UI type, luxury editorial serif.
- Props and space: place the external style inside the same collage world's props and spatial zones — flip phones, digicams, neon screens, editorial proof sheets, club poster walls, backstage runways — never swap into an entirely different world at random.
- Motion: tears, overprints, frame jumps, and black-frame words are still triggered by vocals, snare, hi-hat, 808, and body movement; the external style only alters the visual result after the trigger, e.g. Y2K starburst stickers popping, cyber scanline glitches, dark ink bleeds.

With `style_mode=external_pure`, do not leave this Skill, but never force the retro papercut collage visual mothership. Keep the Skill's 15-second, single-H3, music-sync, 8–10-shot, verbatim-dispatch, and full prompt structure; learn the style itself from the user's description on the fly — when the user gives only one style word, fill in color, material, type, space, and motion using the model's general understanding. Never claim a dedicated knowledge base for it, and never rewrite it as a retro-collage fusion.

## 15-second pre-gates

Only after `scope_confirmed=true`, check the following three items, folding any unresolved style handling from the reminder gate into the same configuration question flow. When multiple items are missing, run the confirmation card flow once — never fire consecutive cards. Present as one popup / one flow with multiple numbered sub-questions, not everything crammed into one long question; in order:

1. Style handling (appears only when a non-template style was mentioned and not yet chosen)
2. Visual medium (appears when live-action / live-action-plus-anime / pure-anime is not yet explicit)
3. Character source (appears when the protagonist source is missing)
4. Music content (appears when music content is missing)

Each number is a sub-card or sub-question within the same popup / flow, each with its own options; do not merge everything into one long question, and do not pop multiple times. When only one item is missing, still use its numbered header; when several are missing, collect them all at once before reading references. When the user cancels, errors occur, or any required sub-question is unparseable, stop at this gate — never guess a default.

### Visual medium

Passes when the user has uploaded a clear real person, made explicit live-action / photoreal / real footage / fashion performance, made explicit "anime style fused into retro collage", or made explicit "pure anime / pure 2D MV / anime character MV". Exit to `anime-game-pv` only when the user explicitly wants an anime game PV, gacha PV, character promo PV, character awakening PV, or game event PV.

Whenever the sub-15-second short MV is confirmed but the medium is not, add this item to the configuration flow. Offer live-action / photoreal fashion performance (recommended), live-action fused with anime, or pure anime / 2D, with the corresponding constraints described in the option text.

If the user picks fusion, write `visual_medium=anime_fusion` and execute as `style_mode=fusion`; never write the film as pure 2D animation. If the user picks pure anime, write `visual_medium=anime`, continue in this Skill, and write the protagonist as a stable anime character with no requirement of real skin or live photography. When the question is cancelled, errors, or unparseable, stop at this gate — never guess.

With `visual_medium=anime`, keep retro trend collage, music structure, kinetic type, paper tears, overprints, frame jumps, and the 8–10-shot structure entirely; only switch the character medium to anime characters / 2D drawing / cel-shaded or comic-magazine texture. Wherever references mention real photography, real skin, or live-action wording, this gate wins: rewrite as anime character consistency, line-art edges, flat color shadows, paper layering, and print halftones — never exit this Skill for it.

### Character source

Passes when the user has uploaded a clear protagonist, chosen an AI-original character, provided a full written character design, or made clear no character is needed. Otherwise ask only:

- Upload a character reference (recommended): wait for the real image.
- AI-original character: automatically design an avant-garde fashion character, wardrobe, and attitude.

When the person in an image is clear, register it directly; ask which image is the protagonist only when multiple images genuinely obscure it. Missing scene or typography images never block.

### Music content

Passes when the user has uploaded audio, provided lyrics with explicit song intent, made explicit original song / instrumental / no music, or given genre plus vocal form. Otherwise ask only:

- Original song (recommended): H3 generates arrangement, vocals, and a complete micro-song in sync.
- Instrumental BGM: H3 generates the score in sync, no vocals, no lyrics.
- Upload reference music: wait for real audio.

After the choice, do not confirm hook, lyrics, screen words, aspect ratio, or duration again; style and medium follow only the completed gates. Default echo: `MiniMax-H3 | 16:9 | 15s | retro trend collage | live-action photoreal | on-screen text English only`. With `style_mode=fusion` or `visual_medium=anime_fusion`, echo: `MiniMax-H3 | 16:9 | 15s | retro trend collage × user-style fusion | on-screen text English only`. With `visual_medium=anime`, echo: `MiniMax-H3 | 16:9 | 15s | retro trend collage | pure anime characters | on-screen text English only`.

## Conditional reading

Read only after the scope and pre-gates pass:

- All projects: `references/prompt-blueprint.md`, `references/style-guide.md`, `references/methods.md`, `references/typography.md`
- With characters: `references/performance-and-space.md`
- Original song, instrumental, or uploaded audio: `references/music.md`

With `style_mode=external_pure`, still read `references/prompt-blueprint.md` to guarantee the 15-second, 8–10-shot, complete H3 prompt and verbatim-dispatch locks; use `style-guide.md`, `methods.md`, and `typography.md` only as checklists for writing density / shot completeness / type-layer completeness — never force master-template content such as retro papercut collage, torn paper, photocopy, or overprint into the final prompt. The external style itself is learned on the fly from the user's description.

Bind real attachments only per their stated purpose: character images lock identity and styling, scene images lock space and light-color, typography images lock letterforms and layout, and audio gets its real structure read first. Without real attachments, write AI-original; never fabricate paths, nodes, or reference content.

## English visual packaging

On-screen kinetic text in this Skill defaults to **English-only** and does not follow `working_language`. `working_language` applies only to execution notes, user communication, and section headers. Visible hero words, lyric type, action type, margin notes, black-frame words, and Typography `Exact text` are by default extracted from or translated into 3–6 short English words/phrases drawn from the lyrics, title, character state, spatial conflict, and mood; never substitute Chinese screen text for the English packaging, and never generate random small print, fake brands, gibberish, or unrelated slogans. Keep the user's original text only when they explicitly require exact wording on screen.

## Generation and verbatim dispatch

Write the single `final_h3_prompt` per `references/prompt-blueprint.md`. It must fully contain the seven-part structure, the actual music/lyrics or BGM declaration, 8–10 shots, per-shot action–space–camera, Typography Layers A/B/C, Rhythm/Cut, and the global generation locks; target 5700–6500 characters, legal range 5200–6800.

Create exactly one H3 video generation at the end. Music, song, vocals, lyrics, sound effects, and visuals are generated in sync by H3 inside the same video by default; never create a separate music asset unless the user explicitly asks for a standalone audio file.

Show the complete `final_h3_prompt` to the user first, then send the same character-identical string to H3. Do not summarize, shorten, translate, rewrite, reorder, polish, or add text between confirmation and execution.

Before execution verify: both pre-gates passed; real refs match their declared duties; lyrics and voice match the character; at least 8 shots, 4 coherent spatial zones, 5 action families, and 2 design-led shots are present; most text shots carry per-shot Layers A/B/C; the music has variation and a clear ending; the actual character count is legal; the displayed string and the executed string are character-identical. On failure, fix only the current string — never execute a summarized version.
