"""Feature 4 — Temporal resolution.

The first TypedMem-specific reasoning step: drop memories that are no longer
(or not yet) valid. Three rules, all simple by design:

1. ``remove_superseded`` — drop any memory with an explicit ``superseded_by``
   link (the store sets this under the SUPERSEDE policy).
2. **validity window** — keep only memories whose ``[effective_from, valid_to)``
   window contains the reference time (``as_of``, or *now*). This removes both
   expired memories (``valid_to`` in the past) and future-valid ones
   (``valid_from`` not yet reached), so a declared future state never shadows
   the current one.
3. ``latest_per_slot`` — for *single-valued* types (preference, goal, decision,
   …), collapse the same ``(workspace, type, subject)`` slot to the member with
   the newest ``effective_from``. Multi-valued types (facts, events) pass
   through untouched, so we never drop legitimately-distinct facts.

Order matters: validity filtering runs **before** latest-per-slot, so "newest"
is always judged among memories that actually apply at the reference time.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..schema import Memory, _now


def remove_superseded(memories: Iterable[Memory]) -> list[Memory]:
    """Drop memories that have been explicitly superseded."""
    return [m for m in memories if m.superseded_by is None]


def filter_valid(
    memories: Iterable[Memory],
    *,
    as_of: datetime | None = None,
    include_expired: bool = False,
) -> list[Memory]:
    """Keep memories valid at ``as_of`` (default: now).

    ``include_expired=True`` ignores the ``valid_to`` bound — useful for
    "what did we believe over time" views — but a memory whose
    ``effective_from`` is still in the future is never surfaced."""
    ref = as_of or _now()
    if include_expired:
        return [m for m in memories if m.effective_from <= ref]
    return [m for m in memories if m.is_valid_at(ref)]


def latest_per_slot(
    memories: Iterable[Memory],
    *,
    types: set[str] | None = None,
    as_of: datetime | None = None,
) -> list[Memory]:
    """Collapse same-slot memories to the one with the newest ``effective_from``,
    but only for ``types`` (single-valued). Memories of other types — or with no
    subject — pass through unchanged. Order of pass-through memories is
    preserved; collapsed winners are appended.

    When ``as_of`` is given, only memories valid at that instant may win a
    slot; the rest of the collapsed types are dropped. This keeps the
    invariant "filter validity first, then pick newest" local to this
    function even when it is called on its own."""
    memories = list(memories)
    if not types:
        return memories
    collapse = set(types)
    best: dict[tuple[str, str, str | None], Memory] = {}
    passthrough: list[Memory] = []
    for m in memories:
        if m.type not in collapse or m.subject is None:
            passthrough.append(m)
            continue
        if as_of is not None and not m.is_valid_at(as_of):
            continue
        key = (m.workspace, m.type, m.subject)
        cur = best.get(key)
        if cur is None or m.effective_from > cur.effective_from:
            best[key] = m
    return passthrough + list(best.values())


def resolve_temporal(
    memories: Iterable[Memory],
    *,
    as_of: datetime | None = None,
    collapse_types: set[str] | None = None,
    include_expired: bool = False,
) -> list[Memory]:
    """Full temporal pass: remove superseded, keep memories valid at ``as_of``
    (default now), then collapse single-valued slots to their latest surviving
    member."""
    ref = as_of or _now()
    out = remove_superseded(memories)
    out = filter_valid(out, as_of=ref, include_expired=include_expired)
    return latest_per_slot(out, types=collapse_types, as_of=None if include_expired else ref)
