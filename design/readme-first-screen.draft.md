<!-- DRAFT, not published. Depends on design/0002-changing-facts.md.
     The transcript below is the target output of the not-yet-built `set`
     API. Once built, it is copied from the README contract test. -->

# TypedMem

**Agent memory stores facts. Facts change. Which one is true now?**

TypedMem keeps the current truth without erasing what used to be true, or
where it came from.

```bash
$ pip install typedmem                  # Python 3.10+, no dependencies

$ typedmem set alice.employer OpenAI
alice.employer = OpenAI                 (new)

$ typedmem set alice.employer Anthropic
alice.employer = Anthropic              (was OpenAI)

$ typedmem get alice.employer
Anthropic

$ typedmem history alice.employer
current   Anthropic   since 2026-09-27   from you (cli)
previous  OpenAI      until 2026-09-27   from you (cli)
```

**What breaks without it:** most agent memory stores both sentences and
retrieves both. Your agent sees "OpenAI" and "Anthropic" with equal weight and
guesses. When two sources genuinely disagree, TypedMem doesn't guess either.
It keeps both and flags the conflict.

Same thing in Python:

```python
from typedmem import AgentMemory

mem = AgentMemory(path="agent.db")
mem.set("alice.employer", "OpenAI")
mem.set("alice.employer", "Anthropic", source="email from Alice")
mem.get("alice.employer")        # 'Anthropic'
```

[Truth Through Time: see it happen →](#) · [How it decides](#) · [Docs](#)

---

<!-- Below the fold: the existing README from "Before vs After" onward
     (contracts, profiles, storage, retrieval, timeline, kernel, CLI),
     unchanged except for links. Footer adds:
     "Also from lyr-ai: AgentSeism — regression decisions for stochastic AI systems." -->
