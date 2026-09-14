# Backlog — observed real-world failure patterns

A record of long-term-memory failure patterns reported by practitioners or
measured in evaluation, mapped to where each sits on the state loop. **Not a
roadmap.** Nothing below is scheduled. The current wedge is item 1 and stays
the only wedge until its Phase 2 is finished; the rest are ordered by
judgement, to be re-ordered when item 1 is done.

```text
source / observation
      ├── identity        whose is it?                     attribution provenance
      ├── authority       may it override?                  authority provenance
      ├── version / hash  is the source still the source?   lineage validity
      └── lineage
            ↓
         memory           validity interval · confidence · state type
            ↓
       governing state    resolution — the current wedge
            ↓
        agent action
            ↓
          outcome         verified result → back to source
```

## Three kinds of provenance, kept apart

| kind | question | measured |
|---|---|---|
| attribution | whose memory is this? | LoCoMo speaker-swap (external triage); the only external case where a memory's source affects gold |
| authority | whose observation may govern state? | Mode A Category A; Mode B Family A — matched by a fixed source ranking (BRQ1, F3) |
| **lineage validity** | is the evidence that justified this memory still true? | not yet |

Lineage validity is distinct from the memory's own validity window. A memory
can be inside `[valid_from, valid_to)`, from a high-authority source, and
wrong — because the thing it was derived from changed:

```text
code @ hash A   →   memory "config lives in foo.py"     (no valid_to; nothing in the memory changed)
code @ hash B   →   foo.py no longer exists              the memory's evidence is gone
```

`memory validity ≠ source validity`. Reported production shape: a note
written three weeks ago about code that has since changed; the agent trusts
it because it is shorter and reads like a conclusion. Reported fix: bind each
memory to a content hash of its source; when the source changes, **flag** the
memory rather than silently rewriting it. The user-facing version is plainer
than any authority value: *don't let an agent trust a memory after the source
that justified it has changed.* Coding agents, docs, config and external
systems are exactly the sources that change.

## Ordered backlog

1. **Current — typed governing-state semantics / global-policy stress test.**
   reliagent-bench PR #5. Does any fixed global merge ordering work across
   heterogeneous state types? Nothing else is added to it.
2. **Next candidate — source-linked invalidation / lineage validity.** Test
   shape: a memory derived from an artefact; the artefact changes; is the
   memory surfaced as suspect before the agent acts on it? Metric:
   stale-evidence action rate. Would need a source hash on `Source` and a
   read-time check; neither exists. Most concrete item; easiest to explain.
3. **Repeated-failure / learned-strategy memory.** Mode B BRQ3, inconclusive:
   the B2-lite tasks solved themselves from context. Needs execution-grounded
   tasks where the failing strategy is not signposted. Separate design.
4. **History and governing state coexisting.** Issue #5: `replace` keeps one
   governing value and no queryable past; `keep_both` keeps the past and lets
   no guard fire. Externally reproduced on 11 LongMemEval + 5 GoodAI items.
5. **Compaction / materialisation at scale.** Reported: long histories end in
   compaction problems, not contradiction problems. Nothing in the current
   evaluation reaches it.
6. **Policy re-evaluation diff.** Replay restores decisions; a policy change
   cannot yet show which historical decisions it would have changed.
7. **Decision-context-dependent governing state.** "The remembered failure
   does not apply here" (Mode B N-04). One scenario, zero false avoidance.

## Rules

- An item enters with a *reported* failure (one line: who, what) or a
  *measured* one (which analysis) — never with a design.
- An item leaves when it becomes a frozen evaluation design with
  pre-registered predictions, not when it becomes a feature.
- Nothing here changes the current wedge's scope.

## Sources

Public thread on the "memory is not a list of facts" write-up (2026-09):
bitemporality and supersession; replay under policy evolution; SCD as the
mature baseline; end utility as not repeating a known failure; source-hash
invalidation when the underlying code changes; "authority, lineage,
lifecycle, procedural direction" as the shape of a reasoning cache — lineage
named independently by two reporters. Motivation, not evidence.
