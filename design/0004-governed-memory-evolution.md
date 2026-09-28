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

**External signal: kai #1702 (2026-09-27).** A maintainer already building
explicit revision states, unresolved conflicts and an immutable event log found
the valid-time rule novel enough to adopt into their own roadmap. They opened
[kai #1790](https://github.com/dcellison/kai/issues/1790) and credited
TypedMem's design. This counts against the hypothesis that the changing-facts
framing is inherently trivial: the example may be simple while the rule
underneath is not. It is one data point, not a positioning decision.

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

### Test protocol (fixed 2026-09-27, before any reader)

The kai experiment was recorded on 2026-09-27 (L3; see "Evidence today"), so the test
can run.

**Readers.** 10 people, **5 per version**. Each person sees **one** version only, so
the second can't be coloured by the first. Assignment alternates A, B, A, B… in the
order people agree to take part. People who have seen TypedMem, its README, or the
Note 03 blog post don't take part. Readers aren't told this is a positioning test,
and D1/D3 aren't explained.

**Materials.** Both versions use the same frame: a GitHub-style README first screen,
same width, same image size. **A** is the current README down to "Try it".
**B** is a local draft with:
- the tagline "Memory that knows how to change.";
- the four problems with evidence (change, conflict, provenance, history/audit),
  and no lifecycle;
- the contract-tested billing-vs-crm example from `docs/states.md`.

Every claim in B must be true of TypedMem today. Only one tagline is tested, because
five readers can't compare several.

**Questions.** The four above, in order, after 10 seconds of viewing. **Question 2
is the primary one** ("How is it different from a vector database or an ordinary
state store?").

**Codebook.** Question 1 and question 2 answers get exactly one code each:
- **T, temporal utility:** only keeping old versions, timestamps, history, or which
  value is newest.
- **G, governed change:** names at least one thing beyond time: disagreement
  between sources, which source to trust or where a value came from, or rules for
  how memory changes.
- **C, complex or unclear:** can't say what it does, or "a complicated
  agent-memory framework", or a generic "memory library".
- **O, other.**

Question 4 is coded **yes** (would keep reading or try) or **no**. Two people code
the answers independently. If they disagree, that reader's code is **C**.

**Decision (with 5 per version, "mostly" = 4 of 5):**
- **Adopt D3** if ≥4/5 of A readers are **T** on question 2, **and** ≥4/5 of B readers
  are **G** on question 2, **and** B has at least as many question-4 "yes" answers as A.
- **Keep D1** if ≥4/5 of B readers are **C** on question 2, **or** ≥4/5 of A readers
  are **G** on question 2.
- **Inconclusive** otherwise, for example 3/5 against 3/5. Record it and keep D1. No
  readers are added after the fact to reach a result.

## If adopted

In order: the new hero, README reordering with details moved to docs, then
Truth Through Time as the first concrete case. Nothing on this list starts before
the decision.
