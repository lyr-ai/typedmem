# States

A **state** is a named piece of information that holds one value at a time
and changes over time: `account.plan`, `customer.shipping_country`,
`project.release_channel`. TypedMem keeps its current value, every value it
used to have, and where each value came from.

**The old value isn't false. It is no longer current.**

[▶ See it happen in the Truth Through Time explorer](../explorer/?s=late)

## Facts change

Every block of output on this page is real. A test runs these commands on
every commit and compares the output.

<!-- contract -->
```console
$ typedmem set account.plan Free --valid-from 2026-01-05 --source signup
account.plan = Free  (new)
$ typedmem set account.plan Pro --valid-from 2026-04-01 --source billing
account.plan = Pro  (was Free)
$ typedmem set account.plan Enterprise --valid-from 2026-09-01 --source billing
account.plan = Enterprise  (was Pro)
$ typedmem get account.plan
Enterprise
$ typedmem history account.plan
Enterprise   current    source: billing
Pro          previous   source: billing
Free         previous   source: signup
$ typedmem history account.plan -v
Enterprise   current    since 2026-09-01          source: billing
Pro          previous   2026-04-01 → 2026-09-01   source: billing
Free         previous   2026-01-05 → 2026-04-01   source: signup
$ typedmem get account.plan --at 2026-06-15
Pro
```

`get --at` answers "what was current then?". Nothing is ever deleted.

## Facts arrive late

TypedMem orders values by **when they became true** (`--valid-from`), not
by when they arrived. A record that describes the past goes into the past,
however late it arrives. If it repeats a value that is already known, its
source is added to that value:

<!-- contract -->
```console
$ typedmem set account.plan Free --valid-from 2026-01-05 --source signup
account.plan = Free  (new)
$ typedmem set account.plan Enterprise --valid-from 2026-09-01 --source billing
account.plan = Enterprise  (was Free)
$ typedmem set account.plan Pro --valid-from 2026-04-01 --source "support ticket"
account.plan: recorded Pro from 2026-04-01 as a past value; current is Enterprise
$ typedmem set account.plan Pro --valid-from 2026-04-01 --source "email from the customer"
account.plan: added source to historical value Pro (from 2026-04-01); current is Enterprise
```

A value with no `--valid-from` counts as true **from now**. TypedMem can
only know a record is old if the record says when it was true.

## Sources disagree

When two values can't be put in time order, TypedMem doesn't pick one. That
happens when they start at the same moment, or when the later one comes from
a weaker source (`--authority`, default 1.0). `get` exits with code 3, and
Python's `get` raises `StateConflict`:

<!-- contract -->
```console
$ typedmem set account.plan Enterprise --valid-from 2026-09-01 --source billing
account.plan = Enterprise  (new)
$ typedmem set account.plan Pro --valid-from 2026-09-01 --source crm
account.plan: CONFLICT: Pro disagrees with Enterprise; no current value
  see: typedmem history account.plan
$ typedmem get account.plan
account.plan: CONFLICT, no current value
Pro          conflict   source: crm       vs Enterprise
Enterprise   conflict   source: billing   vs Pro
$ typedmem set account.plan Enterprise --valid-from 2026-09-10 --source "billing invoice"
account.plan = Enterprise  (resolves conflict: Enterprise vs Pro)
```

A later value from a source at least as trusted settles the conflict.
Authority alone never does: two claims about the same moment stay in
conflict whatever their authority.

## In Python

<!-- contract -->
```python
from datetime import datetime
from typedmem import AgentMemory, StateConflict

mem = AgentMemory(path="agent.db")
mem.set("account.plan", "Free", valid_from=datetime(2026, 1, 5), source="signup")
mem.set("account.plan", "Enterprise", valid_from=datetime(2026, 9, 1), source="billing")
mem.set("account.plan", "Pro", valid_from=datetime(2026, 4, 1), source="support ticket").outcome        # 'past'
mem.get("account.plan")                                                                                # 'Enterprise'
[e.value for e in mem.history("account.plan")]                                                         # ['Enterprise', 'Pro', 'Free']
mem.get("account.plan", as_of=datetime(2026, 6, 15))                                                   # 'Pro'
```

`mem.history(key)` returns `StateEntry` objects (`value`, `status`,
`valid_from`, `valid_to`, `sources`, `conflicts_with`). They print as the
same table as the CLI.

## The rules

| When a value arrives… | TypedMem | Outcome |
|---|---|---|
| nothing set yet | stores it | `new` |
| same value as the one in effect then | adds its source | `unchanged` |
| different, starts later, source not weaker | it becomes current; the old one becomes history | `changed` |
| different, starts earlier | stores it in history at its place in time | `past` |
| different, starts at the same moment, or later but from a weaker source | keeps both, and `get` refuses to pick | `conflict` |
| starts in the future | keeps it, until its time | `scheduled` |

The full rules, including the invariant for what counts as a conflict, are
in [design note 0002](https://github.com/lyr-ai/typedmem/blob/main/design/0002-changing-facts.md).

## Limits

- You name the key. TypedMem doesn't extract states from free text.
- One value per key. For things that hold several values at once, use
  ordinary memories.
- States order values by validity time and source authority only. They
  deliberately don't apply confidence or per-type rules ("ignore a less
  confident write", "always replace"). Use typed memories when those
  should decide.
- States are available in Python and the CLI. The HTTP server and the
  TypeScript client don't expose them yet.
