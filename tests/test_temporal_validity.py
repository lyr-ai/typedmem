"""Temporal validity: ``Memory.valid_from`` / ``valid_to``.

``timestamp`` is when a memory was *observed*; ``[valid_from, valid_to)`` is
when its *content holds*. These tests pin the contract:

- ``None`` means unspecified (persisted as such), ``effective_from`` is the
  operational fallback to ``timestamp``;
- the window is half-open, so a switch-over instant has exactly one state;
- ``valid_from`` may be in the future relative to ``timestamp``;
- an empty/inverted window is rejected;
- temporal resolution filters by validity *before* picking the newest per slot;
- REPLACE ordering uses ``effective_from``;
- confidence decay still keys off ``timestamp``.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from typedmem import (
    ConflictPolicy,
    InMemoryStore,
    Memory,
    PolicyEngine,
    SQLiteMemoryStore,
)
from typedmem.retrieval import (
    RetrievalFilters,
    apply_filters,
    filter_valid,
    latest_per_slot,
    resolve_temporal,
)
from typedmem.schema import _now

UTC = timezone.utc
T = datetime(2026, 6, 1, tzinfo=UTC)
EPS = timedelta(microseconds=1)


def _pref(content, *, ts=None, valid_from=None, valid_to=None, subject="home", type="preference"):
    return Memory(
        type=type, content=content, subject=subject,
        timestamp=ts or _now(), valid_from=valid_from, valid_to=valid_to,
    )


# ── 1. model: fallback, persistence of None, round-trip ─────────────────────
def test_effective_from_falls_back_to_timestamp():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    m = _pref("a", ts=ts)
    assert m.valid_from is None            # persisted meaning: unspecified
    assert m.effective_from == ts          # operational fallback
    m2 = _pref("b", ts=ts, valid_from=T)
    assert m2.effective_from == T


def test_validity_round_trips_and_none_stays_none():
    m = _pref("a", valid_from=T, valid_to=T + timedelta(days=30))
    d = m.to_dict()
    assert d["valid_from"] == T.isoformat()
    back = Memory.from_dict(d)
    assert back.valid_from == T and back.valid_to == T + timedelta(days=30)

    bare = Memory.from_dict(_pref("b").to_dict())
    assert bare.valid_from is None and bare.valid_to is None

    # Pre-v0.9 record without the keys at all
    legacy = _pref("c").to_dict()
    legacy.pop("valid_from"); legacy.pop("valid_to")
    assert Memory.from_dict(legacy).valid_from is None


# ── 2. SQLite migration ─────────────────────────────────────────────────────
def test_sqlite_adds_validity_columns_and_persists(tmp_path):
    path = tmp_path / "v08.db"
    # Simulate a v0.8 database: create the table without the new columns.
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE memories (
        id TEXT PRIMARY KEY, type TEXT NOT NULL, content TEXT NOT NULL,
        confidence REAL NOT NULL, timestamp TEXT NOT NULL, subject TEXT,
        tags TEXT NOT NULL DEFAULT '[]', sources TEXT NOT NULL DEFAULT '[]',
        workspace TEXT NOT NULL DEFAULT 'default', superseded_by TEXT,
        metadata TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL,
        status TEXT, version INTEGER NOT NULL DEFAULT 1, embedder_id TEXT, embedding TEXT)""")
    now = _now().isoformat()
    conn.execute(
        "INSERT INTO memories (id,type,content,confidence,timestamp,updated_at) VALUES (?,?,?,?,?,?)",
        ("old", "fact", "legacy row", 1.0, now, now),
    )
    conn.commit(); conn.close()

    with SQLiteMemoryStore(path) as store:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(memories)")}
        assert {"valid_from", "valid_to"} <= cols
        legacy = store.get("old")
        assert legacy.valid_from is None and legacy.valid_to is None

        m = store.add(_pref("a", valid_from=T, valid_to=T + timedelta(days=1)))
    with SQLiteMemoryStore(path) as store:
        got = store.get(m.id)
        assert got.valid_from == T and got.valid_to == T + timedelta(days=1)


# ── 3. core case: observed recently, valid from earlier ─────────────────────
def test_as_of_resolves_against_validity_not_observation():
    two_years_ago = _now() - timedelta(days=730)
    one_month_ago = _now() - timedelta(days=30)
    san_jose = _pref("lives in San Jose", ts=two_years_ago)
    seattle = _pref("lives in Seattle", ts=_now(), valid_from=one_month_ago)

    then = resolve_temporal([san_jose, seattle], as_of=_now() - timedelta(days=60),
                            collapse_types={"preference"})
    assert then == [san_jose]
    now = resolve_temporal([san_jose, seattle], collapse_types={"preference"})
    assert now == [seattle]


# ── 4. window filtering: expired AND future are excluded ────────────────────
def test_expired_and_future_memories_excluded_by_default():
    expired = _pref("old", ts=_now() - timedelta(days=10), valid_to=_now() - timedelta(days=1))
    future = _pref("planned", ts=_now(), valid_from=_now() + timedelta(days=30))
    current = _pref("now", ts=_now() - timedelta(days=5))

    got = resolve_temporal([expired, future, current], collapse_types={"preference"})
    assert got == [current]

    # include_expired brings back the expired one but never the future one
    got = resolve_temporal([expired, future, current], collapse_types={"preference"},
                           include_expired=True)
    assert set(m.id for m in got) == {current.id}  # still collapsed to newest
    assert {m.id for m in filter_valid([expired, future, current], include_expired=True)} \
        == {expired.id, current.id}


def test_future_valid_memory_does_not_shadow_current_state():
    """Filter first, then pick newest: a future ``valid_from`` must not win the
    slot just because it is the largest effective_from."""
    current = _pref("Postgres", ts=_now() - timedelta(days=5))
    planned = _pref("CockroachDB", ts=_now(), valid_from=_now() + timedelta(days=30))
    assert resolve_temporal([current, planned], collapse_types={"preference"}) == [current]
    # standalone latest_per_slot with as_of honours the same invariant
    assert latest_per_slot([current, planned], types={"preference"}, as_of=_now()) == [current]
    # ...and after the switch-over date the planned one wins
    later = _now() + timedelta(days=31)
    assert resolve_temporal([current, planned], as_of=later, collapse_types={"preference"}) == [planned]


# ── 5. unchanged behaviour without validity fields ──────────────────────────
def test_latest_per_slot_without_validity_matches_previous_behaviour():
    jan = datetime(2026, 1, 1, tzinfo=UTC)
    jul = datetime(2026, 7, 1, tzinfo=UTC)
    old = _pref("startups", ts=jan, subject="companies")
    new = _pref("mature companies", ts=jul, subject="companies")
    assert latest_per_slot([old, new], types={"preference"}) == [new]
    assert resolve_temporal([old, new], collapse_types={"preference"}) == [new]
    assert apply_filters([old, new], RetrievalFilters(as_of=jan)) == [old]


# ── 6. REPLACE compares effective_from ───────────────────────────────────────
def test_replace_ignores_recently_observed_but_earlier_valid_state():
    engine = PolicyEngine()
    jan = datetime(2026, 1, 1, tzinfo=UTC)
    existing = _pref("Seattle", ts=jan, valid_from=jan)
    incoming = _pref("San Jose", ts=datetime(2026, 9, 1, tzinfo=UTC),
                     valid_from=datetime(2025, 12, 1, tzinfo=UTC))
    action = engine.resolve(existing, incoming)
    assert action.policy is ConflictPolicy.IGNORE
    assert action.notes == "incoming weaker than existing for replace"  # wording unchanged

    # And the store-level outcome: existing untouched, no version bump.
    store = InMemoryStore()
    kept = store.add(_pref("Seattle", ts=jan, valid_from=jan))
    store.add(_pref("San Jose", ts=datetime(2026, 9, 1, tzinfo=UTC),
                    valid_from=datetime(2025, 12, 1, tzinfo=UTC)))
    assert store.get(kept.id).content == "Seattle"
    assert store.get(kept.id).version == 1


def test_replace_carries_incoming_validity_onto_record():
    store = InMemoryStore()
    start, end = _now() - timedelta(hours=1), _now() + timedelta(days=90)
    kept = store.add(_pref("Seattle", ts=_now() - timedelta(days=1)))
    store.add(_pref("Portland", ts=_now(), valid_from=start, valid_to=end))
    got = store.get(kept.id)
    assert got.content == "Portland"
    assert got.valid_from == start and got.valid_to == end


# ── 7. decay is anchored on timestamp, not validity ─────────────────────────
def test_decay_ignores_valid_from():
    engine = PolicyEngine()
    ts = _now() - timedelta(days=60)   # preference half-life is 60d
    plain = _pref("a", ts=ts)
    declared = _pref("a", ts=ts, valid_from=_now() - timedelta(days=1))
    now = _now()
    assert engine.effective_confidence(plain, now) == pytest.approx(
        engine.effective_confidence(declared, now))
    assert engine.effective_confidence(plain, now) == pytest.approx(0.5, abs=1e-3)


# ── 8. exact boundary: [from, to) ───────────────────────────────────────────
def test_switch_over_instant_has_exactly_one_valid_state():
    a = _pref("A", ts=T - timedelta(days=10), valid_to=T)
    b = _pref("B", ts=T - timedelta(days=1), valid_from=T)
    assert resolve_temporal([a, b], as_of=T - EPS, collapse_types={"preference"}) == [a]
    assert resolve_temporal([a, b], as_of=T, collapse_types={"preference"}) == [b]
    assert a.is_valid_at(T) is False and b.is_valid_at(T) is True


# ── 9. invalid intervals are rejected ───────────────────────────────────────
def test_empty_or_inverted_window_rejected():
    with pytest.raises(ValueError, match="valid_to"):
        _pref("x", valid_from=T, valid_to=T)                      # empty
    with pytest.raises(ValueError, match="valid_to"):
        _pref("x", valid_from=T, valid_to=T - timedelta(days=1))  # inverted
    with pytest.raises(ValueError, match="valid_to"):
        _pref("x", ts=T, valid_to=T - timedelta(days=1))          # inverted vs. fallback
    # future valid_from is fine
    _pref("x", ts=T, valid_from=T + timedelta(days=30))
