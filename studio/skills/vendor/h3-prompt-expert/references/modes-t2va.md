# T2VA: Text-To-Video/Audio

Use when the user provides no image/video/audio assets.

## Official Format

T2VA has no image alignment instruction. Start directly with the three body fields:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

## Writing Rules

- Build the full audiovisual timeline from text.
- `[Shot 1]` starts with the overall style and initial framing; do not add a timestamp to Shot 1.
- Subsequent shots use increasing cut times inside the total duration, e.g. `[Shot 2] At 00:03.500, the camera cuts to...`.
- Every detail should be visible or audible: style, framing, subject appearance/location, props, action, camera movement, dialogue/singing, text, scene sounds.
- If the user asks for one-take, avoid shot lists and describe continuous phases.

## Creator-Friendly Alternative

For ordinary users, the Chinese section format is fine. Still keep the timeline concrete and include sound/negative constraints.
