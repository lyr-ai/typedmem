# 0002: What is a changing fact in TypedMem?

Status: **approved 2026-09-26** (open questions 1–3 decided: see the end).

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

**Invariant: a conflict set contains only values that remain simultaneously
plausible at the queried time.** Values that start at the same moment end
every earlier value whose authority is no higher than theirs, *even when they
disagree with each other about what came next*.

- Free (January), then billing says Enterprise and the CRM says Pro, both
  from 1 September: the conflict is Enterprise vs Pro. Free is history,
  because both newer claims agree it ended.
- An earlier value from a *stronger* source is not ended by weaker claims.
  It stays in the conflict.

**Open-ended claims (owner decision D2, 2026-09-27).** A later start time
doesn't imply that an earlier open-ended claim has ended. When overlapping
claims can't be put in time order without inventing an end date, they stay
in conflict. When their authority differs, authority keeps a weaker
overlapping claim from silently ending a stronger one.

- A user says "San Jose since 2024" (no end); a weaker inference says
  "Seattle since August 2026". The claims overlap, and nothing says San Jose
  ended, so they conflict. Making Seattle current would invent the fact
  "San Jose ended before August 2026", on the word of the weaker source.
- By contrast, a weaker claim that *starts earlier* than the current value
  describes the past, and goes into history: time order is known.

Measured on reliagent-bench Mode A (A-02 conflict, kept as a deliberate
disagreement with that benchmark's gold; A-08 history, correct): see
[the results](https://github.com/lyr-ai/reliagent-bench/blob/measure/states-0.9.3/external/results/states-0.9.3.md).

*Correction, 0.9.1:* 0.9.0 kept every earlier value in the conflict (Free
above). That violated this section's own definition, since Free and
Enterprise can be put in time order. It was found while checking design
0003's scenarios against the released package.

Stronger authority alone does not resolve a same-time conflict. Values that
start at the same moment conflict whatever their authority. Resolving a
conflict needs later evidence: a conflict is resolved by a later `set` with
authority at least as high as the conflicting values. That is ordinary supersession, so no separate
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

### 5b. Reading: `get` never invents a current value

> change → resolve; disagreement → expose.

`get(key)` returns the current value only when one can be established.

- **Settled:** it returns the value.
- **Nothing set, or the last value has expired:** it returns `None`. The CLI
  prints "not set" and exits 1.
- **In conflict:** it raises `StateConflict`, which carries every value still
  in contention with its provenance. It never returns the stronger value, the
  newer one, or whichever comes first. The CLI lists the values and exits 3.

The headline promise, "TypedMem keeps the current truth", means *when a
current truth can be established*. When it can't, TypedMem says so.

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

### 5c. Presentation

`history` shows the transition by default: value, status and source, newest
first. `history -v` (and `StateHistory.table(dates=True)`) adds each value's
validity window. The first thing a user sees is *what changed*. *When* it
changed is one flag away.

Storage keeps every claim, and presentation may summarise them. For example,
a value first guessed by an agent and later confirmed by an email is two
records. A future view may draw them as one value with two sources.

## Known issues

- ~~`list` can disagree with `get`/`history` after a scheduled value takes
  effect.~~ **Fixed in 0.9.3 (#7).** `all()`, `by_type()`, the retriever and
  `len(AgentMemory)` now resolve states as of now, with the same `resolve`
  that `get` and `history` use. The `superseded_by` index is no longer read
  for states on any read path.

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
3. Validity time, not arrival order (rule 3b). Write t1 OpenAI, then t3
   Anthropic, then t2 Google, which arrives last. Current stays Anthropic, and
   history reads OpenAI → Google → Anthropic.
4. The same start time gives a conflict: `get` raises `StateConflict` naming
   both values, and `contradictions` lists them (rules 4 and 5b).
5. A later write from a weaker source gives a conflict, not a silent ignore
   (rule 4).
6. A stronger later `set` resolves the conflict (section 4).
7. After any of the above, `replay()` of the event log reproduces the state
   exactly.
8. Keys are case-insensitive, and the rules hold under every built-in profile.

## Decisions on the open questions (2026-09-26)

1. **Later but weaker gives a conflict**, not "the later one wins with a
   warning". Temporal order answers *when did the world change*. Authority
   answers *are we entitled to believe the change*. When the two disagree,
   the conflict is exposed. Resolution policies may come later; there will be
   no silent winner in 0.9.
2. **`set` / `get` / `history` live on `AgentMemory`**, backed by
   `MemoryStore.set_state` / `get_state` / `state_history`. There is no
   separate state-store class for users to learn.
3. **Names:** `state`, `set`, `get`, `history`. A future UI can call the view a
   "Truth Timeline".

Scope is frozen to:

- the built-in `state` type;
- `AgentMemory.set` / `get` / `history` and the CLI verbs;
- authority-safe conflicts;
- effective-time ordering;
- source accumulation;
- the README contract test.

No natural-language extraction.
