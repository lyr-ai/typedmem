# D3 proposal: from "changing facts" to "governed memory evolution"

**Status:** Proposal. It is not a decision, and it does not supersede D1 unless the
test below supports it.
**Date:** 2026-09-27
**Owner decision it would replace:** D1

## The decision in force: D1

D1 was decided during Heed plan run 2 (recorded in `.heed/project.json`):
**states first; the pre-0.9 typed-memory core goes under "Advanced".**

The README follows D1:
- the hero is the Truth Through Time still (`account.plan`: Free → Pro →
  Enterprise, with a Pro record arriving late);
- the core line is "The old value isn't false. It is no longer current.";
- the pre-0.9 core starts at README:105, "Beyond states: contract-driven memory".

(D1 and D2 here are owner decisions. They are unrelated to the D1/D2 scenario ids
in `docs/evaluation-plan.md`.)

## Hypothesis

The current hero may **over-compress TypedMem into a temporal-state utility**. A
stranger may read it as "old data has a timestamp, so don't overwrite newer data"
and ask why this isn't a temporal table, version history or effective date.

A broader problem-space framing may better explain why the repository contains
conflict, provenance, policies, history and replay, without leading with
implementation complexity.

## What D3 would change

```text
Current (D1):
changing facts
→ states
→ advanced typed memory

Proposed (D3):
governed memory evolution
→ changing state as the first concrete case
→ deeper mechanisms
```

If adopted, the README order would become:
1. **Hero:** the problem space: the kinds of change a long-lived agent's memory
   goes through. It shows problems a user recognizes, not architecture: no
   `ConflictPolicy`, `DomainProfile`, `MemoryEvent` or `TransitionEngine` on the
   first screen.
2. **First concrete case:** changing facts. Truth Through Time moves here. It is
   kept as it is, not redone.
3. **The other cases,** then contracts, architecture and API. Details move to docs
   where the README duplicates them.

The hero's problem space uses only what has evidence today:

| Problem | The question it answers | Evidence today |
|---|---|---|
| **Change** | What is true now, and what used to be true? | Strongest observed pull |
| **Conflict** | What if sources disagree? | Observed pull |
| **Provenance** | Where did this come from, and whom to trust? | Observed pull |
| **History / audit** | How did memory get here? | Demonstrated in tests; no observed outside pain |

**Lifecycle** (goal resolution, preference drift, summaries; the `evolvers`
capability) is **not** in the hero. See "Evidence today".

Tagline candidates, to test rather than pick: "Memory that knows how to change.",
"Governed memory for long-lived AI agents.", and the current "Memory for AI agents
when facts change." Whichever wins, it may not name lifecycle.

## What D3 does not claim

- That lifecycle or evolvers have demonstrated market pull. They don't.
- That every TypedMem feature belongs in the hero.
- That broader positioning is necessarily better than the current one.
- That the current hero is failing. Nobody outside the project has said so yet.

## Evidence today

From `/beacon value` v0.1 (2026-09-27) and `/beacon` launch research. Pain strength
is independent people, counted by the validator.

| Value (level) | Pains it answers |
|---|---|
| V1 Know which value is current, keep the old ones (demonstrated) | P1 (9 people), P2 (5) |
| V2 Explicit conflict instead of a guessed current value (demonstrated) | P1, P4 (2) |
| V3 Where every value came from; a trusted source outranks a guess (demonstrated) | P2, P4 |
| V4 Rebuild and audit how memory reached its state (demonstrated) | none observed |
| V6 Per-type rules for domain memory (demonstrated) | P4 |
| `evolvers` (drift, goal resolution, summaries) | **no mapped value; no observed pain** |
| Reinforcement (repeated evidence from several sources) | not a value in the map yet |

Pains, in their authors' words:
- P1: the old fact and its replacement both come back, and the agent has to guess
  which is current.
- P2: people want a validity window and history, not a silent overwrite or delete.
- P3 (4 people, **no mapped value**): stale memories resurface silently; nothing
  checks whether they still hold.
- P4: different agents or sessions store contradictory facts, and nothing decides
  between them.

One measured fact **supports the hypothesis**. In the pre-registered 0.9.3
measurement (reliagent-bench `measure/states-0.9.3`,
`external/results/states-0.9.3.md`), states **only tie** the keep-both and
bitemporal baselines on the history runs (LongMemEval KU 65/65 and GoodAI 9/9 for
each of the three). On change over time alone, a bitemporal table does as well.
The variants differ only where sources disagree (Mode A). There, states report a
conflict instead of picking a winner: authority 0.50, against 1.00 for typed memory.
That is by design, not a better score. What sets TypedMem apart is how it handles
disagreement and trust, which is what D3 would put next to change.

## Unknown

> **Does the current hero actually make strangers perceive TypedMem as trivial?**

Today this is the owners' hypothesis, not an observation.

## How it would be tested

**Not before the kai #1702 experiment is recorded** (check 2026-09-29/30). The README
is part of that experiment's environment and stays unchanged until then. A reply
that reads TypedMem as "just a temporal table" is itself evidence for D3.

Then an A/B comprehension test:
- **A:** the current first screen.
- **B:** a problem-space first screen, drafted only for the test. It stays local,
  and uses only the four problems in the table above.

Each reader sees one version for 10 seconds, then answers the same questions in
order:
1. What problem does this project solve?
2. How is it different from storing memories in a vector database or an ordinary
   state store?
3. What kind of project would make you consider using it?
4. Last: would you keep reading or consider trying it? Why?

There is no "which do you like?" question: the test measures the mental model
each version creates, not taste. Readers are people who haven't seen TypedMem.
Fresh model readers can be a cheap first pass, but they are labelled as a proxy
and can't decide the question alone.

**Decision rule, fixed now, before any reader:**
- **Adopt D3 (supersede D1)** if A's answers mostly reduce TypedMem to keeping old
  versions of facts, while B's answers name governing how memory changes,
  conflicts, or keeps evidence and history, and B is no worse on question 4.
- **Keep D1** if B's answers mostly read as "a complicated agent-memory framework",
  or A's answers are clear, specific and differentiated.
- **Record as inconclusive** otherwise; D1 stays.

Either outcome is acceptable.

## If adopted

In order: the new hero, README reordering with details moved to docs, then
Truth Through Time as the first concrete case. Nothing on this list starts before
the decision.
