# MiniMax H3 Studio — Roadmap

Living product notes. Items move from **Idea → Spec → Build → Shipped**.

---

## Now / recently shipped

- [x] Chapter-scoped produce (active chapter only)
- [x] Continue last-frame chain (`mode_locked`, parent after mid-chapter New)
- [x] Vehicles as named assets (spaceship / craft identity on Continue)
- [x] Director LoRA Kaydet (download if missing, then apply)
- [x] Per-shot face/vehicle refs (don’t flood Continues with whole-cast stills)

---

## Next up

### Reference cards (pose / motion / costume)

**Status:** Idea → feasibility check  
**Source:** Community feedback (scene prompting + named refs)  
**Goal:** Let shots call named reference media the same way they call characters / locations.

**Shape (draft)**

- New asset kind: **Reference** (photo or video), one upload per card
- Roles / tags: e.g. pose-start, pose-end, motion, costume
- Prompt tokens like `(reference-pose-start1)` bind to `<Picture N>` / `<Video N>`
- Scene card UI: chips under character/location for refs used in that shot
- Multiple refs = multiple cards (keep one media file per card to avoid model confusion)

**Constraints**

- Prefer New / Ref2VA shots; Continue must keep **previous last frame** as primary continuity
- Respect H3 ref slot limits (~9 images; video slots separate)
- Costume refs complement character cards; they don’t replace face identity locks

**Acceptance (when built)**

1. Create a reference card, name it, upload one still or one video  
2. Mention the name in a shot prompt → produce binds the right Picture/Video tag  
3. Scene summary shows which refs are called  
4. Mid-chapter Continue still chains from last frame (refs don’t steal the canvas)

---

## Later

- [ ] Character costume variants as named stills under one character card (UI flow)
- [ ] Clearer scene-card call list (characters / locations / creatures / vehicles / refs)
- [ ] Optional: reference role presets in the create form (pose / motion / costume)

---

## Parking lot

- Multi-file reference cards (rejected for v1 — too confusing for the model)
- Auto-LLM writing of complex pose-swap prompts (nice-to-have after manual tokens work)
