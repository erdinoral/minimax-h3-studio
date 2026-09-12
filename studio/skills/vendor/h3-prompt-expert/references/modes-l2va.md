# L2VA: Last-Frame Image-To-Video/Audio

Use when one image is the final frame of the target video.

## Required First Line

Put this alignment instruction as the first line of the final prompt, then one blank line:

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.
```

`Shot N` is the final actual shot. `S.SS` is the effective duration with two decimals, such as `15.00-second`.

## Official Body

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

## Description Logic

Use: reasonable prior state → clear movement/change path → final shot converges → exact last-frame landing.

- `<Picture 1>` is not naturally Shot 1; it belongs to the last shot.
- Infer an earlier state that can plausibly evolve into the final image.
- Describe how character, object, camera, scene, light, and composition approach the reference.
- The last moment must land on the referenced final frame without contradiction.
