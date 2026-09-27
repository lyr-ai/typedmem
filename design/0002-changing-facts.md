# 0002: What is a changing fact in TypedMem?

Status: **draft, for review**. No code yet. 2026-09-26.

## The failure this fixes

A new user tries the obvious thing (TypedMem 0.8.0 from PyPI, no API key):

```text
$ typedmem add "Alice works at OpenAI"
$ typedmem add "Alice works at Anthropic"
$ typedmem search "where does Alice work"
0.438  fact  Alice works at Anthropic
0.438  fact  Alice works at OpenAI
$ typedmem contradictions
no contradictions
```

Adding `--subject alice.employer --type fact` changes nothing, under any
profile, because `fact` is `KEEP_BOTH`. The machinery we need already exists:
`decision` (SUPERSEDE) and `preference` (REPLACE) both give the right answer
for the same subject. But a user only reaches it after choosing the right
profile and type and supplying a subject. The product's headline question,
*which one is true now?*, is answered only for users who already understand
the ontology.

Goal: **the most natural input gives the most natural result.** Two writes to
one piece of state, then TypedMem says:

```text
current   Anthropic
previous  OpenAI
why       later value; both came from you at the terminal
```

## Decisions

### 1. Identity: a state is a key the user names

A changing fact is a **state**: a named slot that holds **one value at a
time**. The user names it with a key such as `alice.employer`.

- The key is written `entity.attribute` by convention, but TypedMem treats it
  as opaque. There is no ontology to learn and no parsing that can go wrong.
- Keys are trimmed and lowercased, so `Alice.employer` and `alice.employer`
  are one slot. Values are only trimmed; `OpenAI` stays `OpenAI`.
- The slot is `(workspace, key)`. It is independent of profile: `set` works
  the same under `core`, `personal` or a custom profile.
- Internally a state value is an ordinary `Memory` with type `state`,
  `subject = key`, `content = value`. It is a new built-in type registered in
  every profile, so it uses the existing store, kernel, events and replay.

A state is single-valued **by definition**. "Alice also consults for OpenAI"
is not a second employer. It is another key (`alice.consulting`) or an
ordinary `add`. Multi-valued state is out of scope.

`fact` keeps its current behaviour (`KEEP_BOTH`). Changing it would silently
alter existing stores, and "same subject" was never a claim that two facts
compete for one value.

### 2. Current truth: the latest value that is valid now

Each value has a validity start, `effective_from`. That is the declared
`valid_from`, or the time of the write when none is given (existing field,
existing fallback). An optional `valid_to` ends it.

> **current(key, at t)** = among the key's values valid at `t`, the one with
> the latest `effective_from`.

This is a pure function of the stored values, the same rule
`resolve_temporal` already applies. The `superseded_by` links the kernel
writes are an index of it, never a second source of truth. Because the rule
uses validity time rather than arrival order, learning about an old value
late does not break it (see rule 3 below).

### 3. Writing: four outcomes, each one explicit

Say `set(key, value)` arrives and `C` is the current value.

| # | Situation | Outcome | Kernel action |
|---|---|---|---|
| 1 | No value yet | **new** | insert |
| 2 | Same value as `C` | **unchanged**: add the source to `C`, no new version of the fact | REINFORCE |
| 3 | Different value, starts later than `C`, source not weaker than `C`'s | **changed**: the new value is current, `C` becomes previous | SUPERSEDE |
| 3b | Different value, starts *earlier* than `C` | **past value**: stored in history at its place in time, `C` stays current | insert, already superseded |
| 4 | Different value, starts at the same time as `C`, or later but from a **weaker source** | **conflict**: both kept and cross-linked; no silent winner | FLAG |

Every outcome emits the existing events with before/after snapshots, so all
four are replayable.

### 4. Supersession vs contradiction

- **Supersession** means *the world changed*. Two values can be ordered in
  time, so the later one is current and the earlier one is history. Nothing is
  wrong.
- **Contradiction** means *the sources disagree*. Two values claim the same
  slot and cannot be ordered: they start at the same time, or the later one
  comes from a source with less authority (for example, a model's inference
  against an explicit user statement). TypedMem does not pick a winner.
  `get` reports the conflict and `contradictions` lists it.

A conflict is resolved by a later `set` with authority at least as high as
the conflicting values. That is ordinary supersession, so no separate
"resolve" verb is needed.

This keeps the authority guard we already have (a weaker source cannot
displace a stronger one). But where `REPLACE` silently *ignores* the weaker
write, a state *flags* it, because a silent drop is exactly the failure the
product exists to prevent.

### 5. History: nothing is erased

`history(key)` lists every value the slot has held, newest first. Each entry
shows:

- status (`current`, `previous`, or `conflict`);
- its validity window;
- its provenance: source, when TypedMem learned it, and authority when it
  isn't the default.

The first screen's "why" comes from this list: the current value is current
because it is later, and the history shows where each value came from.

### 6. Minimal input

```bash
typedmem set alice.employer OpenAI
typedmem set alice.employer Anthropic
typedmem get alice.employer        # Anthropic
typedmem history alice.employer
```

```python
from typedmem import AgentMemory

mem = AgentMemory(path="agent.db")
mem.set("alice.employer", "OpenAI")
mem.set("alice.employer", "Anthropic", source="email from Alice")
mem.get("alice.employer")          # 'Anthropic'
mem.history("alice.employer")      # current Anthropic, previous OpenAI
```

The only required inputs are a key and a value. Optional inputs:

- `source` (and `--uri` / `--authority`, as `add` has them);
- `valid_from` / `valid_to`, for "Alice joined Anthropic on 2026-03-01".

Leaving the dates out means "true from now".

CLI `history` currently takes a memory id. It will also accept a key: an
argument that is an existing memory id keeps today's behaviour, and anything
else is read as a key.

## Out of scope for this change

- **Natural-language extraction**: `add "Alice works at Anthropic"` giving
  `alice.employer = Anthropic`. This is option C, to do later, and it will
  write through `set` once it exists. Until then, `add` does not pretend.
- Multi-valued state, value types other than strings, and fuzzy value
  matching (`anthropic` vs `Anthropic` are different values).
- Any change to `fact`, `decision`, `preference` or the profiles.

## Acceptance: the README first screen is the contract

The first-screen example is copied verbatim from a test that runs it against
a fresh store and compares the real output. Dates are normalised; nothing else
is. If the product's behaviour drifts, the test fails before the README can
lie.

Required test cases:

1. The first-screen transcript (rules 1 and 3).
2. Setting the same value again gives **unchanged** and no new history entry
   (rule 2).
3. A backfilled past value lands in history, and current does not change
   (rule 3b).
4. The same start time gives a conflict, with `get` reporting both values
   (rule 4).
5. A later write from a weaker source gives a conflict, not a silent ignore
   (rule 4).
6. A stronger later `set` resolves the conflict (section 4).
7. After any of the above, `replay()` of the event log reproduces the state
   exactly.
8. Keys are case-insensitive, and the rules hold under every built-in profile.

## Open questions for review

1. **Rule 4, weaker-but-later.** Should it be a conflict (as proposed), or
   should the later value win with a warning? A conflict is safer, but makes
   an agent's own updates noisier when their authority is lower than the
   user's.
2. **Where `set/get/history` live.** Proposed: on `AgentMemory` and the CLI,
   backed by new `MemoryStore` methods. Is `AgentMemory` still the front door,
   or should the first screen show a plainer entry point?
3. **Naming.** Is `state` right for the type, and `set` / `get` / `history`
   for the verbs? `history` overlaps with the existing id-based command
   (resolved above by trying the argument as an id first).
