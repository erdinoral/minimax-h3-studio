# Continuum update — announcement draft

Continuum in H3 Studio now offers an ON/OFF switch, a single prompt repeated across sections, or a separate prompt card for each section.

New continuity controls include shared character/setting text and Balanced (22 prior frames) or experimental Strong (39 prior frames) context. Continuing preserves the original prompt prefix, shared context, transition preset, seed and model settings. The interface shows existing duration plus new duration.

We fixed an important integration issue: Spectrum's mutable runtime was preventing safe saved-section reuse and could cause earlier sections to regenerate. Continuum now bypasses Spectrum; it remains available for ordinary native H3 clips. Older Spectrum-enabled Continuum runs are rejected for native continuation instead of silently rerendering them. Originals remain preserved.

Validated with Studio Draft settings (480p, 5 seconds, 12 steps): a five-second clip was extended to ten seconds using the saved first section. Native storage confirmed prefix reuse; inspected first and middle prefix frames were identical, with a small difference near the join. Both colored stickman fighters remained in the scene and the next section moved into combat.

Balanced remains the default. Strong context was not consistently better in the earlier comparison. Character details, motion, lighting and camera continuity can still drift. Audio quality and long-run stability need further evaluation. This is experimental, and examples and feedback are welcome.
