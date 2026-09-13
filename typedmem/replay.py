"""Replay: rebuild memory state from the event log.

``replay`` applies event *outcomes*, in order. It never consults a
``PolicyEngine``, ``ConflictPolicy``, or resolver — replay is "restore what
was decided", not "decide again". That is what makes the log a stable record:
changing a policy tomorrow must not change what yesterday's log replays to.

Each replayable event is self-contained (see ``events.snapshot``): ``after`` is
the full state of the memory once the event has happened, ``after=None`` means
it was deleted. Legacy events (pre-v0.9, no snapshots) cannot be applied; in
strict mode they raise ``ReplayError``, otherwise they are skipped and the
result is best-effort.

Out of scope here: compaction / checkpoints, restoring *into* a store, and any
snapshot-schema migration beyond checking ``snapshot_version``.
"""

from __future__ import annotations

from collections.abc import Iterable

from .events import SNAPSHOT_VERSION, MemoryEvent
from .schema import Memory


class ReplayError(RuntimeError):
    """An event in the stream cannot be applied (no snapshot, or a snapshot
    version this build does not understand)."""


def replay(events: Iterable[MemoryEvent], *, strict: bool = True) -> dict[str, Memory]:
    """Fold an ordered event stream into ``{memory_id: Memory}``.

    ``events`` must already be in application order (``store.timeline()`` and
    ``store.history()`` return them that way). Deleted memories are absent
    from the result.
    """
    state: dict[str, Memory] = {}
    for e in events:
        if not e.has_snapshot:
            if strict:
                raise ReplayError(
                    f"event {e.id!r} ({e.action!r} on {e.memory_id!r}) carries no "
                    "snapshot; it predates replayable logging. Pass strict=False "
                    "to skip such events."
                )
            continue
        sv = e.payload.get("snapshot_version")
        if sv != SNAPSHOT_VERSION:
            raise ReplayError(
                f"event {e.id!r} has snapshot_version {sv!r}; this build "
                f"understands {SNAPSHOT_VERSION}"
            )
        after = e.after
        if after is None:
            state.pop(e.memory_id, None)
        else:
            state[e.memory_id] = Memory.from_dict(after)
    return state
