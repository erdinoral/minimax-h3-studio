---
name: h3-visual-design
description: |
  Create H3 motion-design video using kinetic typography, tracking graphics, or live-action and hand-drawn interaction. Requires a visible moving technique; not for static design or generic animation.
trigger-words: [H3 motion design, kinetic typography, motion typography, tracking graphics, TouchDesigner look, hand-drawn live action, motion packaging]
---

# H3 Visual Design

Treat this Skill as a thin routing entry. The main file only decides the visual technique and carries no concrete style recipes; once a route is chosen, read the corresponding reference on demand — that reference owns setup, prompt, generation, and delivery rules.

## 1. Route selection

| Dominant intent | Route | Required reference |
| --- | --- | --- |
| Add kinetic type, titles, cards, graphics, captions, or AE-style packaging to a person, product, logo, scene, spoken video, or original footage | `typography-packaging` | [typography-packaging.md](references/typography-packaging.md) |
| Produce TD / TouchDesigner / CV debug visuals, tracking frames, topology lines, digital IDs, partial negatives, or "the world as AI sees it" | `td-cv-tracking` | [td-cv-tracking.md](references/td-cv-tracking.md) |
| Produce videos that fuse real living spaces with 2D hand-drawn, doodle, crayon, or chalk animation | `handdrawn-live-action` | [handdrawn-live-action.md](references/handdrawn-live-action.md) |

When TD/CV or hand-drawn fusion intent appears explicitly, enter that route first; all other kinetic type, logo, spoken-word, and material packaging goes to `typography-packaging`. Never guess a route from weak signals like "cool", "effects", or "visual vibe"; when decisive information is missing, ask the user once which technique they want.

One task reads one route by default. When the user explicitly asks to combine two techniques, decide the primary route first, then read only the one additional relevant reference; never preload all routes or merge three rule sets into a single prompt.

## 2. Top-level boundaries

The following intents do not enter this Skill:

| User intent | Destination |
| --- | --- |
| A complete MV driven by music, lyrics, rap, fashion performance, or beat-based storyboarding | `cool-music-video` |
| Advertising driven by brand, product selling points, or commercial narrative | `brand-ad` or `ad-tvc` |
| An anime game PV driven by character awakening, battle, worldview, or gacha events | `anime-game-pv` |
| Evidence-based analysis and shot-by-shot recreation of a reference video | `video-deconstruct` |
| KOC / UGC creator seeding, reviews, unboxing, or product selling | `koc-video` |
| Pure transcription, SRT/ASS, subtitle translation, or motionless subtitle burn-in | general subtitle / post tooling |

Judge by the core result the user wants delivered; never seize other full-category Skills based on a single keyword.

## 3. Shared execution constraints

1. Executed directly by the media agent; do not create a Stage Execution Plan and do not dispatch downstream workers to redesign.
2. Read only the references the chosen route explicitly requires; the route reference is the source of truth for concrete questions, prompt structure, generation method, and completion criteria.
3. Use only attachments, canvas nodes, and user facts that actually exist; never fabricate asset paths, brands, text, personal identities, or reference relationships.
4. Preserve the user's explicit model, duration, aspect ratio, subject, copy, and audio requirements; ask only for missing information that blocks the chosen route.
5. After the route produces the final prompt, the displayed content, the dispatched content, and what is actually sent to H3 must be identical; no downstream summarizing, translating, or rewriting.
6. The route's hard rules take precedence over the generic rules of this entry file; do not deliver until the route passes its own completion checks.
