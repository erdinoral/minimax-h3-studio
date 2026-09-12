# Editing And Source-Video Preservation

Use when editing an existing video or when a video is the base footage.

## Preservation Clause

Start the prompt with a strong source-preservation statement:

```text
@视频1 是待编辑源视频。严格保持 @视频1 的镜头运动、构图、主体动作时序、空间关系、遮挡关系、景深、光照方向、帧率和整体节奏不变。只修改以下内容：...
```

## Replacement Rules

- Name the exact old object and exact new object.
- State where it appears and when it changes.
- Preserve original movement path, occlusion, shadow, reflection, contact, and interaction.
- Keep unedited subjects and regions unchanged.

## Background / AR / World Editing

- Match perspective, ground plane, scale, depth of field, light direction, reflections, edge shadows, motion blur, and parallax.
- Virtual elements must obey real scene occlusion and camera shake.
- For AR/reality augmentation, do not regenerate the full scene unless requested.

## Negative Constraints

Target preservation failures: no source camera change, no altered unedited subjects, no background mismatch, no broken occlusion, no lighting inconsistency, no new watermark, no temporal flicker.
