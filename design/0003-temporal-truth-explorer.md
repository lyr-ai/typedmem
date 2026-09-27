# Design 0003 — Temporal Truth Explorer

**Status:** Accepted 2026-09-26, with the decisions in section 22  
**Product:** TypedMem  
**Scope:** Interactive product explanation / visualization  
**Target release:** After v0.9.1 (the scenario 3 fix); must not block distribution  
**Working title:** Temporal Truth Explorer  
**Visual family:** Reliable AI Systems / editorial scientific style  
**Primary question:** *What was true then, and what is true now?*

---

## 1. Motivation

TypedMem v0.9 introduces a simple state abstraction:

```python
mem.set(...)
mem.get(...)
mem.history(...)
```

The core behavior is easy to state but harder to appreciate from API documentation alone.

A state can change over time. An old value can stop being current without becoming false historically. Information can arrive after the period in which it was true. Sources can disagree, in which case TypedMem must expose the conflict rather than silently inventing a current truth.

The visualization should make these semantics understandable **before the reader understands TypedMem's implementation, conflict policies, temporal resolver, or storage model**.

It is not intended to visualize every feature in TypedMem.

Its job is to make four ideas visually obvious:

1. **Current truth is different from historical truth.**
2. **History is preserved when state changes.**
3. **Effective time is different from arrival time.**
4. **Unresolvable disagreement remains a conflict rather than being silently overwritten.**

---

# 2. Canonical example

Do **not** use:

> Alice works at OpenAI → Alice works at Anthropic.

Employment is semantically ambiguous: people can have multiple employers, consulting relationships, overlapping roles, etc.

Instead use a naturally single-valued product state:

```text
account.plan
```

Canonical history:

```text
January      Free
April        Pro
September    Enterprise
```

At the present time:

```text
CURRENT
Enterprise

HISTORY
Free → Pro → Enterprise
```

This example has several useful properties.

It is immediately understandable to a developer or SaaS engineer; it is naturally modeled as one current state; previous values remain meaningful historical facts; late-arriving records are plausible; conflicting systems are plausible; and no real company/person names distract from the underlying concept.

---

# 3. Core visual metaphor

The visual metaphor is:

> **Threads through time.**

A state is not represented as a collection of unrelated memories.

It is represented as a temporal thread whose value changes.

For example:

```text
Jan                 Apr                         Sep                    NOW
│                    │                           │
FREE ━━━━━━━━━━━━━━━━○
                     ╲
                      ● PRO ━━━━━━━━━━━━━━━━━━━━○
                                                 ╲
                                                  ● ENTERPRISE ━━━━━━━●
                                                                       ↑
                                                                    CURRENT
```

### Visual grammar

| Element | Meaning |
|---|---|
| Solid line | Value valid during this period |
| `●` | Value becomes current |
| `○` | Value stops being current |
| Faded historical segment | Previously true state |
| Strong final segment | Current state |
| Parallel competing threads | Conflicting claims |
| Knot / intersection | Unresolved conflict |
| Source annotation | Provenance of the claim |
| Timeline position | Effective time, not arrival order |

The visualization must never imply that historical values were simply incorrect.

The key conceptual distinction is:

> **The old value isn't false. It is no longer current.**

---

# 4. Scenario 1 — Facts change

This is the default scenario.

## Input

Conceptually:

```text
January
account.plan = Free

April
account.plan = Pro

September
account.plan = Enterprise
```

## Visual sequence

### Act 1 — Initial truth

```text
FREE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━●
                                              CURRENT
```

Narrative:

> The account starts on Free.

### Act 2 — State changes

Pro arrives.

Free's validity line ends and Pro begins.

```text
FREE ━━━━━━━━━━━━━━━○
                    ╲
                     ● PRO ━━━━━━━━━━━━━━━━━━━━━●
                                                CURRENT
```

Then Enterprise:

```text
FREE ━━━━━━━○
            ╲
             ● PRO ━━━━━━━━━━━○
                              ╲
                               ● ENTERPRISE ━━━━━━━━━●
                                                    CURRENT
```

### Act 3 — Current truth

The visual settles on:

```text
CURRENT
Enterprise
```

with history underneath:

```text
Free → Pro → Enterprise
```

Narrative:

> **TypedMem keeps what is true now without erasing what used to be true.**

---

# 5. Scenario 2 — Facts arrive late

This scenario explains one of TypedMem's most important temporal properties.

## Initial knowledge

TypedMem receives:

```text
January     Free
September   Enterprise
```

So initially:

```text
FREE ━━━━━━━━━━━━━━━━━○
                      ╲
                       ● ENTERPRISE ━━━━━━━━━━━━━●
                                               CURRENT
```

## Late arrival

Later, an older record arrives saying:

```text
April
account.plan = Pro
```

Critically, **Pro arrives after Enterprise was already stored**.

The animation should first show Pro entering from the present/right-hand side, representing arrival time.

It then moves backward into its correct effective-time position:

```text
FREE ━━━━━━━○
            ╲
             ● PRO ━━━━━━━━━━━○
                              ╲
                               ● ENTERPRISE ━━━━━━━━━●
                                                    CURRENT
```

Enterprise remains current.

## Key line

> **It arrived last. It wasn't true last.**

Secondary explanation:

> TypedMem orders state by when a value became true, not by when the record arrived.

This scenario must visually distinguish:

```text
arrival order
```

from:

```text
truth order
```

without requiring the reader to know the term "bitemporal."

---

# 6. Scenario 3 — Sources disagree

This scenario explains `StateConflict`.

Assume two sources describe the same state for the same effective period.

Example:

```text
Billing system
account.plan = Enterprise

CRM
account.plan = Pro
```

Neither claim can safely be ordered as a normal state transition.

## Visual

Instead of:

```text
Pro → Enterprise
```

show two parallel claims converging on the same effective period:

```text
BILLING       ━━━━━━━━━━━ ENTERPRISE ━━━━━━━━━━━
                              ╲
                               ╳   CONFLICT
                              ╱
CRM           ━━━━━━━━━━━━━ PRO ━━━━━━━━━━━━━━━━
```

The intersection/knot is the central visual element.

Use the accent failure/conflict color sparingly here.

Do **not** automatically animate one claim winning.

## Result

```text
CURRENT
unresolved
```

Narrative:

> **When sources disagree and TypedMem cannot establish an ordered change, it doesn't silently choose.**

On interaction, expose provenance:

```text
Enterprise
source: billing

Pro
source: crm
```

This should correspond to the actual behavior of:

```python
mem.get("account.plan")
```

raising `StateConflict`.

The visualization must not show a winner when the product would raise a conflict.

---

# 7. Scenario 4 — Authority resolves a conflict (out of v1 scope)

**Removed from v1.** Under current semantics, stronger authority alone does not resolve a same-time conflict; resolution requires later evidence (design 0002 §4). Showing it would add a second temporal rule to the first explorer. Kept as future work; no animation.

---

# 8. Interaction design

The explorer should have three primary scenario tabs:

```text
Facts change
Facts arrive late
Sources disagree
```

Default:

```text
Facts change
```

The primary control is:

> **▶ Play**

The animation should be short enough to replay without frustration: approximately 4–6 seconds.

After completion:

> **↺ Replay**

---

# 9. Time scrubber

After the initial animation completes, the user can scrub through effective time.

Example:

```text
Jan ━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━ Sep
```

At January:

```text
CURRENT AT THIS TIME
Free
```

At June:

```text
CURRENT AT THIS TIME
Pro
```

At present:

```text
CURRENT AT THIS TIME
Enterprise
```

The wording **"Current at this time"** is intentional.

It reinforces that current truth is evaluated *as of* a point in time.

The scrubber is secondary interaction; it should not be required to understand the first animation.

---

# 10. Provenance

Provenance should be visible but subordinate.

For example:

```text
Free          source: signup
Pro           source: billing
Enterprise    source: billing
```

Do not turn the first layer into a provenance graph.

On click/tap of a value, reveal:

```text
VALUE
Enterprise

VALID FROM
Sep 1

SOURCE
billing

STATUS
current
```

The first visual layer remains:

> truth through time.

The second layer explains why.

---

# 11. Visual style

TypedMem should share a visual family with AgentSeism without copying AgentSeism's seismic metaphor.

Shared style:

- warm ivory/paper background;
- editorial serif for narrative statements;
- monospace for keys, values, dates, and measurements;
- charcoal primary ink;
- muted sage/mineral accent;
- cinnabar reserved for conflict;
- fine scientific annotation lines;
- substantial negative space;
- minimal cards and pills;
- no generic AI gradients;
- no glassmorphism;
- no neon/cyber aesthetic.

### TypedMem-specific motif

AgentSeism:

> tremor → rupture

TypedMem:

> **thread → transition → history → knot**

The projects should look like siblings, not clones.

---

# 12. Motion language

Motion must communicate semantics rather than decorate the page.

### Normal state change

A new value begins where the old value ends.

Motion should feel continuous:

```text
Free ─────○
          ╲
           ● Pro
```

### Historical state

The old segment becomes visually quieter but remains visible.

It must **not disappear**.

### Late arrival

The new record first appears as newly arrived information, then moves to its correct effective-time position.

This is the strongest animation in Scenario 2.

### Conflict

Two claims approach the same state/time region but neither replaces the other.

They form a visible knot/intersection.

No winner animation occurs.

### Reduced motion

With `prefers-reduced-motion`, show the final state immediately while preserving all semantic distinctions.

---

# 13. Data honesty

This is a hard requirement.

Like the AgentSeism Explorer, the TypedMem Explorer must be generated from **real product behavior**, not hand-authored marketing outcomes.

The three scenarios should run through the actual TypedMem API.

For example:

```python
mem.set(...)
mem.get(...)
mem.history(...)
```

The generated visualization data should contain the actual:

- current value;
- history ordering;
- effective dates;
- sources;
- conflict state.

A test must fail if the product behavior and visualization fixture diverge.

The explorer must never maintain a separate implementation of TypedMem's resolution semantics.

---

# 14. README integration

The README first screen remains simple.

Suggested structure:

```text
Agent memory stores facts. Facts change.
Which one is true now?

TypedMem keeps the current truth without erasing
what used to be true — or where it came from.

[set → set → get → history transcript]

[static Temporal Truth frame]

▶ Explore how truth changes
```

The static frame should show:

```text
Free → Pro → Enterprise
                  ↑
               CURRENT
```

Do not embed a complicated interactive application directly in the GitHub README.

The static visual links to:

```text
lyr-ai.github.io/typedmem/explorer/
```

---

# 15. Blog integration

The same visualization should support a short product/technical story.

Potential title:

> **Yesterday's Fact Isn't Necessarily Today's Truth**

or:

> **Memory Gets Hard When Facts Change**

The visual should be reusable without requiring the reader to know TypedMem.

This is important for distribution.

The story begins with the problem, not the package:

```text
An AI remembers that an account is on Pro.

Later it learns the account upgraded to Enterprise.

Then an old billing record arrives saying the account
was on Pro in April.

What should it believe now?
```

The visualization answers before TypedMem is introduced.

---

# 16. Social / Reddit asset

Produce a short GIF/MP4 from Scenario 2.

Recommended sequence:

```text
Free
  ↓
Enterprise becomes current
  ↓
old Pro record arrives later
  ↓
Pro moves backward into history
  ↓
Enterprise remains CURRENT
```

Final frame:

> **It arrived last. It wasn't true last.**

Potential Reddit title:

> **What should an AI remember when new information describes the past?**

Another:

> **I kept running into a weird agent-memory problem: the newest memory isn't always the current truth**

This should be tested independently of TypedMem branding.

---

# 17. Non-goals

Version 1 is **not**:

- a generic knowledge-graph viewer;
- a vector-store visualization;
- a memory debugger;
- a graph database browser;
- an ontology editor;
- a natural-language extraction UI;
- a production dashboard;
- a visualization of every TypedMem memory type;
- a hosted SaaS application.

Do not add:

```text
nodes everywhere
force-directed graphs
embeddings
3D
memory clusters
chat UI
```

unless a later product need specifically requires them.

The visual should remain centered on:

> **one state changing through time.**

---

# 18. Implementation architecture

Keep it close to the AgentSeism Explorer pattern.

Suggested pipeline:

```text
TypedMem real API
      ↓
scenario generator
      ↓
small deterministic JSON
      ↓
D3 visualization
      ↓
static preview + interactive explorer
```

The browser should not reimplement the TypedMem kernel.

Example generated structure:

```json
{
  "key": "account.plan",
  "as_of": "2026-09-27",
  "current": "Enterprise",
  "history": [
    {
      "value": "Free",
      "valid_from": "...",
      "valid_to": "...",
      "source": "signup",
      "status": "previous"
    },
    {
      "value": "Pro",
      "valid_from": "...",
      "valid_to": "...",
      "source": "billing",
      "status": "previous"
    },
    {
      "value": "Enterprise",
      "valid_from": "...",
      "valid_to": null,
      "source": "billing",
      "status": "current"
    }
  ]
}
```

Conflict scenario additionally exposes competing claims rather than a `current` value.

---

# 19. Acceptance criteria

The first version is complete when all of the following are true:

1. A stranger can identify the current value without reading documentation.
2. A stranger can see that previous values are preserved rather than deleted.
3. Scenario 2 makes it visually obvious that arrival order and effective-time order differ.
4. Scenario 3 has no visual winner when `mem.get()` would raise `StateConflict`.
5. Every displayed value, ordering, source, and conflict comes from actual TypedMem execution.
6. A test detects drift between TypedMem behavior and explorer data.
7. The explorer works without an API key.
8. The explorer requires no backend.
9. It works on mobile.
10. Reduced-motion mode remains understandable.
11. A static frame works in README/blog/social contexts.
12. The entire first scenario can be understood in roughly 5–10 seconds.
13. The visualization does not delay the TypedMem v0.9.0 release.

---

# 20. Success criterion

The visualization is **not** successful merely because it is attractive.

The five-second comprehension test is:

Show someone the completed first scenario, hide it, and ask:

> **What did that picture mean?**

A successful answer is approximately:

> "The account used to be Free, then Pro, and now Enterprise. The old values are still kept."

For Scenario 2:

> "Something arrived later, but because it described the past it didn't replace the current value."

For Scenario 3:

> "Two sources disagree, so the system refuses to pretend it knows which one is current."

If those answers require explaining TypedMem first, the visualization has failed.

---

# 21. Delivery order

Do **not** block v0.9.0 on this work.

Order (revised 2026-09-26: distribution does not wait for the explorer):

```text
1. Release the 0.9.x correctness fix (0.9.1: conflict sets contain only
   simultaneously plausible values)
2. Share the plain changing-facts story
3. Build the scenario generator from the real TypedMem API
4. Build the explorer
5. Update the README to the canonical account.plan example + explorer link
6. Redistribute with the visual story
```

The main product hypothesis being tested remains:

> **Does the changing-facts problem that previously generated discussion actually convert into installs, stars, questions, and real usage when the product makes the solution obvious?**

The visualization exists to make that product idea easier to understand. It should not become a reason to postpone testing it.

---

# 22. Decisions (2026-09-26)

1. **Scenario 3 depends on 0.9.1.** 0.9.0 wrongly kept the earlier value (Free) in the conflict. Fixed in 0.9.1 under the invariant in design 0002 §4: a conflict set contains only values that remain simultaneously plausible at the queried time. Verified from a fresh PyPI install: scenario 3 gives exactly `Enterprise` vs `Pro`, with Free as history.
2. **Scenario 4 is out of v1** (section 7).
3. **One canonical example.** When the explorer lands, the README moves from `alice.employer` to `account.plan`. The README contract test keeps the transcript real.
4. **Location.** The explorer is a standalone static page in this repo's docs site, at `https://lyr-ai.github.io/typedmem/explorer/`, outside the main mkdocs nav. It can't live in the blog repo: this repo's project Pages site owns `/typedmem/`.
5. **Distribution first.** The plain changing-facts story is shared before the explorer exists. The explorer is the second wave (section 21).
