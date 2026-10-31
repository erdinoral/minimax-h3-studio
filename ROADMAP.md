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

## Prioritized backlog

Ordered by impact for a **local, card-based, chapter workflow** (not a cloud credit app).
Each item builds on what already exists — noted under "Builds on".

### 1. Storyboard still → approve → video

**Status:** v1 shipped (Director shot cards)  
**Why:** Cheapest way to catch wrong cast / location / framing before a slow video render.
Competitors (LTX Studio, Flow, Sora storyboard) all gate video behind a cheap frame.

- [x] Per New shot: "Kare üret" queues one Qwen frame (`/api/cinema/shot-frame`, job mode `qwen_frame`)
- [x] Named cards in the shot (cast → craft → set, max 3) go to Qwen Edit as Picture 1..3
- [x] "Onayla" sets the frame as the shot's `first_frame_name`; New video starts from it
- [ ] Chapter Üret option: "only approved shots"
- [ ] Warn when shot text changed after the frame was approved

**Builds on:** Qwen still pipeline (`qwen_still.py`, sheet jobs), shot cards, `first_frame_name`, film-workspace review states (`draft / review / approved`).

### 2. Takes (variants) per shot

**Why:** Generation is stochastic; picking the best of 2–3 beats regenerating blindly.

- "2 take / 3 take" option on shot or chapter produce (different seeds)
- Pick a take → it becomes the shot's selected clip
- Continue children chain from the **selected** take's last frame, not the newest job
- Unselected takes stay in gallery, never feed the chain

**Builds on:** `_latest_job_for_shot_id`, `selected_job` in film project, seed handling.

### 3. Reference cards (pose / motion / costume)

See "Next up" above.

### 4. Shot-to-shot color match on Continue

**Why:** Long Continue chains drift in color / exposure; cuts look like different days.

- Optional post step: match each Continue clip to its parent's last frame
- Toggle per chapter ("Renk eşitle")

**Builds on:** `chain_normalize` / `colour_match` already used inside Multishot packs — extend to per-shot Continue jobs.

### 5. Chapter → one film export

**Why:** Users want a watchable file, not 12 loose clips.

- "Bölümü birleştir": selected takes in shot order → one mp4
- Optional film score / ducking under dialogue
- Then "Filmi birleştir" across chapters

**Builds on:** `/api/cinema/concat`, `/api/cinema/film-plan/concat`, `music.concat_keep_audio_mix_score`. Mostly UI + "selected take" wiring.

### 6. Camera preset chips on shot card

**Why:** Camera language is the most-asked control; typing it is error-prone.

- Chips: Sabit, Dolly-in, Dolly-out, Orbit, Crane up, Handheld, Tracking
- Selection injects a fixed camera line into the composed prompt (not free text)

**Builds on:** structured shot fields / `compose_h3_prompt`, setup "camera" pill.

### 7. Start + end frame for a shot

**Why:** Control where a shot **ends** — chapter transitions, landing a ship, a door closing.

- Optional "bitiş karesi" on a New shot (upload or approved storyboard still)
- Next Continue starts from that controlled end

**Builds on:** FL2VA `last_frame_name` (already in t2v graph), storyboard keyframe mode.

---

## Later

- [ ] Character costume variants as named stills under one character card (UI flow)
- [ ] Clearer scene-card call list (characters / locations / creatures / vehicles / refs)
- [ ] Optional: reference role presets in the create form (pose / motion / costume)
- [ ] Per-shot retry with seed jitter when a job fails or is rejected
- [ ] Time / VRAM estimate before chapter produce (shots × duration × quality)
- [ ] Portable project pack: export/import film JSON + card stills as one zip
- [ ] Subtitles (SRT) from shot dialogue lines on export

---

## Parking lot

- Multi-file reference cards (rejected for v1 — too confusing for the model)
- Auto-LLM writing of complex pose-swap prompts (nice-to-have after manual tokens work)
- Motion brush / regional video inpaint (needs model support H3 doesn't expose today)
- Lip-sync to external TTS (H3 already speaks dialogue natively; revisit if quality demands it)
- Cloud credits / accounts (out of scope — local-first is the product's advantage)
