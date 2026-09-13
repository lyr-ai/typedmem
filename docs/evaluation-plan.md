# TypedMem Evaluation: From State Semantics to Empirical Evidence

**Status:** Design
**Date:** 2026-09-13
**Phase:** Diagnostic benchmark → external validation → paper decision

## 1. Motivation

TypedMem has reached a natural implementation milestone. The current system
makes several explicit choices about long-term agent memory:

- provenance authority is distinct from confidence;
- observation time is distinct from temporal validity;
- conflict resolution operates over typed state rather than retrieval results
  alone;
- replacement semantics can vary by memory type;
- state-changing events contain enough information for deterministic replay.

The next question is no longer whether these abstractions are internally
consistent. It is:

> **Do these semantics measurably improve the reliability of long-horizon
> agents?**

This evaluation phase answers that question before TypedMem grows additional
state-management abstractions. The goal is not to benchmark every feature or
to maximise a leaderboard score. It is to test a small number of falsifiable
claims about memory state semantics.

---

## 2. Research questions

### RQ1 — Does provenance-aware conflict resolution prevent state corruption?

When an explicit user statement conflicts with a newer but lower-authority
inference, does authority-aware resolution preserve the correct state more
reliably than recency/confidence-based resolution?

```text
Session 1     User: I live in San Jose.
Session 2     The agent infers from indirect context: "The user lives in Seattle."
Later         Where does the user live?
```

The distinction is not retrieval quality. Both memories may be retrieved. The
question is which one becomes authoritative state.

### RQ2 — Does explicit temporal validity reduce stale-state and temporal reasoning errors?

Can separating observation time from validity time improve answers when
information is learned after it became true; a state has expired; a future
state has been declared but is not yet active; or a query asks about
historical rather than current state?

```text
January        "I live in San Jose."
September 10   "I moved to Seattle on August 1."

Where did I live on July 15?     → San Jose
Where did I live on August 15?   → Seattle
Where do I live now?             → Seattle
```

A timestamp-only system has insufficient semantics to represent this cleanly.

### RQ3 — Do typed conflict rules outperform one universal replacement policy?

Different memory types represent different forms of state. A deadline may
care primarily about the newest effective state; a biographical fact may
require both temporal and confidence guards; other types may need different
update semantics.

> A single global conflict rule will systematically fail on some memory
> types, while type-specific rules can preserve the intended state semantics.

This must be tested rather than assumed.

---

## 3. Explicit non-goals

**Replay is not an accuracy ablation.** Replay provides reproducibility and
auditability. It is tested as `historical events → deterministic
reconstructed state`, not included in an accuracy ladder to make the full
system appear stronger.

**This is not a general memory leaderboard.** The diagnostic benchmark
isolates specific failure modes. General long-term-memory performance is
evaluated separately on existing external benchmarks (§20).

**This is not yet a large benchmark.** The first version contains roughly
40–60 controlled scenarios. The purpose is to learn whether the mechanisms
produce measurable separation before investing in hundreds of examples.

**No new TypedMem architecture work.** During the diagnostic phase, do not
add materialised-state rebuild, policy migration, event compaction, further
resolution DSLs, or new validity semantics — unless an evaluation result
exposes a concrete blocker.

---

## 4. Evaluation architecture

```text
Scenario
   ↓
Memory construction / updates
   ↓
Memory system variant
   ↓
Resolved state
   ↓
Query / decision
   ↓
Evaluation
```

The separation is what makes a failure attributable to one of: extraction,
storage/update, conflict resolution, retrieval, answer generation. The first
experiments minimise extraction and generation noise wherever possible.

---

## 5. Two evaluation modes

### Mode A — State-level evaluation (primary)

Scenarios construct the intended memory writes directly, without an LLM
interpreting a conversation:

```text
write A:  content = lives in San Jose   source = explicit user   authority = 1.0
write B:  content = lives in Seattle    source = inferred        authority = 0.3
```

Then inspect the resolved state. This isolates TypedMem's actual mechanism,
is deterministic, and is cheap.

```text
State Accuracy  =  correct final state / evaluated states
```

Mode A answers: *if the memory writes are correct, does the state-management
layer resolve them correctly?*

### Mode B — End-to-end agent evaluation (secondary)

```text
conversation → memory extraction → TypedMem → retrieval → answer
```

This introduces realistic noise and answers: *does the state-level
improvement survive inside an actual agent pipeline?*

Mode A comes first. Otherwise an extraction failure looks like a
conflict-resolution failure.

---

## 6. System variants

Not `baseline vs full TypedMem` — that shows whether the whole helps, not
why. Controlled ablations:

| variant | what it is | expected to improve |
|---|---|---|
| **V0** retrieval baseline | memories stored independently; no authority guard; timestamp as the only temporal signal; no validity window; one global replacement strategy | — (establishes the failure rate of memory-as-records) |
| **V0-scd** bitemporal baseline | a slowly-changing-dimension / bitemporal table: valid-time and transaction-time columns, supersession by newest valid-time, no notion of source authority or confidence | the strongest *non-agent* baseline; what a data engineer would build — see §24 |
| **V1** state resolver | TypedMem's state/conflict machinery with the mechanisms under evaluation disabled | separates "explicit state resolution exists" from each semantic addition |
| **V2** + provenance authority | V1 plus authority-aware replacement protection | authority-conflict scenarios; little or none elsewhere |
| **V3** + temporal validity | V2 plus `valid_from` / `valid_to`, `as_of` semantics, future-validity filtering | retroactive updates, expired state, future state, historical queries |
| **V4** full typed resolution | V3 plus per-type replacement guards | mixed-type scenarios where a universal policy is intentionally insufficient |

The localisation matters. If authority improves every unrelated category
dramatically, investigate leakage or confounding before celebrating.

---

## 7. Diagnostic benchmark v0

Target ~55 scenarios; quality over count. Each scenario may carry several
queries.

| category | target |
|---|---:|
| Provenance / authority conflict | 15 |
| Temporal validity | 15 |
| Typed resolution | 15 |
| Mixed / adversarial | 10 |
| **Total** | **55** |

---

## 8. Category A — Provenance / authority (RQ1)

| id | scenario | correct behaviour | isolates |
|---|---|---|---|
| A1 | explicit user "San Jose"; later inference "probably Seattle" | state stays San Jose | the basic veto |
| A2 | existing authority 1.0 / confidence 0.70; incoming authority 0.3 / confidence 0.98 | incoming does not replace | authority from confidence |
| A3 | incoming inference is substantially newer | IGNORE | authority from recency |
| A4 | existing state is newer; incoming has stronger provenance but describes an older state | incoming does not automatically replace | the asymmetry: lower authority → veto; higher authority ≠ automatic victory |
| A5 | equal authority on both sides | falls back to the configured temporal/confidence rules | that the benchmark is not testing "authority always wins" |

---

## 9. Category B — Temporal validity (RQ2)

| id | scenario | expected |
|---|---|---|
| B1 | retroactive update: observed Sep 10, "moved on Aug 1" | historical queries respect Aug 1, not Sep 10 |
| B2 | historical query before transition, `as_of` Jul 15 | San Jose |
| B3 | historical query after transition, `as_of` Aug 15 | Seattle |
| B4 | exact boundary: `A.valid_to = T`, `B.valid_from = T` | `T − ε` → A; `T` → B (pins the half-open interval) |
| B5 | future state: "starting Oct 1, Postgres" | before Oct 1, current DB ≠ Postgres; after, = Postgres; the future memory must not shadow current state early |
| B6 | expired state: `valid_to < now` | absent from current state; recoverable by historical lookup |

---

## 10. Category C — Typed resolution (RQ3)

Scenarios must genuinely justify different semantics. Do not manufacture type
differences merely to demonstrate configurability.

Candidate types:

- **Deadline** — "The deadline is Friday." / later "The deadline moved to
  Monday." Recency and effective state may dominate.
- **Biographical fact** — explicit fact plus an uncertain conflicting
  inference. Both provenance and confidence may matter.
- **Goal / plan** — "I plan to deploy in October." / later "now planned for
  November." Temporal semantics may differ from a durable fact.

**Before finalising these scenarios, define the intended semantics for each
type independently of TypedMem's implementation.** Otherwise the labels
encode whatever TypedMem currently does, and the benchmark tests nothing.

---

## 11. Category D — Mixed and adversarial

| id | scenario |
|---|---|
| D1 | low-authority inference that is newer, more confident, and temporally inconsistent |
| D2 | high-authority statement describing an older historical state |
| D3 | a future state conflicting with the current state |
| D4 | multiple updates across three sessions |
| D5 | irrelevant but semantically similar memories competing during retrieval |
| D6 | correct memory is older in observation time but newer in effective validity |

Most useful after the individual mechanisms pass their isolated tests.

---

## 12. Scenario format

Declarative, inspectable, and described independently of a specific TypedMem
API call wherever possible:

```yaml
id: authority_001
category: authority

memories:
  - content: "User lives in San Jose"
    source_type: explicit_user
    authority: 1.0
    confidence: 0.70
    observed_at: ...
  - content: "User lives in Seattle"
    source_type: model_inference
    authority: 0.3
    confidence: 0.95
    observed_at: ...

queries:
  - type: current_state
    expected: "San Jose"

expected_transition:
  action: ignore
```

---

## 13. Labels

Every scenario carries two labels.

**Outcome label** — what state should be returned (`San Jose`).

**Mechanism label** — why:

```text
authority_veto · effective_from · validity_expired · validity_future ·
validity_boundary · confidence_guard · type_specific_resolution
```

The mechanism label is what makes failure analysis possible beyond aggregate
accuracy.

---

## 14. Metrics

| metric | definition | mode |
|---|---|---|
| **state accuracy** (primary) | correct resolved state / total states; overall and per category | A |
| **transition accuracy** | expected transition performed (REPLACE / IGNORE / KEEP) | A |
| **temporal accuracy** | correct state at the requested `as_of` / temporal queries | A |
| **corruption rate** | correct states overwritten by lower-quality evidence / opportunities for such corruption | A |
| **end-to-end answer accuracy** | final natural-language answer semantically correct; kept separate from state accuracy | B |
| **end-task utility** (Phase 2B+) | task success, steps to completion, clarification questions asked, latency — on a task the agent performs *using* the memory, not a question about the memory | B, §24 |

Corruption rate is often more interpretable than accuracy for authority
scenarios: *"provenance-aware resolution reduced state corruption from X% to
Y%"* is a sentence a reader can act on.

---

## 15. Expected-result matrix

Written down before running anything:

| variant | authority | temporal | typed | mixed |
|---|---:|---:|---:|---:|
| V0 retrieval baseline | low | low | low | low |
| V0-scd bitemporal baseline | low | **high** | low | medium |
| V1 resolver | medium | low | low/medium | low |
| V2 + authority | **high** | low | low/medium | medium |
| V3 + validity | high | **high** | medium | high |
| V4 full typed | high | high | **high** | **high** |

These are hypotheses, not desired results. If the observed table disagrees,
investigate the disagreement rather than adjusting the benchmark until the
table looks right.

---

## 16. Controls against benchmark self-confirmation

A custom benchmark carries the risk of designing tasks around TypedMem and
then "discovering" that TypedMem solves them.

1. **Define expected semantics before running variants.** Labels are
   committed before comparative results are seen.
2. **Negative controls.** Scenarios that should not benefit from
   TypedMem-specific semantics: a stable fact, no conflict, straightforward
   retrieval, equal-authority consistent updates. Full TypedMem should not
   outperform the baseline everywhere.
3. **Perturb superficial details** — names, cities, dates, wording,
   ordering, confidence values, irrelevant memories — while preserving the
   semantic structure.
4. **Hold retrieval constant** for mechanism experiments: competing systems
   see the same candidate memories, so better retrieval is not mistaken for
   better resolution.
5. **External benchmark later.** Custom diagnostic results are necessary but
   insufficient for a paper claim (§20).

---

## 17. Pilot experiment

Not all 55 scenarios first. Twenty:

```text
5 authority · 5 temporal · 5 typed-resolution · 5 mixed/control
```

Run every variant. Produce:

| variant | overall | authority | temporal | typed | mixed |
|---|---:|---:|---:|---:|---:|
| V0 | | | | | |
| V1 | | | | | |
| V2 | | | | | |
| V3 | | | | | |
| V4 | | | | | |

and a failure table:

| scenario | variant | expected | actual | mechanism | diagnosis |
|---|---|---|---|---|---|

---

## 18. Pilot decision criteria

The pilot succeeds if at least one mechanism shows:

1. clear separation from its ablation;
2. improvement concentrated in the expected category;
3. no major regression on negative controls;
4. failures that can be explained mechanistically.

Statistical significance is not required from 20 cases. The pilot is looking
for signal.

---

## 19. If there is no signal

Do not add features. Diagnose in this order:

- **A. Benchmark problem** — does the scenario actually exercise the intended
  mechanism?
- **B. Adapter problem** — are the variants truly different, or is shared
  code preserving TypedMem semantics in the baseline?
- **C. Metric problem** — is answer accuracy hiding meaningful state
  differences?
- **D. Hypothesis failure** — the mechanism may not materially improve
  reliability. That is a valid result, and it is written up as one.

Only after these are understood should the implementation change.

---

## 20. Expansion after the pilot

If the pilot shows meaningful separation:

**Phase 2A — Expand the diagnostic benchmark.** Grow from ~20 to ~55
reviewed scenarios with controlled perturbations (§16.3). Every added
scenario carries both labels (§13) before it is run.

**Phase 2B — Repeated runs for Mode B.** LLM-dependent end-to-end
experiments run multiple repetitions per scenario. Report the distribution
and its interval, never a single run; treat extraction failures as a
separate, reported category rather than folding them into state accuracy.

**Phase 2C — External benchmark.** Select one or two existing
long-term-memory benchmarks with useful overlap in multi-session memory,
temporal reasoning, and memory updates. Run V0 and V4 on them, plus V2 and
V3 where the benchmark's category structure allows attribution. The purpose
is not to top the benchmark; it is to check whether the diagnostic
separation survives on tasks nobody designed around TypedMem. Report the
external result beside the diagnostic one, with the disagreements, if any,
explained rather than reconciled.

---

## 21. Paper decision

The paper is written only if, after Phase 2:

- at least two of RQ1–RQ3 show separation on the diagnostic benchmark that
  is concentrated where the expected-result matrix predicted;
- the negative controls are flat;
- Mode B preserves the direction of the Mode A result, with variance
  reported;
- the external benchmark does not contradict the diagnostic result on the
  categories they share.

If those hold, the contribution is the *state-semantics framing* and the
measured corruption reduction, not TypedMem as a library. If they do not
hold, the write-up is a negative result on the diagnostic benchmark, which
is still worth publishing as a note, and this plan's §19 diagnosis is the
content.

---

## 22. Deliverables and sequencing

```text
1. scenario schema (§12) + mechanism labels (§13)              committed first
2. adapters for V0–V4, with a test that V0 shares no resolution code with V4
3. 20 pilot scenarios, labels frozen before the first run
4. pilot run; results and failure tables committed as-is
5. decision per §18 / §19
6. Phase 2A–2C only on a positive decision
```

Where it lives: the benchmark harness and scenarios go in a separate
repository so that TypedMem's own test suite stays about TypedMem's
contract, and so that another memory system can be plugged in as a variant
without importing TypedMem. This document is the plan; the results are
recorded there, append-only, one entry per run that produced a number.

---

## 23. What changes this plan

This plan is frozen alongside the PR 1–4 milestone. It changes only if:

- a pilot scenario cannot be expressed without a TypedMem feature that does
  not exist — in which case the feature is scoped as the smallest thing that
  unblocks the scenario, and nothing more;
- the §19 diagnosis identifies an adapter or metric flaw, which is fixed in
  the harness rather than in TypedMem;
- the pilot is negative, in which case the plan's remaining phases are
  cancelled and the negative result is written up.

None of the deferred items in §3 are added on the strength of intuition
during this phase. The point of the phase is to replace intuition with a
number.

---

## 24. External feedback → evaluation implications

Four pieces of feedback on the state-semantics write-up, and where each one
lands. The priority is: absorb into the benchmark first, into the paper
framing second, into the roadmap third. **None of them opens a PR now.**

| feedback | the point | absorbed as |
|---|---|---|
| **bitemporality / supersession** (Multi-DAC) | long-horizon memory has to distinguish observation time from valid time, and "newer" is ambiguous until you say on which axis | **bitemporal correctness** — Category B already tests it; make the three query classes explicit and balanced: *current state*, *historical as-of*, *future-valid*. Add supersession chains (A superseded by B superseded by C, with a query at each interval) to B and D. |
| **replay + policy versioning** (shashank_magic) | replay should restore historical outcomes, not re-run the current policy; policy versions are part of decision provenance | **replay determinism** — a Mode A check, not an accuracy ablation (§3): same event log, two policy versions, identical replayed state. Policy migration and decision provenance stay on the roadmap (§3, §23), not in this phase. |
| **SCD / data warehousing** (presentofai) | validity windows and supersession are slowly-changing dimensions; a bitemporal table has done this for decades | **SCD baseline** — the most important item here, because it is the reviewer attack. Validity and supersession are *not* the novelty. V0-scd (§6) is the strong baseline; the claim under test is narrower: agent memory adds *noisy, inferred, provenance-dependent* updates, and a bitemporal table has no notion of which writer was entitled to write. Category A and D are where that shows; on Category B alone, V0-scd should match V3, and the matrix (§15) says so. |
| **end-task utility / domain specificity** (bestjaegerpilot) | memory correctness is intrinsic; what matters is whether the agent does the task better — and that is domain-specific | **end-task utility** — a third evaluation layer above Mode A and Mode B (§14): task success, bug rate, steps, latency, clarification count on a task the agent performs *with* the memory. Coding is the natural first domain and doubles as the external-domain validation of §20. Not in the pilot; in Phase 2B. |

Two consequences for the paper framing, recorded here so they are not
rediscovered after the results are in:

- **Related work leads with bitemporal databases and SCD**, not with agent
  memory libraries. The novelty claim is provenance-aware resolution over
  inferred updates, tested against a bitemporal baseline that already gets
  the temporal part right.
- **A result that beats V0 but not V0-scd on temporal scenarios is the
  expected result, not a failure.** It means the temporal machinery is
  correct and unoriginal — which is what §15 predicts — and the paper's
  claim rests on Category A and D, where authority and typed guards are
  doing work a bitemporal table cannot.
