# TypedMem

**Memory for AI agents when facts change.**

Your agent knows the account is **Enterprise**. Then an old support ticket
arrives saying it was **Pro** in April. Which value is current, and should the
newest record win?

TypedMem keeps the current truth without erasing what used to be true, or
where it came from. **The old value isn't false. It is no longer current.**

## The core: states

| Promise | What you get |
|---|---|
| **Current state** | One current value per named state (`account.plan`), with `get` |
| **History** | Every earlier value, kept with its validity window, with `history` |
| **Provenance** | Where each value came from, and how much to trust it |
| **Conflict** | When sources genuinely disagree, `get` refuses to invent an answer |

```bash
pip install typedmem          # Python 3.10+, no dependencies
typedmem set account.plan Enterprise --valid-from 2026-09-01 --source billing
typedmem get account.plan
```

Start with **[States](states.md)**, or watch it happen in the
**[Truth Through Time explorer](explorer/?s=late)**.

## How it works

Values are ordered by **when they became true** (validity time), not by
when they arrived. Sources carry **authority**, so a weaker source can't
silently override a stronger one. A later value **supersedes** an earlier
one; values that can't be ordered are a **conflict**. The rules are in
[design note 0002](https://github.com/lyr-ai/typedmem/blob/main/design/0002-changing-facts.md).

## Advanced: typed memory

Underneath states is TypedMem's typed memory core: profiles, per-type
conflict policies, a replayable event log, evolvers and recall.

TypedMem is the layer between data and reasoning where every change is governed by an explicit contract — not learned, not implicit. Every memory has a declared type validated against a profile, a conflict policy that fires deterministically on slot collision, a structured source with dedup identity, and an entry in a first-class event timeline. Memories update on conflict, decay over time, and summarize non-destructively — all under rules you wrote, not rules the system inferred.

```
                              ┌──────────────────┐
                              │  DomainProfile   │  ← schema: which types,
                              │  TypeSpec × N    │     which policies,
                              │  prompt + rules  │     which validations
                              └────────┬─────────┘
                                       │
       text ──► Extractor ──► Memory ──┴──► MemoryStore ──► Retriever
                                            │
                                            ▼
                                         Evolver
                              (contradictions, drift, goals,
                               non-destructive summarization)
```

**Zero runtime dependencies.** Stdlib only — LLM clients, YAML profile loading, and richer embedders are optional extras.

### Why typed memory

Most "AI memory" libraries are wrappers around a vector database. That works for "remember what the user said," but it falls apart the moment you want an agent to:

- track **who said what, in which document, at which span**
- handle **the same fact from three sources** without storing it three times
- recognize that **a new decision supersedes the old one** without losing the audit trail
- **summarize stale events** without throwing away the originals
- **isolate** legal memory from medical memory on the same machine
- **flag contradictions** instead of silently overwriting them

TypedMem treats these as first-class concepts.

## Start here

<div class="grid cards" markdown>

- :material-timeline-clock-outline: **[States](states.md)**

    Current value, history, late records and conflicts: the core of TypedMem.

- :material-play-circle-outline: **[Truth Through Time](explorer/?s=late)**

    See a late record move into the past while the current value stays.

- :material-rocket-launch: **[Quickstart](quickstart.md)**

    Install, write your first memory, run the engineering-design demo.

- :material-lightbulb-outline: **[Concepts](concepts.md)**

    Source, workspace, ConflictPolicy, Memory — the four primitives.

- :material-file-tree: **[Profiles](profiles.md)**

    Schema for a domain: types, policies, prompt templates.

- :material-update: **[Evolvers](evolvers.md)**

    Contradiction surfacing, drift detection, goal resolution, summarization.

- :material-console-line: **[CLI](cli.md)**

    `typedmem` shell tool — `set`, `get`, `history`, `add`, `search`, …

- :material-source-repository: **[Source on GitHub](https://github.com/lyr-ai/typedmem)**

    Code, tests, issues.

</div>

