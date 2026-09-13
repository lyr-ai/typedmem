"""Replayable event log: full before/after snapshots + ``replay``.

Contract pinned here:

- every state-changing event carries ``snapshot_version``, ``before``, ``after``
  as ``Memory.to_dict()`` values (never object references);
- ``replay(events)`` folds ``after`` snapshots in order and reproduces the
  live state exactly — validity, sources, version, metadata included;
- snapshots are immutable values: mutating the live object later does not
  change history;
- replay applies outcomes and never re-runs policy, so the same stream
  replays identically regardless of the current ``PolicyEngine``;
- the log survives JSONL / SQLite round-trips and stays replayable;
- legacy events without snapshots are readable but not replayable
  (``ReplayError`` in strict mode, skipped otherwise).
"""

from datetime import datetime, timedelta, timezone

import pytest

from typedmem import (
    SNAPSHOT_VERSION,
    ConflictPolicy,
    GoalResolver,
    HashingEmbeddingProvider,
    InMemoryStore,
    JSONLMemoryStore,
    Memory,
    MemoryEvent,
    MemoryType,
    PolicyEngine,
    ReplayError,
    SQLiteMemoryStore,
    Source,
    TypePolicy,
    replay,
    snapshot,
)
from typedmem.policy import DEFAULT_POLICIES
from typedmem.schema import _now

UTC = timezone.utc


def _engine(**overrides):
    pols = dict(DEFAULT_POLICIES)
    for t, policy in overrides.items():
        pols[t] = TypePolicy(None, False, policy)
    return PolicyEngine(pols)


def _live(store) -> dict[str, dict]:
    return {m.id: snapshot(m) for m in store}


def _replayed(store, **kw) -> dict[str, dict]:
    return {mid: snapshot(m) for mid, m in store.replay(**kw).items()}


# ── every event is self-contained ───────────────────────────────────────────
def test_every_lifecycle_event_carries_snapshots():
    store = InMemoryStore()
    a = store.add(Memory("preference", "tea", subject="drink", confidence=0.6))
    store.add(Memory("preference", "coffee", subject="drink", confidence=0.9))   # REPLACE
    store.delete(a.id)

    events = store.history(a.id)
    assert [e.action for e in events] == ["added", "replaced", "deleted"]
    for e in events:
        assert e.has_snapshot and e.payload["snapshot_version"] == SNAPSHOT_VERSION
        assert e.payload["version"] == (e.after or e.before)["version"]

    added, replaced, deleted = events
    assert added.before is None and added.after["content"] == "tea"
    assert replaced.before["content"] == "tea" and replaced.after["content"] == "coffee"
    assert replaced.before["version"] == 1 and replaced.after["version"] == 2
    assert deleted.before["content"] == "coffee" and deleted.after is None


# ── add → replace → reinforce → delete replays to the live state ────────────
def test_replay_reproduces_live_state_across_policies():
    store = InMemoryStore(_engine(fact=ConflictPolicy.REINFORCE, claim=ConflictPolicy.SUPERSEDE,
                                  risk=ConflictPolicy.FLAG, note=ConflictPolicy.KEEP_BOTH))
    # REPLACE (preference default)
    store.add(Memory("preference", "tea", subject="drink", confidence=0.6))
    store.add(Memory("preference", "coffee", subject="drink", confidence=0.9))
    # REINFORCE, with a new source and then a duplicate source
    src = Source("doc1", chunk_id="c1", authority=0.8)
    store.add(Memory("fact", "earth orbits sun", subject="astro", confidence=0.6, sources=[src]))
    store.add(Memory("fact", "earth orbits sun", subject="astro", confidence=0.7,
                     sources=[Source("doc2", authority=0.5)]))
    store.add(Memory("fact", "earth orbits sun", subject="astro", confidence=0.7, sources=[src]))
    # SUPERSEDE
    store.add(Memory("claim", "v1", subject="design"))
    store.add(Memory("claim", "v2", subject="design"))
    # FLAG
    store.add(Memory("risk", "sqlite is fine", subject="storage"))
    store.add(Memory("risk", "sqlite blocks", subject="storage"))
    # KEEP_BOTH + delete
    store.add(Memory("note", "n1", subject="misc"))
    doomed = store.add(Memory("note", "n2", subject="misc"))
    store.delete(doomed.id)
    # evolver-driven update through the TransitionEngine
    store.add(Memory(MemoryType.GOAL, "learn to count to ten", subject="child"))
    store.add(Memory(MemoryType.EVENT, "child counted to ten today", subject="child"))
    GoalResolver(HashingEmbeddingProvider(dim=1024), threshold=0.2).evolve(store)

    assert _replayed(store) == _live(store)
    assert len(store.replay()) == len(store)


def test_replay_restores_validity_sources_version_and_metadata():
    store = InMemoryStore()
    vf, vt = datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)
    m = store.add(Memory(
        "preference", "Seattle", subject="home", confidence=0.7,
        sources=[Source("user", chunk_id="c", span=(0, 7), authority=1.0, uri="u://x")],
        tags=["b", "a"], metadata={"k": {"nested": [1, 2]}}, valid_from=vf, valid_to=vt,
    ))
    store.add(Memory("preference", "Portland", subject="home", confidence=0.9,
                     valid_from=vf + timedelta(days=1)))  # REPLACE → version 2
    back = store.replay()[m.id]
    live = store.get(m.id)
    assert back.version == live.version == 2
    assert back.valid_from == vf + timedelta(days=1) and back.valid_to is None
    assert [s.key() for s in back.sources] == [s.key() for s in live.sources]
    assert back.sources[0].authority == 1.0 and back.sources[0].uri == "u://x"
    assert back.metadata == live.metadata and set(back.tags) == set(live.tags)
    assert back.timestamp == live.timestamp and back.updated_at == live.updated_at


# ── snapshots are values, not references ────────────────────────────────────
def test_snapshot_is_immune_to_later_mutation_of_live_object():
    store = InMemoryStore()
    m = store.add(Memory("fact", "original", subject="s", tags=["t"],
                         sources=[Source("d")], metadata={"k": [1]}))
    added = store.history(m.id)[0]
    frozen = dict(added.after)

    live = store.get(m.id)           # InMemoryStore hands back the live object
    live.content = "mutated"
    live.tags.append("t2")
    live.sources.append(Source("d2"))
    live.metadata["k"].append(2)
    live.metadata["new"] = True

    assert added.after == frozen
    assert added.after["content"] == "original"
    assert added.after["tags"] == ["t"]
    assert [s["document_id"] for s in added.after["sources"]] == ["d"]
    assert added.after["metadata"] == {"k": [1]}


def test_snapshot_strips_store_cache_keys_only():
    m = Memory("fact", "x", metadata={"_embedding": [0.1, 0.2], "_embedder_id": "h", "keep": 1})
    snap = snapshot(m)
    assert snap["metadata"] == {"keep": 1}
    assert m.metadata["_embedding"] == [0.1, 0.2]      # source object untouched
    assert snapshot(None) is None


# ── replay applies outcomes; it never re-runs policy ────────────────────────
def test_replay_is_independent_of_current_policy():
    a = InMemoryStore()                                   # preference → REPLACE
    a.add(Memory("preference", "tea", subject="drink", confidence=0.6))
    a.add(Memory("preference", "coffee", subject="drink", confidence=0.9))
    events = a.timeline()
    assert len(a) == 1

    b = InMemoryStore(_engine(preference=ConflictPolicy.KEEP_BOTH))
    b.add(Memory("preference", "tea", subject="drink", confidence=0.6))
    b.add(Memory("preference", "coffee", subject="drink", confidence=0.9))
    assert len(b) == 2                                    # a different policy decides differently...

    state = replay(events)                                # ...but the recorded outcome is fixed
    assert len(state) == 1
    assert next(iter(state.values())).content == "coffee"
    assert {mid: snapshot(m) for mid, m in state.items()} == _live(a)


def test_reinforce_without_new_sources_is_logged_and_replayable():
    store = InMemoryStore(_engine(fact=ConflictPolicy.REINFORCE))
    src = Source("d", chunk_id="c")
    m = store.add(Memory("fact", "claim", subject="t", confidence=0.6, sources=[src]))
    store.add(Memory("fact", "claim", subject="t", confidence=0.7, sources=[src]))
    live = store.get(m.id)
    assert live.version == 2 and live.confidence > 0.6
    ev = store.history(m.id)[-1]
    assert ev.action == "reinforced" and ev.reason.startswith("+0 source(s)")
    assert ev.before["version"] == 1 and ev.after["version"] == 2
    assert _replayed(store) == _live(store)


# ── persistence round-trips ─────────────────────────────────────────────────
@pytest.mark.parametrize("backend", ["jsonl", "sqlite"])
def test_persisted_log_replays_after_reopen(tmp_path, backend):
    path = tmp_path / ("mem.jsonl" if backend == "jsonl" else "mem.db")
    open_store = (lambda: JSONLMemoryStore(path)) if backend == "jsonl" else (lambda: SQLiteMemoryStore(path))

    store = open_store()
    a = store.add(Memory("preference", "tea", subject="drink", confidence=0.6,
                         sources=[Source("u", authority=1.0)], valid_from=_now() - timedelta(days=1)))
    store.add(Memory("preference", "coffee", subject="drink", confidence=0.9,
                     sources=[Source("u", authority=1.0)]))
    gone = store.add(Memory("fact", "temporary", subject="x"))
    store.delete(gone.id)
    expected = _live(store)
    store.close()

    store = open_store()
    try:
        assert _live(store) == expected
        assert _replayed(store) == expected
        ev = store.history(a.id)[1]
        assert ev.action == "replaced" and ev.before["content"] == "tea"
        assert ev.after["sources"][0]["authority"] == 1.0
    finally:
        store.close()


def test_sqlite_event_order_is_stable_for_equal_timestamps(tmp_path):
    with SQLiteMemoryStore(tmp_path / "t.db") as store:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(5):
            store._append_event(MemoryEvent(
                memory_id="m", workspace="default", action=f"a{i}", source="system",
                timestamp=ts, payload={"snapshot_version": SNAPSHOT_VERSION, "before": None,
                                       "after": Memory("fact", f"v{i}", id="m", timestamp=ts).to_dict()},
            ))
        assert [e.action for e in store.history("m")] == [f"a{i}" for i in range(5)]
        assert store.replay()["m"].content == "v4"


# ── legacy / unknown snapshots ──────────────────────────────────────────────
def _legacy(memory_id="legacy", action="added"):
    return MemoryEvent(memory_id=memory_id, workspace="default", action=action,
                       source="store", payload={"version": 1})


def test_legacy_event_is_readable_but_not_replayable():
    legacy = _legacy()
    assert legacy.has_snapshot is False and legacy.before is None and legacy.after is None
    ok = MemoryEvent(memory_id="m", workspace="default", action="added", source="store",
                     payload={"snapshot_version": SNAPSHOT_VERSION, "before": None,
                              "after": Memory("fact", "x", id="m").to_dict()})
    with pytest.raises(ReplayError, match="predates replayable logging"):
        replay([legacy, ok])
    state = replay([legacy, ok], strict=False)
    assert set(state) == {"m"}


def test_unknown_snapshot_version_rejected():
    bad = MemoryEvent(memory_id="m", workspace="default", action="added", source="store",
                      payload={"snapshot_version": SNAPSHOT_VERSION + 1, "before": None,
                               "after": Memory("fact", "x", id="m").to_dict()})
    with pytest.raises(ReplayError, match="snapshot_version"):
        replay([bad])
