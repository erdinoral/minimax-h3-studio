# Production reliability roadmap — 2026-10-18

## Evidence and review rules

Repository AGENTS snapshot: inspect logs before fixes; preserve app/launcher separation; keep existing user changes; validate changes with relevant tests. Scope is Studio application code and documentation. No launcher scripts, dependencies or downloaded models will be changed, so launcher destination/example requirements do not apply. Read logs/api/start.js/latest and ComfyUI logs. Preserve the paused film production, its files and settings; do not resume it for code verification.

Official sources reviewed:

- https://github.com/MiniMax-AI/MiniMax-H3 — base generation, reference modalities, separate hosted Context-IR / regeneration stages.
- https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/ref-en.txt — distinct identity subjects, concrete frame anchors, video continuation, ordered scene state and audio roles.
- Installed Continuum implementation and native docs — same-run video/audio context differs from an independent job's last-frame handoff.

Do not equate local native 1088 generation with the hosted regeneration pipeline. Do not equate a valid graph or a character still with successful motion. Do not impose arbitrary prompt-length limits: official guidance calls for explicit descriptions; remove redundant authoring text without deleting distinct beats.

## Implementation order and acceptance

1. **Completed/cancelled correctness (#28).** Identify cancellation provenance; target Stop to the jobs present when requested, never a successor that starts during the HTTP call. Recover legacy cancelled records only from confirmed successful Comfy history with a saved video, never from the presence of a possibly partial file. Explicitly cancelled jobs remain cancelled. Tests must cover races and incomplete history. This does not establish the reporter's exact cause or resolve visual drift.
2. **Bounded reference cost.** New Continuum jobs default to Match Output; retain Max Identity as an explicit validated API option. Retain stored job choices. Expose the actual handoff method and chunk count in job records. Keep same-run multi-chunk production available; never claim last-frame handoff transfers motion/audio history. No resolution, step or Spectrum changes on existing jobs.
3. **Prompt fidelity.** Avoid repeating an action verbatim as chronological beats; preserve different beat text and round-trip authoring fields. Do not rewrite existing saved films automatically.
4. **Hybrid availability (#21).** Verify existing filename handling; support model subfolders with their relative loader paths. Keep incomplete/unknown weights disabled. Selection must update both graph families and preserve encoder/VAE choices. Do not download large models silently or call issue resolved without reporter confirmation.
5. **Pause (#19).** Existing pause-after-current is useful, but not mid-sampler suspension and does not reclaim resources until the active job finishes. Expose truthful capabilities; retain issue open. Do not simulate pause with interrupt or promise resumability unsupported by the engine.

## Design self-review

Accepted: provenance-based status repair, snapshot-based cancellation, explicit reference sizing, honest continuity metadata, safe model discovery, non-destructive text deduplication. These are independently testable and do not need an expensive render.

Rejected: blindly increasing steps, forcing Spectrum off, automatically retrying failed scenes, adopting arbitrary MP4 files as completed renders, silently splitting all native runs into one-chunk jobs, promising a seamless film after metadata tests, forcing local workflows to use hosted APIs.

Deferred until a separate short visual experiment: same-run vs last-frame handoff motion comparison; matched Spectrum A/B; performance benchmark with identical model/seed/steps/reference count and dimensions; temporal review with audio playback. Native prefix resume with Spectrum must follow the installed engine contract; do not bypass its safety checks.

## Validation and issue handling

Run targeted Python and JavaScript tests, syntax checks and diff checks. Reload the idle app through Pinokio only after changes pass. Check read-only live endpoints; never enqueue production as a smoke test. Keep #19/#21 open as described above; #28 remains unconfirmed without the reporter's diagnostic logs. No issue comments or public release are sent implicitly by this development task.

## Implemented and reviewed

- Found an additional reference-numbering defect: compacting references to each chunk's active order produced incorrect labels for a fixed-slot V39 helper, and raw Picture labels did not account for the first-frame offset. Director now maps section-local Picture/@R labels to the take's fixed @R slots. The installed native sampler owns final Picture expansion. Regression tests include a first-frame guide and differing character order/subsets.
- Stop holds the queue-selection lock across the engine interrupt request. It does not interrupt Comfy when Studio has no running job, and does not overwrite a job that completes during the request. User cancellation source/time is recorded and cleared on explicit retry.
- Startup recovery of legacy cancelled output requires successful, completed Comfy history plus video output. Missing history or an arbitrary MP4 cannot prove completion. It reattaches to the recorded prompt for download; it does not submit a replacement render. This is a repair path and a race fix, not proof of #28's original cause.
- Match Output is the new default for reference geometry. Max Identity remains an explicit validated Director API choice and stored job selections remain authoritative. There is no measured speed claim until an equivalent render benchmark is performed.
- Production details distinguish a native saved-prefix continuation from an independent last-frame handoff; native chunk count and stored reference size are displayed and archived.
- Duplicate Action/Beats text is omitted only when equivalent after whitespace/case/terminal-punctuation normalization. Distinct chronology is retained. Saved film data is not rewritten.
- Model catalog and Hybrid detection include nested directories and preserve relative Comfy loader filenames. Alternate filenames still require the known full model size. Encoder/VAE settings are preserved.
- Queue pause capabilities explicitly report after-current behavior. Mid-render pause remains unsupported; #19 remains open.

Validated: 58 targeted Python tests and all 39 JavaScript tests pass; Python compilation, JavaScript syntax and git diff whitespace checks pass. Tests use mocks/temp files and do not render. Existing uncommitted planner/UI changes were preserved. Launcher scripts, installed weights, existing film settings and the paused overnight automation were not edited by this update.

Remaining acceptance gate: a short, controlled visual/audio continuation test and equivalent performance benchmark. These code checks cannot establish cinematic quality or the reporting user's hardware behavior.

Live verification after Pinokio restart: Studio serves the updated asset revision; OpenAPI advertises Match Output as the Director default; queue pause capability is after_current; active engine remains MiniMax; installed Hybrid is recognized; Spectrum remains 0.60; no queued/running Studio jobs. Overnight automation remains PAUSED and its runner is stopped. No film render was submitted.

Initial-pass exit checklist: AGENTS/task scope reviewed, logs inspected, application changes separated from launchers, pre-existing changes preserved, targeted regression tests passed, syntax/whitespace checks passed, idle restart and live read-only checks passed. No launcher edits were made, so launcher capture/example changes were not applicable. At that checkpoint, public issue closure, comments, push and release had not been performed.

## Authorized completion pass

The user subsequently authorized completing the short experiments and publishing the update. The full suite now passes 225 Python and 39 JavaScript tests. Saved-prefix continuation no longer acquires an unintended last-frame keyframe when the original run was prompt-only. Retry preserves explicit starting images while refreshing independent handoffs. Per-job Spectrum provenance is captured from the submitted graph, then retained in Gallery and displayed in production details.

Short Director experiments run as separate test films and restore the original active film/settings. They do not resume or modify the paused feature-film plan. Generated media and local diagnostic artifacts are excluded from the release. The queued matched Spectrum control used the same actual prompt, seed, first frame and reference images, but was interrupted when Pinokio and both backend services became unavailable. No completion or matched speedup is claimed for that control. Its recorded job is held as interrupted rather than being resubmitted automatically. Original settings were restored offline after verifying the services were stopped.

Three draft results completed at 480p/8 steps: native Spectrum OFF, native Spectrum 0.60, and a two-job Spectrum 0.60 last-frame chain, each exactly8s/192frames with32kHz audio. The Spectrum examples had translucent/ghost artifacts; fixed-camera compliance was imperfect. The film-quality gate therefore remains failed/unconfirmed. Code reliability fixes can ship independently; the release does not claim these draft renders establish production quality. Full listening and an equivalent 1088p performance comparison remain unverified. The developer-control-plane outage is recorded as an external interruption with unknown closure cause, not attributed to H3 or to a code change without evidence.


## Completed exact-prompt control

After the user reopened Pinokio, a fresh exact-prompt OFF control completed: the actual prompt/chunk prompts, seed, steps, dimensions, references, guide and reference sizing matched the Spectrum 0.60 case. Both outputs contain 192 frames / 8 seconds and 32 kHz audio. Recorded wall time was 344.45 s OFF versus 272.86 s ON; OFF followed a restart with different loading/cache conditions, so this single draft pair is not an isolated Spectrum speedup benchmark or a 1088p prediction. The sampled OFF frames did not show the conspicuous translucent double-body trails seen in ON, but walking/fixed-camera compliance still failed full acceptance. This is a limited observation, not a universal causal conclusion. The interrupted attempt remains preserved. Original active film and Spectrum 0.60 settings were restored, the queue is idle and feature production remains paused. Audio listening and an equivalent 1088p benchmark remain outstanding.
