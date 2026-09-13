"""First-class memory event log (v0.6a).

A ``MemoryEvent`` records one change to one memory: who made it, when, why,
and what changed. Every successful add/update/delete/conflict-resolution
emits one, so the event stream is the canonical change feed — not a partial
audit trail of only contested writes.

Sources distinguish *where* a change originated:

- ``store`` — automatic lifecycle from MemoryStore.add/update/delete
- ``evolver`` — ContradictionSurfacer / GoalResolver / SummaryEvolver / drift
- ``agent`` — caller explicitly tags an agent write
  (e.g. AgentMemory.remember passes ``event_source="agent"``)
- ``user`` — caller explicitly tags a human action
- ``system`` — migration, import, maintenance

``source_name`` carries the specific producer ("drift_detector",
"AgentMemory.remember", "migrate_evolution_history") so debugging doesn't
have to guess.

v0.9 makes the log **replayable**. Every state-changing event carries full
``before`` / ``after`` snapshots of the memory in ``payload``::

    {"snapshot_version": 1, "version": <int>, "before": <dict|None>, "after": <dict|None>}

Snapshots are ``Memory.to_dict()`` values (plain JSON data, never object
references) taken at the instant of the change, so an event is self-contained:
``after`` *is* the memory's state once the event has happened, and
``after=None`` means it no longer exists. Replaying a log therefore applies
outcomes — it never re-runs a policy. Events written before v0.9 have no
snapshots (``has_snapshot`` is False) and can be read but not replayed.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    from .schema import Memory

EventSource = Literal["store", "evolver", "agent", "user", "system"]

# Bumped only when the shape of a snapshot (``Memory.to_dict()``) changes in a
# way a replayer must know about. Purely a marker; no migration machinery.
SNAPSHOT_VERSION = 1


def snapshot(m: "Memory | None") -> dict[str, Any] | None:
    """Canonical event snapshot of a memory: ``Memory.to_dict()`` minus the
    underscore-prefixed metadata keys stores use as caches (``_embedding``,
    ``_embedder_id``). ``to_dict`` copies every nested container, so the
    result is an immutable-by-construction value that later mutation of ``m``
    cannot touch. Same function for every store backend."""
    if m is None:
        return None
    d = m.to_dict()
    d["metadata"] = {k: v for k, v in d["metadata"].items() if not k.startswith("_")}
    return d

EVENT_SOURCES: frozenset[str] = frozenset(
    {"store", "evolver", "agent", "user", "system"}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryEvent:
    memory_id: str
    workspace: str
    action: str
    source: EventSource
    type: str | None = None
    subject: str | None = None
    source_name: str | None = None
    reason: str = ""
    input_ids: list[str] = field(default_factory=list)
    output_ids: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.source not in EVENT_SOURCES:
            raise ValueError(
                f"MemoryEvent.source must be one of {sorted(EVENT_SOURCES)}, "
                f"got {self.source!r}"
            )

    # ── snapshot accessors (v0.9) ──────────────────────────────────────
    @property
    def has_snapshot(self) -> bool:
        """True if this event carries before/after state and can be replayed."""
        return "snapshot_version" in self.payload

    @property
    def before(self) -> dict[str, Any] | None:
        """Memory state before the change (``None`` for a creation, or for a
        legacy event without snapshots)."""
        return self.payload.get("before")

    @property
    def after(self) -> dict[str, Any] | None:
        """Memory state after the change (``None`` for a deletion, or for a
        legacy event without snapshots)."""
        return self.payload.get("after")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryEvent":
        data = dict(d)
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def to_legacy_history_dict(self) -> dict[str, Any]:
        """Adapter for ``evolution_history(memory_id)`` callers that expect
        the pre-v0.6 dict shape: ``{evolver, action, input_ids, output_ids,
        reason, timestamp}``. ``source_name`` falls back to ``source`` when
        unset so legacy entries still have a non-empty ``evolver`` field."""
        return {
            "evolver": self.source_name or self.source,
            "action": self.action,
            "input_ids": list(self.input_ids),
            "output_ids": list(self.output_ids),
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }
