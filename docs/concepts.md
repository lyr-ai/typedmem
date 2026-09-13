# Concepts

Four primitives carry the design.

## Memory

A typed dataclass — not just text in a bag.

```python
from typedmem import Memory, Source

m = Memory(
    type="claim",
    content="Drug X reduces blood pressure",
    confidence=0.85,
    subject="drug_x",
    workspace="medical",
    sources=[Source(document_id="paper_a.pdf", chunk_id="results", span=(120, 240))],
    tags=["cardiology"],
)
```

Fields:

| Field | Type | Notes |
|---|---|---|
| `type` | `str` | Built-in (`fact`/`preference`/…) or profile-defined (`claim`/`decision`/…) |
| `content` | `str` | The actual memory text |
| `confidence` | `float` | `[0, 1]`; decays per type's `half_life_days` |
| `subject` | `str \| None` | Who/what — part of the conflict slot key |
| `tags` | `list[str]` | Free-form (or constrained by `TypeSpec.allowed_tags`) |
| `workspace` | `str` | Namespace; defaults to `"default"` |
| `sources` | `list[Source]` | Provenance — see below |
| `status` | `str \| None` | E.g. `"active"`/`"resolved"` for goals |
| `superseded_by` | `str \| None` | Set by `SUPERSEDE` policy or evolvers |
| `valid_from` | `datetime \| None` | When the content starts to apply; may be later than `timestamp` ("from Oct 1 I live in Seattle"). `None` = unspecified |
| `valid_to` | `datetime \| None` | When it stops applying (exclusive). `None` = open-ended |
| `metadata` | `dict[str, Any]` | Library-managed fields (`replace_log`, `conflicts_with`, `evolution_history`, …) plus user-defined keys |

### Observation time vs. validity

`timestamp` is when the memory was **observed** (written). `[valid_from, valid_to)` is when its **content holds**. They answer different questions and are kept apart:

| | field | used by |
|---|---|---|
| epistemic freshness — "how long since we last observed this?" | `timestamp` | confidence decay (`half_life_days`) |
| temporal validity — "during which period is this true?" | `valid_from` / `valid_to` | temporal resolution, `as_of` queries, REPLACE ordering |

`Memory.effective_from` is the operational fallback: `valid_from` if declared, else `timestamp`. `Memory.is_valid_at(t)` tests the half-open window `[effective_from, valid_to)` — half-open so that `A.valid_to == B.valid_from` yields exactly one valid state at the switch-over instant. A `valid_to` at or before `effective_from` is rejected at construction.

`valid_from` may be in the future relative to `timestamp`. `resolve_temporal()` filters to memories valid at `as_of` (default: now) **before** collapsing single-valued slots to their newest member, so a declared future state never shadows the current one; it becomes the answer once `as_of` passes its `valid_from`. Nothing closes a window automatically — `REPLACE`/`SUPERSEDE` do not set the old memory's `valid_to`. That is a per-type decision reserved for a later resolution-rule contract.

`Memory.type` is plain `str` so profiles can register custom types. The `MemoryType` enum (`MemoryType.FACT == "fact"`, etc.) is kept as a back-compat alias.

## Source — structured provenance

Without provenance, a `claim` is just a sentence. With it, you can cite, deduplicate, and trust-weight.

```python
from typedmem import Source

Source(
    document_id="paper_a.pdf",     # opaque, caller-chosen
    chunk_id="results",            # optional: which section/chunk
    span=(120, 240),               # optional: char offsets
    retrieved_at=...,              # defaults to now (UTC)
    authority=0.95,                # REPLACE guard + REINFORCE weight (see below)
    uri="https://arxiv.org/abs/..." # optional
)
```

`Source.key()` returns `(document_id, chunk_id, span)` — the dedup identity for `REINFORCE`. Two chunks from the same document independently corroborating a memory are kept as distinct evidence.

`Source.from_any(value)` lifts strings into Sources for v0.3 backward compat.

## Workspace — namespace isolation

Every `Memory` has a `workspace: str` (default `"default"`). Conflict resolution is workspace-scoped: a `preference` with subject `"user"` in workspace `"legal"` never collides with the same in workspace `"medical"`.

```python
store = SQLiteMemoryStore("memories.db", default_workspace="legal")
# … all queries default to 'legal'; override per-call with workspace=...
```

CLI:

```bash
typedmem --workspace legal add "..." --type obligation
typedmem workspaces
```

## ConflictPolicy — the intelligence layer

When you `store.add(memory)` and a memory with the same `(workspace, type, subject)` slot already exists, the type's `ConflictPolicy` decides what happens:

| Policy | What it does |
|---|---|
| `REPLACE` | Existing record updated in place (same id). Incoming must be no weaker on every key in the type's `resolve_by` (default `effective_from` + `confidence`) or it downgrades to `IGNORE`. A lower-authority incoming never replaces a higher-authority existing (strongest source on each side is compared; memories with no `sources` make no authority claim) |
| `KEEP_BOTH` | Both stored independently; no link |
| `SUPERSEDE` | Old gets `superseded_by = new.id` and stays in store; new is the active record |
| `REINFORCE` | Single record; sources unioned by `(document_id, chunk_id, span)`; confidence boosted by authority-weighted blend |
| `FLAG` | Both stored; each gets `metadata["conflicts_with"]` pointing at the other |
| `IGNORE` | Incoming discarded; existing untouched. Also auto-applied when REPLACE-target incoming is strictly weaker |

The right policy depends on what the type *means*:

- A user's **preference** changes → `REPLACE`
- A scientific **claim** can have multiple competing answers → `KEEP_BOTH`
- An engineering **decision** evolves but the audit trail matters → `SUPERSEDE`
- **Evidence** for the same outcome from two papers → `REINFORCE`
- A safety **risk** with two contradictory readings → `FLAG`

These defaults live in `DomainProfile.builtin(...)` — see [Profiles](profiles.md).

## How they compose

```
   Memory.add()
      │
      ▼
   (workspace, type, subject) slot lookup
      │
      ├── empty   → store directly
      │
      └── occupied → PolicyEngine.resolve(existing, incoming)
                     │
                     ▼
                  ConflictAction { REPLACE | KEEP_BOTH | SUPERSEDE | REINFORCE | FLAG | IGNORE }
                     │
                     ▼
                  store mutation + metadata updates
```

Same flow whether the memory came from `RuleBasedExtractor`, `LLMExtractor`, or your own code. Same flow whether the backend is `InMemoryStore`, `JSONLMemoryStore`, or `SQLiteMemoryStore`.
