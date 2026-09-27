# CLI

After installing TypedMem, the `typedmem` shell command is on your PATH.

```bash
typedmem --help
```

## Global options

| Flag | Default | Notes |
|---|---|---|
| `--store PATH` | `~/.typedmem/memories.db` | `.db` → SQLite, `.jsonl` → JSONL. Override via `$TYPEDMEM_DB` |
| `--workspace NAME` | `default` | Memory namespace; isolates one agent/domain from another |
| `--profile NAME` | _(none)_ | Built-in domain profile to bind: validates types and required fields, applies per-type policies |
| `--profile-file PATH` | _(none)_ | Path to a custom profile in `.json` or `.yaml` |

## Subcommands

### `set`

Set a **state**: a named value that changes over time. Nothing is
overwritten. See [States](states.md).

```bash
typedmem set account.plan Enterprise --valid-from 2026-09-01 --source billing
```

Options: `--source` (where the value came from; default `cli`), `--uri`,
`--authority` (trust in the source, default 1.0; a later but weaker value
opens a conflict), `--valid-from` (when the value became true; default now),
`--valid-to` (exclusive). The output says what happened: `(new)`,
`(was X)`, a past value recorded, a source added to a historical value,
`(unchanged)`, a conflict, or scheduled.

### `get`

Print the current value of a state.

```bash
typedmem get account.plan
typedmem get account.plan --at 2026-06-15      # the value in effect then
```

Exit codes: `0` value printed · `1` not set · `3` conflict (the competing
values and their sources are printed to stderr).

### `add`

Add a memory (or extract from text via `RuleBasedExtractor` if no `--type`).

```bash
typedmem add "I prefer concise answers"
typedmem --profile engineering_design add "Use SQLite for storage" \
  --type decision --subject storage_backend \
  --document-id design_v1.md --authority 0.95
```

Options: `--type`, `--subject`, `--tags`, `--confidence`, `--document-id`, `--uri`, `--authority`, `--valid-from`, `--valid-to` (ISO-8601; naive values are taken as UTC; `--valid-to` is exclusive; both require `--type`).

### `search`

Semantic search across stored memories. Uses `HashingEmbeddingProvider` by default; `--no-embed` falls back to token overlap.

```bash
typedmem search "blood pressure reduction" --type evidence --limit 5
typedmem search "ship" --include-superseded
```

Options: `--limit`, `--type` (repeatable), `--tag` (repeatable), `--include-superseded`, `--no-embed`, `--dim`.

### `list`

List stored memories, newest first.

```bash
typedmem list --type observation
typedmem --workspace medical list --json
```

### `delete`

Delete by id.

```bash
typedmem delete MEMORY_ID
```

### `compact`

Compact a JSONL store (rewrite as one record per live memory).

```bash
typedmem --store memories.jsonl compact
```

### `workspaces`

List workspaces present in the store.

```bash
typedmem workspaces
```

### `profiles`

List built-in domain profiles and their types.

```bash
typedmem profiles
```

### `evolve`

Run an Evolver over the store.

```bash
typedmem evolve --evolver contradictions
typedmem evolve --evolver drift --apply
typedmem evolve --evolver goals --threshold 0.9            # dry-run
typedmem evolve --evolver goals --threshold 0.9 --apply    # commit
```

| Flag | Notes |
|---|---|
| `--evolver` | One of `contradictions`, `drift`, `goals` |
| `--apply` | Required to mutate. `drift` and `goals` default to dry-run for safety |
| `--threshold` | `goals` only — minimum cosine similarity to resolve (default `0.85`) |
| `--min-replaces` | `drift` only — REPLACE count threshold (default `3`) |
| `--window-days` | `drift` only — trailing window for replace counting (default `30`) |
| `--dim` | Hashing embedder dimension (`goals` only) |

`SummaryEvolver` is intentionally not exposed via CLI — it needs an LLM client; use the Python API.

### `history`

For a **state key**, list every value it has held, newest first, with status
(`current`, `previous`, `conflict`, `scheduled`) and source. `-v` adds each
value's validity window.

```bash
typedmem history account.plan
typedmem history account.plan -v
```

For a **memory id**, show that memory's event timeline from the event log,
with the source of each event (`user`, `agent`, `evolver`, `system`).
`--json` prints the events as JSON.

```bash
typedmem history MEMORY_ID [--json]
```

## Conventions

- Read-only commands never need `--apply`.
- Evolver mutations always require explicit opt-in.
- Output is plain text by default; `list --json` emits structured JSON.

## Example: a typical agent session

```bash
# Capture the design discussion
typedmem --profile engineering_design --workspace project_x add \
  "Use SQLite for storage" --type decision --subject storage_backend \
  --document-id design_v1.md

typedmem --profile engineering_design --workspace project_x add \
  "Switch to PostgreSQL" --type decision --subject storage_backend \
  --document-id design_v2.md

# Look at the active decision and the audit trail
typedmem --workspace project_x list --type decision
typedmem --workspace project_x list --type decision --include-superseded

# Surface any flagged risks
typedmem --workspace project_x evolve --evolver contradictions
```
