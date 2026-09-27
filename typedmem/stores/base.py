"""Abstract MemoryStore: concrete API on top of a few storage primitives.

v0.6a adds a first-class memory event log. Every successful add/update/delete
emits a typed ``MemoryEvent``; subclasses implement two extra primitives
(``_append_event``, ``_iter_events``) on top of the four they already had.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Iterator

from ..events import EVENT_SOURCES, SNAPSHOT_VERSION, EventSource, MemoryEvent
from ..kernel import (
    ConfidenceStrategy,
    DefaultLifecycleStrategy,
    IdentityStrategy,
    LifecycleStrategy,
    PolicyConfidenceStrategy,
    SlotIdentityStrategy,
    Transition,
    TransitionEngine,
)
from ..policy import ConflictAction, ConflictPolicy, PolicyEngine
from ..schema import Memory, MemoryType
from ..source import Source
from ..state import (
    STATE_TYPE,
    Resolution,
    SetResult,
    StateConflict,
    StateEntry,
    entries,
    normalize_key,
    normalize_value,
    resolve,
    utc,
)

if False:  # TYPE_CHECKING only; avoid hard import cycle
    from ..profiles.base import DomainProfile


def _record_lifecycle_event(
    store: "MemoryStore",
    m: Memory,
    *,
    action: str,
    input_ids: list[str],
    output_ids: list[str],
    reason: str,
    source: EventSource = "store",
    source_name: str | None = None,
    before: dict | None,
    after: dict | None,
) -> None:
    """Emit a MemoryEvent for a lifecycle change. Replaces the v0.4.2
    ``metadata["evolution_history"]`` write — the event log is now indexed
    storage with no 50-entry cap, and ``evolution_history(memory_id)`` reads
    back through this same log.

    ``before`` / ``after`` are ``events.snapshot()`` values taken by the caller
    at the right instants (the engine owns the mutation, so it owns the
    snapshot timing). They are required so no state change can be logged
    without being replayable."""
    event = MemoryEvent(
        memory_id=m.id,
        workspace=m.workspace,
        type=m.type,
        subject=m.subject,
        action=action,
        source=source,
        source_name=source_name,
        reason=reason,
        input_ids=list(input_ids),
        output_ids=list(output_ids),
        # ``version`` is the resulting version (RFC-0001 invariant); the
        # snapshots make the event self-contained for ``replay``.
        payload={
            "version": m.version,
            "snapshot_version": SNAPSHOT_VERSION,
            "before": before,
            "after": after,
        },
    )
    store._append_event(event)


class MemoryStore(ABC):
    """Subclasses implement six primitives below; everything else is derived.
    Backends may override derived methods when SQL can answer faster.
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        *,
        default_workspace: str = "default",
        profile: "DomainProfile | None" = None,
        identity: IdentityStrategy | None = None,
        confidence: ConfidenceStrategy | None = None,
        lifecycle: LifecycleStrategy | None = None,
    ) -> None:
        self.policy = policy or PolicyEngine()
        self.default_workspace = default_workspace
        self.profile = profile
        # RFC-0001 kernel: replaceable policies with behavior-preserving
        # defaults, plus the single mutation funnel. Public add/delete, conflict
        # resolution, and every mutating evolver route through ``self.transitions``.
        self.identity = identity or SlotIdentityStrategy()
        self.confidence = confidence or PolicyConfidenceStrategy(self.policy)
        self.lifecycle = lifecycle or DefaultLifecycleStrategy()
        self.transitions = TransitionEngine(self)
        # Lazily-migrated memory ids — keys whose legacy
        # ``metadata["evolution_history"]`` has been folded into the event
        # log. We only migrate once per memory per process.
        self._migrated_ids: set[str] = set()

    # ── Primitives ────────────────────────────────────────────────────────
    # ``_put`` / ``_delete`` are ENGINE-INTERNAL storage primitives. They perform
    # no validation, versioning, conflict resolution, or event emission. The only
    # sanctioned callers are the TransitionEngine and the store's own
    # ``_migrate_legacy_history`` maintenance path. Application code and plugins
    # (evolvers) must go through ``add`` / ``delete`` / ``apply_transition`` — a
    # direct ``_put`` bypasses the audit trail and the version invariant.
    @abstractmethod
    def _put(self, m: Memory) -> None: ...

    @abstractmethod
    def _get(self, memory_id: str) -> Memory | None: ...

    @abstractmethod
    def _delete(self, memory_id: str) -> bool: ...

    @abstractmethod
    def _iter(self) -> Iterator[Memory]: ...

    @abstractmethod
    def _append_event(self, event: MemoryEvent) -> None: ...

    @abstractmethod
    def _iter_events(self) -> Iterator[MemoryEvent]: ...

    # ── Public API ────────────────────────────────────────────────────────
    def add(
        self,
        m: Memory,
        *,
        event_source: EventSource = "store",
        event_source_name: str | None = None,
    ) -> Memory:
        """Insert a memory, honoring the type's ConflictPolicy on slot collision.

        Slot key is (workspace, type, subject); subject-less memories never
        collide and are inserted directly. If a profile is bound, the memory
        is validated first (raises on failure — strict).

        ``event_source``/``event_source_name`` tag the resulting MemoryEvent
        so consumers can tell "agent wrote this" from "evolver promoted this"
        from "migration imported this". Defaults are ``"store"`` / ``None``,
        which preserves all v0.5 call sites.
        """
        if event_source not in EVENT_SOURCES:
            raise ValueError(
                f"event_source must be one of {sorted(EVENT_SOURCES)}, "
                f"got {event_source!r}"
            )
        if m.type == STATE_TYPE:
            raise ValueError(
                "'state' memories are written with set_state() (AgentMemory.set, "
                "`typedmem set`), which keeps their current value and history correct"
            )
        if self.profile is not None:
            errors = self.profile.validate(m)
            if errors:
                raise ValueError(
                    f"profile {self.profile.name!r} rejected memory: {errors}"
                )
        return self.transitions.apply(
            Transition(
                action="add", memory=m,
                actor=event_source, actor_name=event_source_name,
            )
        )

    def add_many(
        self,
        ms: Iterable[Memory],
        *,
        event_source: EventSource = "store",
        event_source_name: str | None = None,
    ) -> list[Memory]:
        return [
            self.add(m, event_source=event_source, event_source_name=event_source_name)
            for m in ms
        ]

    def get(self, memory_id: str) -> Memory | None:
        return self._get(memory_id)

    def is_active(self, m: Memory) -> bool:
        """Whether a memory is currently active, per the store's
        ``LifecycleStrategy`` (default: not superseded, and — for goals —
        status is ACTIVE)."""
        return self.lifecycle.is_active(m)

    def delete(
        self,
        memory_id: str,
        *,
        event_source: EventSource = "store",
        event_source_name: str | None = None,
    ) -> bool:
        """Delete a memory. Emits a ``deleted`` MemoryEvent BEFORE the row is
        removed, so the event survives in the log and ``changed_since()``
        surfaces deletions to consumers staying in sync."""
        if event_source not in EVENT_SOURCES:
            raise ValueError(
                f"event_source must be one of {sorted(EVENT_SOURCES)}, "
                f"got {event_source!r}"
            )
        return self.transitions.apply(
            Transition(
                action="delete", memory_id=memory_id,
                actor=event_source, actor_name=event_source_name,
            )
        )

    def apply_transition(self, t: Transition):
        """Apply a kernel ``Transition`` directly. This is the low-level funnel
        the public ``add``/``delete`` build on; plugins (evolvers) should route
        their mutations through here rather than calling ``_put`` directly."""
        return self.transitions.apply(t)

    def all(self, *, workspace: str | None = None, include_superseded: bool = False) -> list[Memory]:
        """Memories in ``workspace``. Unless ``include_superseded``, only those in
        effect **now**: ordinary memories that aren't superseded, and for each
        state the values ``get``/``history`` treat as in effect now (the current
        value, or every value in a conflict). See ``_in_effect_now``."""
        ws = workspace if workspace is not None else self.default_workspace
        if include_superseded:
            return [m for m in self._iter() if m.workspace == ws]
        return self._in_effect_now([m for m in self._iter() if m.workspace == ws], ws)

    def by_type(self, t: MemoryType, *, workspace: str | None = None,
                include_superseded: bool = False) -> list[Memory]:
        ws = workspace if workspace is not None else self.default_workspace
        t = t.value if isinstance(t, MemoryType) else t
        return [m for m in self.all(workspace=ws, include_superseded=include_superseded) if m.type == t]

    def _in_effect_now(self, memories: list[Memory], ws: str) -> list[Memory]:
        """Filter to what is in effect now. States are resolved as of now with the
        same ``resolve`` as get/history, not read from the ``superseded_by``
        index, which is written at ``set`` time and goes stale once a
        scheduled value takes effect (#7)."""
        out = [m for m in memories if m.type != STATE_TYPE and m.superseded_by is None]
        keys = sorted({m.subject for m in memories if m.type == STATE_TYPE})
        if keys:
            now = datetime.now(timezone.utc)
            for key in keys:
                out += resolve(self._state_records(key, ws), now).live
        return out

    def workspaces(self) -> list[str]:
        return sorted({m.workspace for m in self._iter()})

    # ── Timeline (v0.6a) ─────────────────────────────────────────────────
    def history(self, memory_id: str) -> list[MemoryEvent]:
        """Every event that touched this memory, oldest first. Includes the
        ``deleted`` event even after the memory row is gone."""
        self._migrate_legacy_history(memory_id)
        events = [e for e in self._iter_events() if e.memory_id == memory_id]
        events.sort(key=lambda e: e.timestamp)
        return events

    def timeline(
        self,
        *,
        subject: str | None = None,
        type: str | None = None,
        workspace: str | None = None,
        source: EventSource | None = None,
    ) -> list[MemoryEvent]:
        """Filtered event stream, oldest first. All filters are AND-combined;
        omitted filters match anything. Workspace defaults to None (all
        workspaces) so callers can audit globally."""
        type_str = type.value if isinstance(type, MemoryType) else type
        if source is not None and source not in EVENT_SOURCES:
            raise ValueError(
                f"source must be one of {sorted(EVENT_SOURCES)}, got {source!r}"
            )
        self._migrate_legacy_history_all()
        out: list[MemoryEvent] = []
        for e in self._iter_events():
            if subject is not None and e.subject != subject:
                continue
            if type_str is not None and e.type != type_str:
                continue
            if workspace is not None and e.workspace != workspace:
                continue
            if source is not None and e.source != source:
                continue
            out.append(e)
        out.sort(key=lambda e: e.timestamp)
        return out

    def replay(self, *, strict: bool = True) -> dict[str, Memory]:
        """Rebuild ``{memory_id: Memory}`` purely from this store's event log,
        applying recorded outcomes in order — no policy is consulted. With a
        fully replayable log the result equals the live state; see
        ``typedmem.replay.replay`` for ``strict`` semantics on legacy events."""
        from ..replay import replay as _replay
        return _replay(self.timeline(), strict=strict)

    def changed_since(self, timestamp: datetime) -> list[MemoryEvent]:
        """All events strictly after ``timestamp``, oldest first. The canonical
        change feed for consumers staying in sync — includes adds, updates,
        deletes, and evolver-driven transforms."""
        self._migrate_legacy_history_all()
        out = [e for e in self._iter_events() if e.timestamp > timestamp]
        out.sort(key=lambda e: e.timestamp)
        return out

    # ── States (design 0002) ─────────────────────────────────────────────
    # A state is a named value that changes over time. Which value is current
    # is decided by ``typedmem.state.resolve`` (validity time, then authority);
    # these methods store values and keep the index links in step with it.
    def _state_records(self, key: str, workspace: str) -> list[Memory]:
        return [m for m in self._iter()
                if m.type == STATE_TYPE and m.subject == key and m.workspace == workspace]

    def set_state(
        self,
        key: str,
        value: str,
        *,
        source: "Source | str | None" = None,
        authority: float | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        workspace: str | None = None,
        event_source: EventSource = "store",
        event_source_name: str | None = None,
    ) -> SetResult:
        """Record that ``key`` holds ``value`` (from ``valid_from``, default now).

        Nothing is overwritten. A later value supersedes the current one; an
        earlier one goes into history; the same value adds its source to the
        existing record. A value that can't be ordered against the current one
        (same start, or later but from a weaker source) opens a conflict. See
        design/0002-changing-facts.md."""
        if event_source not in EVENT_SOURCES:
            raise ValueError(
                f"event_source must be one of {sorted(EVENT_SOURCES)}, got {event_source!r}"
            )
        key, value = normalize_key(key), normalize_value(value)
        ws = workspace if workspace is not None else self.default_workspace
        src = Source.from_any(source)
        if authority is not None:
            src = (replace(src, authority=authority) if src
                   else Source(document_id="unspecified", authority=authority))
        incoming = Memory(
            type=STATE_TYPE, content=value, subject=key, workspace=ws,
            sources=[src] if src else [],
            valid_from=utc(valid_from), valid_to=utc(valid_to),
        )
        now = datetime.now(timezone.utc)          # after incoming.timestamp
        records = self._state_records(key, ws)
        before = resolve(records, now)
        previous = before.current.content if before.current else None
        was_conflict = tuple(before.values) if not before.settled and before.live else ()

        # The same value as the one in effect when this one starts: corroboration.
        at_start = resolve(records, incoming.effective_from)
        same = at_start.current if at_start.values == [value] else None
        if same is not None and incoming.valid_to in (None, same.valid_to):
            seen = {s.key() for s in same.sources}
            new = [s for s in incoming.sources if s.key() not in seen]
            if new:
                self.transitions.apply(Transition(
                    action="reinforced", memory_id=same.id,
                    changes={"sources": [*same.sources, *new]},
                    actor=event_source, actor_name=event_source_name,
                    reason=f"+{len(new)} source(s): "
                           + ", ".join(s.document_id for s in new),
                ))
            return self._set_result(key, value, "unchanged", same.id, ws, now,
                                    previous, was_conflict, source_added=bool(new))

        self.transitions.apply(Transition(
            action="create", memory=incoming,
            actor=event_source, actor_name=event_source_name,
            reason=f"set {key} = {value!r}",
        ))
        after = resolve(self._state_records(key, ws), now)
        self._relink_state(after, actor=event_source, actor_name=event_source_name)
        status = next(e.status for e in entries(key, after) if e.memory_id == incoming.id)
        outcome = {"scheduled": "scheduled", "conflict": "conflict", "previous": "past",
                   "current": "changed" if records else "new"}[status]
        return self._set_result(key, value, outcome, incoming.id, ws, now,
                                previous, was_conflict)

    def _set_result(self, key, value, outcome, memory_id, ws, now,
                    previous, was_conflict, source_added: bool = False) -> SetResult:
        res = resolve(self._state_records(key, ws), now)
        es = entries(key, res)
        entry = next(e for e in es if e.memory_id == memory_id)
        return SetResult(
            key=key, value=value, outcome=outcome, entry=entry, previous=previous,
            current=res.current.content if res.current else None,
            conflicts=tuple(e for e in es if e.status == "conflict"),
            resolved_conflict=was_conflict if res.settled else (),
            source_added=source_added,
        )

    def _relink_state(self, res: Resolution, *, actor, actor_name) -> None:
        """Bring ``superseded_by`` / ``conflicts_with`` in line with ``res``,
        one logged update per record whose links changed."""
        by_id = {m.id: m for m in res.records}
        for m in res.records:
            succ = res.successor.get(m.id)
            conf = sorted(res.conflicts.get(m.id, []))
            had = sorted(m.metadata.get("conflicts_with", []))
            if m.superseded_by == succ and had == conf:
                continue
            changes: dict = {}
            if m.superseded_by != succ:
                changes["superseded_by"] = succ
            if had != conf:
                md = {k: v for k, v in m.metadata.items() if k != "conflicts_with"}
                if conf:
                    md["conflicts_with"] = conf
                changes["metadata"] = md
            if succ and "superseded_by" in changes:
                action = "superseded"
                enders = sorted({by_id[i].content for i in res.ended_by.get(m.id, [succ])})
                reason = (f"superseded by {enders[0]!r}" if len(enders) == 1 else
                          "ended by conflicting values " + ", ".join(map(repr, enders)))
            elif conf and "metadata" in changes:
                action = "flagged"
                reason = "in conflict with " + ", ".join(
                    sorted({repr(by_id[i].content) for i in conf}))
            else:
                action = "relinked"
                reason = "state links updated"
            self.transitions.apply(Transition(
                action=action, memory_id=m.id, changes=changes,
                actor=actor, actor_name=actor_name, reason=reason,
            ))

    def get_state(self, key: str, *, workspace: str | None = None,
                  as_of: datetime | None = None) -> str | None:
        """The value of ``key`` in effect at ``as_of`` (default now), or ``None``
        if it has none. Raises ``StateConflict`` when values contend: a current
        value is never invented."""
        key = normalize_key(key)
        ws = workspace if workspace is not None else self.default_workspace
        res = resolve(self._state_records(key, ws),
                      utc(as_of) or datetime.now(timezone.utc))
        if not res.live:
            return None
        if not res.settled:
            raise StateConflict(
                key, [e for e in entries(key, res) if e.status == "conflict"])
        return res.current.content

    def state_history(self, key: str, *, workspace: str | None = None,
                      as_of: datetime | None = None) -> list[StateEntry]:
        """Every value ``key`` has held, newest first, with status and provenance."""
        key = normalize_key(key)
        ws = workspace if workspace is not None else self.default_workspace
        res = resolve(self._state_records(key, ws),
                      utc(as_of) or datetime.now(timezone.utc))
        return entries(key, res)

    # ── Legacy compat ────────────────────────────────────────────────────
    def evolution_history(self, memory_id: str) -> list[dict]:
        """v0.4.2-compatible shape: list of dicts with ``evolver``, ``action``,
        ``input_ids``, ``output_ids``, ``reason``, ``timestamp``. Backed by
        the v0.6a event log; entries that were stored in
        ``metadata["evolution_history"]`` migrate on first access."""
        return [e.to_legacy_history_dict() for e in self.history(memory_id)]

    # ── Evolution helpers ────────────────────────────────────────────────
    def contradictions(self, *, workspace: str | None = None) -> list[list[Memory]]:
        """Return groups of memories that cross-link via metadata.conflicts_with."""
        from ..evolvers.contradictions import ContradictionSurfacer
        return ContradictionSurfacer().clusters(self, workspace=workspace)

    def drift_flags(self, *, workspace: str | None = None) -> list[Memory]:
        """Memories that carry ``metadata['drift_flags']`` (post-drift-detector)."""
        ws = workspace if workspace is not None else self.default_workspace
        return [m for m in self._iter()
                if m.workspace == ws and m.metadata.get("drift_flags")]

    def find_slot(self, m: Memory) -> Memory | None:
        """Return the live memory occupying the same identity slot as ``m``, or
        None. Uses the store's ``IdentityStrategy``. With the default
        ``SlotIdentityStrategy`` this preserves historical behavior exactly —
        subject-less memories never collide, and the fast ``_find_same_slot``
        path (indexed on SQLite) is used. A custom identity strategy falls back
        to a key-based scan."""
        if isinstance(self.identity, SlotIdentityStrategy):
            if m.subject is None:
                return None
            return self._find_same_slot(m.workspace, m.type, m.subject)
        key = self.identity.key_for(m)
        for cand in self._iter():
            if (cand.superseded_by is None and cand.id != m.id
                    and self.identity.key_for(cand) == key):
                return cand
        return None

    def _find_same_slot(self, workspace: str, t: MemoryType, subject: str) -> Memory | None:
        for m in self._iter():
            if (m.type == t and m.subject == subject and m.workspace == workspace
                    and m.superseded_by is None):
                return m
        return None

    # ── Lazy migration of metadata["evolution_history"] ─────────────────
    def _migrate_legacy_history(self, memory_id: str) -> None:
        if memory_id in self._migrated_ids:
            return
        m = self._get(memory_id)
        if m is None:
            self._migrated_ids.add(memory_id)
            return
        legacy = m.metadata.get("evolution_history")
        if not legacy:
            self._migrated_ids.add(memory_id)
            return
        for entry in legacy:
            ts = entry.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts)
                except ValueError:
                    ts_dt = None
            else:
                ts_dt = None
            event = MemoryEvent(
                memory_id=memory_id,
                workspace=m.workspace,
                type=m.type,
                subject=m.subject,
                action=str(entry.get("action", "annotated")),
                source="system",
                source_name="migrate_evolution_history",
                reason=str(entry.get("reason", "")),
                input_ids=list(entry.get("input_ids", [])),
                output_ids=list(entry.get("output_ids", [])),
                payload={"legacy_evolver": entry.get("evolver")},
                timestamp=ts_dt or MemoryEvent.__dataclass_fields__["timestamp"].default_factory(),
            )
            self._append_event(event)
        m.metadata.pop("evolution_history", None)
        self._put(m)
        self._migrated_ids.add(memory_id)

    def _migrate_legacy_history_all(self) -> None:
        """Walk every memory once and migrate any leftover legacy history.
        Per-memory work is gated by ``_migrated_ids`` so this is O(n) only on
        the first call and cheap thereafter."""
        for m in list(self._iter()):
            if m.id in self._migrated_ids:
                continue
            self._migrate_legacy_history(m.id)

    # ── Conflict dispatch ─────────────────────────────────────────────────
    def _apply_conflict(
        self,
        existing: Memory,
        incoming: Memory,
        action: ConflictAction,
        *,
        event_source: EventSource = "store",
        event_source_name: str | None = None,
    ) -> Memory:
        """Backward-compatible shim. Conflict dispatch now lives in the kernel
        ``TransitionEngine`` (the single mutation funnel); this delegates so any
        existing caller keeps working."""
        return self.transitions._apply_conflict(
            existing, incoming, action,
            actor=event_source, actor_name=event_source_name,
        )

    def __iter__(self) -> Iterator[Memory]:
        return self._iter()

    def __len__(self) -> int:
        return sum(1 for _ in self._iter())

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
