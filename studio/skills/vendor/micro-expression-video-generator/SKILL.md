---
name: micro-expression-video-generator
description: |
  Turn a character image, script excerpt, or emotion cue into timed micro-expression direction and an optional clip. Use for nuanced screen acting; not scripts, rigging, lip sync, or compositing.
trigger-words: [micro-expression, character acting prompt, nuanced emotion performance, character performance, acting prompt, emotional acting, tearful composure]
---

# Micro-expression Performance

Use this Skill when the user wants a character's emotional acting to feel more natural, layered, and cinematic.

## Input Modes

- **Image mode**  a character image to continue from.
- **Script mode**  a script, shot prompt, or storyboard to enhance only the acting layer.
- **Emotion phrase mode**  a short feeling or scene cue.

## References

Use the bundled references for the detailed writing system:

- `references/source-notes.md`
- `references/performance-prototype-library.md`
- `references/emotion-route-library.md`
- `references/muscle-dispatch-library.md`
- `references/video-prompt-guardrails.md`
- `references/tempo-density-guide.md`
- `references/climax-reset-patterns.md`

## Workflow

1. Read the user input and preserve existing character, scene, dialogue, and camera intent.
2. Ask for shot time if missing, then ask for performance intensity if missing.
3. Draft a concise prompt pack and present it for review. Continue to an optional performance clip only after confirmation. Prefer MiniMax H3 because it supports the required image, audio, and acting-control workflow. Honor another user-selected model if it meets the confirmed requirements; if it does not, explain the capability difference and let the user choose an equivalent.

## Boundaries

This Skill focuses on acting prompts and performance direction. It does not replace full scriptwriting, facial rigging, lip-sync editing, or final compositing.
