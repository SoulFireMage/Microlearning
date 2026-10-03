# Design notes

These notes cover the original product brief and technical spec (brainstormed with Gemini), what this build keeps, what it changes, and what it leaves open.

## What the brief gets right

The diagnosis is sound and specific:

- **Fluency is not durability.** Summary apps feel like learning because reading smooth prose is easy. The testing effect, where retrieving something strengthens memory more than re-reading it, is one of the most robust findings in learning research (e.g. Roediger & Karpicke, 2006).
- **The real cost for a divergent learner is re-entry, not entry.** Designing for *resumption* rather than *retention* is the genuinely novel idea in the brief, and the primer is its mechanism.
- **Streaks punish variance.** An all-or-nothing counter turns an off week into a reason to quit.
- **Graph, not queue.** Branching turns a distraction into a recorded association.

The fractal L0/L1/L2 depth, the state machine and the primer modal are all kept close to the spec.

## Where this build departs from the spec, and why

| # | Spec | Change | Reason |
|---|---|---|---|
| 1 | No retrieval mechanism anywhere | Each unit has a **recall probe**. *Resurface* uses an expanding interval (1d / 3d / ×2.5) | The brief names the illusion of competence as the core failure, then specifies a system with no retrieval in it. This closes that gap. No overdue counts, no penalties. |
| 2 | Content sourcing unspecified (5 seed units) | **Ingest** from Wikipedia, arXiv, URLs or pasted text. Source text is stored with the unit and fed to later synthesis | "Where does content come from?" was the open question. Grounding generation in stored source text reduces drift. |
| 3 | LLM writes L2 "with source references" | Prompts forbid invented citations. Every layer carries **provenance** (`curated` / `extracted` / `synthesised`). Synthesised layers say "verify before trusting" and can be hand-edited (which marks them curated) | LLM-generated references are a known hallucination hotspot. Labelling keeps ground truth and synthesis visibly separate. |
| 4 | LLM returns `suggested_next_unit_id` | The recommended unit is chosen **deterministically** (last *stuck* unit, else the current unit). LLM-proposed relation ids are validated against the database | A model cannot be trusted to emit real primary keys. |
| 5 | `/data` persistent disk + SQLite WAL | `/data` is now a **Storage Bucket mount** (object storage) on HF. The app uses the rollback journal (`DELETE`) there, plus a JSON export | WAL needs a shared-memory index that network/object-backed filesystems often cannot provide. HF's own Label Studio guide runs SQLite on a bucket mount, but I have not verified durability under crash conditions. Export often. |
| 6 | `DORMANT` set by a 7-day idle timeout | Dormancy is computed **lazily** on read | Spaces sleep when idle, so a background timer would not fire. |
| 7 | `PAUSED → ACTIVE` only via `PRIMER_ACKNOWLEDGED` | Added `RESUME` (PAUSED→ACTIVE, no primer), manual `PAUSE`, `AUTO_PAUSE` (enforces the active-thread limit), `REOPEN` for resolved threads, and branching from NEW/PAUSED | Returning to a parent after a 20-minute branch should not need a primer. Resolved curiosities do come back. |
| 8 | (implicit) | Transitions are a SQL **compare-and-swap** on status | Found in testing: two parallel requests both ran the dormancy sweep and the second crashed. |
| 9 | Single `user_notes` field | Append-only **pins** log (latest pin is also mirrored into `user_notes`) | Overwriting loses the trail the primer needs. |
| 10 | `current unit` not modelled | `threads.current_unit_id / current_depth / current_lens` | Branching and resuming need to know where you were. |
| 11 | Resumption Score = reactivated / dormant | Kept, plus **median time parked before return** | The brief talks about the half-life of dormancy recovery, which the ratio does not measure. Both are shown neutrally, never as a target. |
| 12 | `colorTo: slate` | `gray` | `slate` is not a valid HF Space colour. |
| 13 | Qwen2.5-72B / Llama-3.3-70B | `Qwen/Qwen3.8-27B` via Inference Providers (configurable) | Current model with live providers. Reasoning output (`<think>…</think>`) is filtered from streams and JSON. |
| 14 | `APP_SECRET` with no auth design | Recommend a **private Space**. Optional `APP_PASSWORD` gate with an HMAC cookie (`SameSite=None` because the Space page embeds the app in a cross-site iframe) | Simplest secure default. |
| 15 | HTMX/React + Tailwind CDN | Vanilla JS SPA, libraries **vendored** (marked, DOMPurify, KaTeX) | No build step and no runtime CDN dependency. KaTeX is essential for ML maths and was missing from the spec. |
| 16 | SQLAlchemy | Plain `sqlite3` with explicit DDL | Small schema, fewer moving parts. |

### The addition the spec did not have: lenses

Depth is one axis; **lens** is a second, orthogonal one:

- **Pattern** leads with the invariant, the structural parallel in another field, what that mapping preserves, and *where it breaks*.
- **Steps** builds from definitions, numbers each step and includes a worked numeric example.
- **Core** is the balanced exposition.

This is aimed squarely at a fast pattern-matcher and a careful step-builder reading the same concept. Softmax and backprop ship with all three L1 lenses as examples. Others can be synthesised on demand.

## Things I am unsure about (worth arguing over)

1. **Is the primer the right unit of re-entry?** An alternative: open a parked thread with one *recall question* about what you had locked down, then show the primer. Retrieval before re-reading would turn the primer into a retrieval event rather than a fluent summary, which is exactly the trap the brief warns about. It is cheap to try.
2. **Does "Pattern vs Steps" match how Kat and Richard actually differ?** Or is the real split about *order* (shape first vs. ground first) rather than *style*? If so, one layer with two reading orders might beat two layers.
3. **Content strategy.** Wikipedia, arXiv abstracts and open textbooks (OpenStax, Distill-style articles) are freely usable. Full arXiv PDFs need extraction and are licence-dependent. Is the goal broad coverage, or a deep, hand-checked core for ML maths that grows outward?
4. **Single-user vs shared graph.** Currently personal. A shared, curated concept graph with personal threads on top is a different product with different trust requirements.

## Roadmap candidates

- A visual graph view of the atlas (the data is already served at `/api/graph`).
- Recall-first re-entry (point 1 above).
- PDF ingest (arXiv full text) with section chunking.
- Scheduled JSON snapshots to the Storage Bucket or a private dataset repo.
- Import from export JSON.
