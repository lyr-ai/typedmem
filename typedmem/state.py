"""States: named, single-valued facts that change over time (design 0002).

A state is a key such as ``alice.employer`` that holds one value at a time.
Each value is an ordinary ``Memory`` of type ``state`` (``subject`` = key,
``content`` = value), so states use the store, kernel, event log and replay
like everything else.

Which value is current is a **pure function** of the key's stored values
(``resolve``), decided by validity time rather than arrival order:

- A value that starts later *supersedes* the one before it, unless its source
  is weaker. Then the two are in *conflict*.
- Two different values that start at the same instant are in conflict.
- A conflict has no current value. It stays open until a later value from a
  source at least as strong as every contender settles it.

``superseded_by`` and ``metadata["conflicts_with"]`` on the stored records are
an index of this function, rewritten on every write. They are never a second
source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import groupby

from .schema import Memory
from .source import Source

STATE_TYPE = "state"

# Reasons ``SetResult.outcome`` can take.
OUTCOMES = ("new", "unchanged", "changed", "past", "conflict", "scheduled")


def normalize_key(key: str) -> str:
    """Keys are trimmed and case-insensitive: ``Alice.Employer`` is ``alice.employer``."""
    k = key.strip().lower() if isinstance(key, str) else ""
    if not k:
        raise ValueError(f"state key must be a non-empty string, got {key!r}")
    return k


def normalize_value(value: str) -> str:
    v = value.strip() if isinstance(value, str) else ""
    if not v:
        raise ValueError(f"state value must be a non-empty string, got {value!r}")
    return v


def authority(m: Memory) -> float:
    """A value's authority: its strongest source. A value set without a source
    carries the default authority, 1.0, the same as ``Source``'s default."""
    return max((s.authority for s in m.sources), default=1.0)


def utc(t: datetime | None) -> datetime | None:
    """Naive datetimes are taken as UTC so they compare with stored ones."""
    if t is None or t.tzinfo is not None:
        return t
    return t.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class StateEntry:
    """One value in a state's history.

    ``status``:

    - ``current``: the value in effect now;
    - ``previous``: replaced by a later value, or ended;
    - ``conflict``: contending for the current value with another value;
    - ``scheduled``: starts in the future.

    ``valid_to`` is the declared end, or the start of the value that replaced it.
    """

    key: str
    value: str
    status: str
    valid_from: datetime
    valid_to: datetime | None
    sources: tuple[Source, ...]
    observed_at: datetime
    memory_id: str
    authority: float
    conflicts_with: tuple[str, ...] = ()       # values this one contends with

    def to_dict(self) -> dict:
        return {
            "key": self.key, "value": self.value, "status": self.status,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "sources": [s.to_dict() for s in self.sources],
            "observed_at": self.observed_at.isoformat(),
            "memory_id": self.memory_id, "authority": self.authority,
            "conflicts_with": list(self.conflicts_with),
        }


class StateConflict(Exception):
    """Raised by ``get`` when the state's current value cannot be established:
    two or more values contend and none is entitled to win. ``entries`` holds
    every contender, with provenance."""

    def __init__(self, key: str, entries: list[StateEntry]) -> None:
        self.key = key
        self.entries = entries
        values = " vs ".join(repr(e.value) for e in entries)
        super().__init__(f"{key} is in conflict: {values}; no current value")


@dataclass(frozen=True)
class SetResult:
    """What a ``set`` did. ``outcome`` is one of ``OUTCOMES``. ``previous`` is
    the current value before the write (``None`` if there was none, or if it
    was in conflict). ``current`` is the current value after it (``None`` if
    none or in conflict). ``conflicts`` lists the contenders when the state is
    in conflict after the write."""

    key: str
    value: str
    outcome: str
    entry: StateEntry
    previous: str | None
    current: str | None
    conflicts: tuple[StateEntry, ...] = ()
    resolved_conflict: tuple[str, ...] = ()   # values of the conflict this write settled
    source_added: bool = False                # an unchanged write that added a new source


@dataclass
class Resolution:
    """The result of ``resolve``: the contenders in effect at ``as_of`` and the
    index links (successor, conflict partners) for every stored value."""

    as_of: datetime
    records: list[Memory]
    live: list[Memory]
    successor: dict[str, str] = field(default_factory=dict)
    ended_by: dict[str, list[str]] = field(default_factory=dict)   # the epoch that ended it
    conflicts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def values(self) -> list[str]:
        return sorted({m.content for m in self.live})

    @property
    def settled(self) -> bool:
        return len(self.values) == 1

    @property
    def current(self) -> Memory | None:
        """The value in effect, or ``None`` when nothing is set or it's in conflict."""
        if not self.settled:
            return None
        return max(self.live, key=_order)


def _order(m: Memory) -> tuple:
    return (m.effective_from, m.timestamp, m.id)


def _expired(m: Memory, t: datetime) -> bool:
    return m.valid_to is not None and m.valid_to <= t


def resolve(records: list[Memory], as_of: datetime) -> Resolution:
    """Replay the key's values in validity order up to ``as_of``.

    Values that start at the same instant form one *epoch*. The epoch's
    strength is the authority of its strongest value. An epoch **ends** every
    value in effect before it whose authority is at most that strength; values
    that are stronger survive. The epoch's own values and the survivors are
    then the values in effect: one value means settled, several mean conflict.

    Invariant (design 0002, section 4): a conflict set contains only values
    that remain simultaneously plausible at the queried time. A value that
    later claims of at least its authority agree has ended is history, even
    when those claims disagree about what came next.
    """
    records = sorted(records, key=_order)
    res = Resolution(as_of=as_of, records=records, live=[])
    live: list[Memory] = []
    started = [m for m in records if m.effective_from <= as_of]
    for start, group in groupby(started, key=lambda m: m.effective_from):
        group = list(group)
        live = [m for m in live if not _expired(m, start)]
        values = {m.content for m in group}
        strength = max(authority(m) for m in group)
        survivors = [p for p in live
                     if p.content not in values and authority(p) > strength]
        for p in live:
            if p in survivors:
                continue
            same = [g for g in group if g.content == p.content]
            res.successor[p.id] = max(same or group, key=_order).id
            res.ended_by[p.id] = [g.id for g in group]
        live = survivors + group
    res.live = [m for m in live if not _expired(m, as_of)]
    if not res.settled:
        for m in res.live:
            res.conflicts[m.id] = [o.id for o in res.live if o.content != m.content]
    return res


def entries(key: str, res: Resolution) -> list[StateEntry]:
    """Every value the key has held, newest first, with status and provenance."""
    by_id = {m.id: m for m in res.records}
    live_ids = {m.id for m in res.live}
    out = []
    for m in sorted(res.records, key=_order, reverse=True):
        succ = by_id.get(res.successor.get(m.id, ""))
        if m.effective_from > res.as_of:
            status = "scheduled"
        elif m.id in live_ids:
            status = "current" if res.settled else "conflict"
        else:
            status = "previous"
        valid_to = m.valid_to
        if succ is not None and (valid_to is None or succ.effective_from < valid_to):
            valid_to = succ.effective_from
        out.append(StateEntry(
            key=key, value=m.content, status=status,
            valid_from=m.effective_from, valid_to=valid_to,
            sources=tuple(m.sources), observed_at=m.timestamp, memory_id=m.id,
            authority=authority(m),
            conflicts_with=tuple(sorted({by_id[i].content for i in res.conflicts.get(m.id, [])})),
        ))
    return out


def _day(t: datetime) -> str:
    return t.date().isoformat()


def _provenance(e: StateEntry) -> str:
    if not e.sources:
        return ""
    ids = ", ".join(dict.fromkeys(s.document_id for s in e.sources))
    auth = f" (authority {e.authority:g})" if e.authority != 1.0 else ""
    return f"source: {ids}{auth}"


def format_entries(es: list[StateEntry], *, dates: bool = False) -> str:
    """The history table the CLI prints and ``StateHistory`` shows in a REPL:
    value, status and source, newest first. ``dates=True`` adds each value's
    validity window (``history -v``)."""
    if not es:
        return "(no history)"
    rows = []
    for e in es:
        if not dates:
            window = ""
        elif e.status == "previous":
            window = f"{_day(e.valid_from)} → {_day(e.valid_to) if e.valid_to else '?'}"
        elif e.status == "scheduled":
            window = f"from {_day(e.valid_from)}"
        else:
            window = f"since {_day(e.valid_from)}"
        note = f"vs {', '.join(e.conflicts_with)}" if e.conflicts_with else ""
        rows.append((e.value, e.status, window, _provenance(e), note))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    return "\n".join(
        "   ".join(c.ljust(w) for c, w in zip(r, widths) if w).rstrip() for r in rows)


class StateHistory(list):
    """``AgentMemory.history``'s return value: a plain list of ``StateEntry``
    (newest first) that prints as the history table."""

    def table(self, *, dates: bool = False) -> str:
        return format_entries(self, dates=dates)

    def __repr__(self) -> str:
        return format_entries(self)

    __str__ = __repr__
