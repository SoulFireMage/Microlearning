# The field guide to threads/

*Your guide's voice is Kat's: a fast pattern-matcher who helped dream this place up. Shape first, details after. If you're a step-by-step reader, the **Five-minute tour** is your on-ramp; read it with the app open in another tab.*

---

## The one-breath version

This isn't a course and it isn't a streak. It's a **map of ideas** (the *Atlas*) plus **threads**: lines of curiosity you follow through that map. You can follow three at once, wander off sideways, vanish for a month and come back without paying for it.

Most learning apps are built for minds that move in straight lines. This one is built for minds that branch.

## Why it's shaped like this

Three things break most microlearning for associative thinkers. Each one has a counter-move here:

| What goes wrong elsewhere | What happens here |
|---|---|
| **Smooth summaries feel like learning but don't stick.** Reading is easy, so it *feels* like mastery. | Every concept has a **recall question**. You pull the idea back out of your own head, which is what actually makes it stick. |
| **Coming back is expensive.** Three weeks later you've lost the thread and "Step 4 of 12" means nothing. | A thread left alone is **parked**, not failed. When you return you get a **30-second primer**: what you were solving, what you'd nailed down, where you got stuck. |
| **Streaks punish real life.** Miss a day, lose the flame, quit. | No streaks. No red badges. No "days missed". The only stat counts how often you *came back*. |

The core bet: for a branching mind, the real cost of learning isn't starting. It's the **re-entry burn**. Get that near zero and the branching becomes an asset instead of a leak.

---

## The five-minute tour

Do this once and the rest of the guide will click into place.

1. **Open the Atlas** (top bar). These are the concepts the app knows, grouped by domain. Skim the hooks. Click one that tugs at you.
2. **Start a thread there.** Give it a *question*, not a topic. "Why does attention use softmax?" beats "Attention". The question is what the primer will remind you of later.
3. **Read L0.** That's the 30-second hook: one idea, no fluff. If that's all the bandwidth you've got today, stop. That still counts.
4. **Switch to L1** (the depth switch under the title). The 3-minute anatomy: how it works, where it breaks.
5. **Try the lens switch: Core / Pattern / Steps.** Same depth, different way of explaining (more below). The starter concepts *Softmax* and *Backpropagation* have all three written for L1, so start there to feel the difference.
6. **Press Ctrl+K** (or the 📌 button) and type one sentence: a question, a half-thought, a snag. That's a **pin**. It's how future-you finds the edge you were standing on.
7. **Scroll to Connections** at the foot of the page. Click a related concept and choose **Branch to a new thread**. Your first thread is checkpointed and the new one opens.
8. **Go back to Threads** (top-left). There they are: one active, one paused, linked parent → child. Nothing lost.

That's the whole loop. Everything else is detail.

---

## The pieces

### Threads and their states

A thread is one line of curiosity. It moves through states on its own; you never have to "manage" it.

```
NEW ──open──▶ ACTIVE ⇄ PAUSED ──(7 days untouched)──▶ PARKED
                 │         ▲                             │
                 │         └──── primer, then resume ────┘
                 └──▶ RESOLVED  (you're satisfied; reopen any time)
```

- **Active:** what you're in now. At most **two** at once. Open a third and the least recently used one is paused for you. That's a feature: it protects your attention, not a limit to fight.
- **Paused:** checkpointed. Click it and you're straight back in.
- **Parked:** untouched for 7 days. Opening it **always** shows the primer first, never a wall of text.
- **Resolved:** the curiosity is satisfied. That's not "done forever": its connections stay in the map, and **Reopen** brings it back.

The line at the top of the home page, *"resumption 3/4 parked threads picked back up"*, plus how long threads typically rest before you return, is the only scoreboard here. Both describe your rhythm. Neither judges it.

### Depth: L0, L1, L2

Every concept can exist at three zoom levels:

- **L0, the hook (~30 s).** The one non-obvious idea. Enough on a fried-brain day.
- **L1, the anatomy (~3 min).** Mechanics, failure modes, trade-offs.
- **L2, the deep dive.** Formal definitions, derivations, code, edge cases, history. For when hyperfocus arrives and you want to go all the way down.

Switching depth keeps your place on the page and records how deep you've gone.

### Lenses: Core, Pattern, Steps

Depth is *how far*. Lens is *which way in*.

- **Pattern** leads with the shape: the invariant, the same structure turning up in another field, and exactly **where that analogy breaks**. It's dense and quick. (In our house this is my lens.)
- **Steps** builds from definitions. Every symbol is defined before it's used, steps are numbered, and there's a small worked example with real numbers. (This is Richard's. He checks the arithmetic.)
- **Core** is the balanced middle.

A greyed-out lens or depth means that layer doesn't exist yet. Press **Synthesize** to have the AI write it, or **Write it yourself**. A good habit: read Pattern to see the shape, then Steps to prove you can walk it.

### Marking where you are

Under every concept:

- **✓ Locked in:** you could explain it to someone. Primers list these as "what you locked down".
- **⚑ Stuck here:** friction. It's not failure, it's *data*. The primer brings you back to exactly this spot, and the app asks you to pin what the snag is.
- **📌 Pin a thought (Ctrl+K):** works anywhere in a thread without leaving the page. Pins are kept as a trail, and your latest pin becomes the primer's "where you froze".

> Pin before you leave. Even "lost me at the Jacobian" is gold to future-you.

### Connections: how the map grows

At the foot of every concept there are four kinds of neighbour:

- **Prerequisites:** what this builds on.
- **Downstream:** what builds on this.
- **Structural parallels:** the same pattern in another domain. *Softmax* **is** the Boltzmann distribution from physics, wearing a different coat.
- **Contrast points:** things that are easy to confuse with this one.

Click any of them and you choose:

- **Explore in this thread:** stay on one line of thought; the concept joins this thread's trail (the chips under the title).
- **Branch to a new thread:** fork. Add a reason ("needed Raft before distributed state made sense") and the primer will use it. You can also record *how* the two concepts relate, which adds a new connection to the map.

**+ link a concept** adds a connection by hand. This is where *your* map starts to differ from anyone else's.

### Primers: the re-entry burn, near zero

Open a parked thread and you get:

- **The problem you were solving:** the anchor.
- **What you locked down:** up to three things you'd nailed.
- **Where you froze:** your last pin, or the concept you marked stuck.
- **Jump back in at …:** it drops you at the stuck spot if there is one, otherwise where you left off.

With an AI key set (see below), the primer is written fresh from your trail. Without one, it's assembled straight from your pins and marks, which still works. **regenerate** rewrites it.

### Resurface: memory that sticks

Concepts you've read at L1 or deeper, or locked in, show up in **Resurface** for a recall check:

1. Answer in your own words. Rough is fine; the effort of reaching for it is the point.
2. Reveal the reference answer.
3. Say how it went. That sets when the question comes back: **Didn't have it** → 1 day, **Partly** → 3 days, **Had it** → a week or more, growing each time.

**Skip** just moves on. Nothing piles up, nothing goes overdue, nothing is ever deleted. Do one, or none.

### Adding new concepts

- **+ Source** (top bar): pull in a concept from a **Wikipedia** article, an **arXiv** paper, any **web page**, or **pasted text**. The source text is stored with the concept, so later write-ups are based on it rather than the AI's memory. With an AI key it drafts L0, L1, a recall question and connections to concepts you already have.
- **+ Thread** with a new name, or **Branch** to a concept that doesn't exist yet: this creates an empty concept you can **Synthesize** or write yourself.

### Trust labels: what to believe

Every layer carries a small label:

- **curated:** written or corrected by a person.
- **extracted:** copied straight from the source.
- **synthesised:** written by the AI. *Verify before trusting.*

This matters. AI write-ups can be fluent, sophisticated and *wrong*. During testing, a Pattern deep dive on softmax confidently put the wrong kind of geodesic in a table. Read synthesised layers the way you'd read a clever friend's notes: useful, but check the load-bearing claims. Use **edit** to fix a layer; it then becomes *curated*. That's also how the map gets better over time.

---

## Rhythms that work

- **Low-energy day:** wander the Atlas reading only L0 hooks. Start nothing. That's still a good day.
- **Hyperfocus day:** pick one thread, go to L2, branch as often as you like. Pin as you go.
- **Before you stop:** one pin. Always. Ten seconds now saves ten minutes later.
- **Feeling scattered:** look at Threads. You'll see the map of where your head has been, and it's usually more connected than it feels.
- **Done with something:** Resolve it, without ceremony. It stays in the map, and it can come back.

---

## Building on it

Out of the box, the Atlas holds a small, deliberately cross-linked slice of machine-learning maths: backprop, gradient descent, softmax, entropy, KL divergence, the Boltzmann distribution, attention and SVD. It's a seed, not the garden. To grow your own:

1. **Pick a question you actually have** and start a thread on it, even if no concept for it exists yet.
2. **Pull in sources** with + Source as you go: the article you were reading anyway, the paper someone mentioned.
3. **Link concepts across domains** with + link a concept, especially *parallels*. Those cross-domain links are where branching minds get their best ideas.
4. **Write the lens that's missing.** If Pattern exists and Steps doesn't (or the other way round), write it yourself. Explaining it is the deepest kind of learning.
5. **Correct what's wrong.** Every fix turns *synthesised* into *curated*, and the map gets more trustworthy.
6. **Back up now and then:** `/api/export` (also linked on the home page while storage is temporary) downloads everything as a JSON file.

---

## If someone just sent you a link

You're looking at **their** copy. Each copy of this app is one person's map: anyone who can open it sees, and edits, the same threads. To get your own:

1. On the Hugging Face page for the Space, open the **⋮** menu and choose **Duplicate this Space**. (This only works if the owner made it public or shared it with you.)
2. In your copy's **Settings → Variables and secrets**, add a **secret** (not a variable, since variables are publicly visible):
   - `OPENROUTER_API_KEY` (a budget-limited key from openrouter.ai), **or** `HF_TOKEN` (a Hugging Face token with *Inference Providers* permission). Without either, everything except the AI writing still works.
3. In **Settings → Storage Buckets**, attach a bucket at **`/data`**. Without it, your map is wiped whenever the Space restarts, and the home page will warn you.
4. If your copy is **public**, also add secrets `APP_PASSWORD` and `APP_SECRET` (any long random string). Otherwise strangers can edit your threads and spend your AI budget.

Optional settings: `OPENROUTER_MODEL` (default `qwen/qwen3.8-27b`), `LLM_REASONING` (`off` / `low` / `medium` / `high`: higher means slower but more careful deep dives), `DORMANCY_DAYS` (default 7), `MAX_ACTIVE_THREADS` (default 2), `WIKIMEDIA_TOKEN` (if Wikipedia starts refusing requests).

The source code, design notes and tests are at **github.com/SoulFireMage/Microlearning**.

---

## Honest limits

- **AI layers can be wrong.** See *Trust labels*. The labels are there so you always know what you're standing on.
- **Deep dives are slow to start.** The model thinks before it writes, so expect 30–60 seconds of "thinking…" before text appears.
- **One map per copy.** There are no separate accounts; sharing the link shares the map.
- **Wikipedia sometimes refuses** requests from shared cloud servers. If it does, paste the text instead, or add a `WIKIMEDIA_TOKEN`.

---

## Quick reference

| | |
|---|---|
| **Ctrl+K** / 📌 | Drop a pin (inside a thread) |
| **L0 / L1 / L2** | Depth: 30 s / 3 min / deep |
| **Core / Pattern / Steps** | Lens: balanced / shape-first / step-by-step |
| **✓ Locked in** | You could explain it |
| **⚑ Stuck here** | Friction; the primer brings you back here |
| **⑂ Branch** | Fork a child thread; the parent is checkpointed |
| **Parked** | Untouched 7+ days; opens with a primer |
| **Resurface** | Recall checks on an expanding schedule |
| **◐** | Light / dark theme |

Go follow something. Branch when it tugs. Come back whenever. The map will remember the way.
