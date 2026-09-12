# I2VA: First-Frame Image-To-Video/Audio

Use when one image is the actual first frame of the target video.

## Required First Line

Put this alignment instruction as the first line of the final prompt, then one blank line:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

## Official Body

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

## Description Logic

Use: first-frame anchor → action start → continuous change → result/reaction.

- Treat `<Picture 1>` as the exact 0.00-second frame.
- Preserve identity, clothing, colors, key objects, composition, and spatial relationships from Picture 1.
- Start by describing the visible style, subject, composition, and scene anchors in the picture.
- Then describe what begins to move and how the camera or subject develops.
- Avoid contradictions that would require the first frame to be different from the reference image.
