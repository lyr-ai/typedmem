"""Source authority in REPLACE conflict resolution.

``Source.authority`` has been documented as a "weight in conflict resolution"
since v0.4a (CLI ``--authority`` help, ``source.py`` docstring), but
``PolicyEngine.resolve`` only ever consulted timestamp and confidence. These
tests pin the contract: a lower-authority incoming memory cannot REPLACE a
higher-authority existing one, regardless of recency or confidence.
"""

from datetime import timedelta

from typedmem import (
    ConflictPolicy,
    InMemoryStore,
    Memory,
    MemoryType,
    PolicyEngine,
    Source,
)
from typedmem.policy import memory_authority
from typedmem.schema import _now


def _pref(content, *, authority=None, confidence=1.0, days_ago=0, sources=None):
    if sources is None:
        sources = [] if authority is None else [Source("doc", authority=authority)]
    return Memory(
        MemoryType.PREFERENCE, content, subject="home",
        confidence=confidence, sources=sources,
        timestamp=_now() - timedelta(days=days_ago),
    )


# ── the regression case from the field ───────────────────────────────────────
def test_old_explicit_statement_beats_new_confident_inference():
    """Explicit user statement (authority 1.0, old, conf 0.7) vs. model
    inference (authority 0.3, new, conf 0.95) → IGNORE. Before this fix the
    inference silently replaced the statement because it was newer and more
    confident."""
    engine = PolicyEngine()
    existing = _pref("lives in San Jose", authority=1.0, confidence=0.7, days_ago=730)
    incoming = _pref("lives in Seattle", authority=0.3, confidence=0.95)

    action = engine.resolve(existing, incoming)

    assert action.policy is ConflictPolicy.IGNORE
    assert "authority" in action.notes


def test_store_keeps_explicit_statement_end_to_end():
    store = InMemoryStore()
    kept = store.add(_pref("lives in San Jose", authority=1.0, confidence=0.7, days_ago=730))
    store.add(_pref("lives in Seattle", authority=0.3, confidence=0.95))

    assert len(store) == 1
    assert store.get(kept.id).content == "lives in San Jose"
    assert store.get(kept.id).version == 1  # IGNORE mutates nothing
    actions = [e.action for e in store.history(kept.id)]
    assert "replaced" not in actions


# ── higher / equal authority keeps existing semantics ────────────────────────
def test_newer_higher_authority_replaces():
    engine = PolicyEngine()
    existing = _pref("lives in San Jose", authority=0.3, days_ago=1)
    incoming = _pref("lives in Seattle", authority=1.0)
    assert engine.resolve(existing, incoming).policy is ConflictPolicy.REPLACE


def test_equal_authority_falls_through_to_timestamp_and_confidence():
    engine = PolicyEngine()
    # newer + equal confidence → REPLACE, as before
    assert engine.resolve(
        _pref("a", authority=0.8, days_ago=1), _pref("b", authority=0.8),
    ).policy is ConflictPolicy.REPLACE
    # older → IGNORE, as before
    older = engine.resolve(_pref("a", authority=0.8), _pref("b", authority=0.8, days_ago=1))
    assert older.policy is ConflictPolicy.IGNORE
    assert older.notes == "incoming weaker than existing for replace"
    # less confident → IGNORE, as before
    weaker = engine.resolve(
        _pref("a", authority=0.8, confidence=0.9, days_ago=1),
        _pref("b", authority=0.8, confidence=0.4),
    )
    assert weaker.policy is ConflictPolicy.IGNORE


def test_higher_authority_does_not_override_timestamp_or_confidence_guard():
    """Authority is a veto for the weaker side, not a trump card for the
    stronger side: a high-authority incoming that is *older* still loses to
    the existing timestamp rule."""
    engine = PolicyEngine()
    existing = _pref("a", authority=0.3)
    incoming = _pref("b", authority=1.0, days_ago=1)
    assert engine.resolve(existing, incoming).policy is ConflictPolicy.IGNORE


# ── missing provenance makes no authority claim ───────────────────────────────
def test_no_sources_on_either_side_skips_authority_check():
    engine = PolicyEngine()
    # existing has provenance, incoming has none → old rules only
    assert engine.resolve(
        _pref("a", authority=1.0, days_ago=1), _pref("b"),
    ).policy is ConflictPolicy.REPLACE
    # existing has none, incoming has low authority → old rules only
    assert engine.resolve(
        _pref("a", days_ago=1), _pref("b", authority=0.1),
    ).policy is ConflictPolicy.REPLACE
    # neither → unchanged v0.4a behaviour
    assert engine.resolve(_pref("a", days_ago=1), _pref("b")).policy is ConflictPolicy.REPLACE


# ── multi-source memories use their strongest source ─────────────────────────
def test_memory_authority_is_max_over_sources():
    m = _pref("a", sources=[
        Source("weak", authority=0.2),
        Source("strong", authority=0.9),
        Source("mid", authority=0.5),
    ])
    assert memory_authority(m) == 0.9
    assert memory_authority(_pref("b")) is None


def test_reinforced_memory_defended_by_best_source():
    engine = PolicyEngine()
    existing = _pref("a", days_ago=1, sources=[
        Source("weak", authority=0.2), Source("strong", authority=0.9),
    ])
    incoming = _pref("b", authority=0.5)
    assert engine.resolve(existing, incoming).policy is ConflictPolicy.IGNORE


# ── other policies are untouched ──────────────────────────────────────────────
def test_authority_guard_only_applies_to_replace():
    from typedmem import TypePolicy
    from typedmem.policy import DEFAULT_POLICIES

    for policy in (ConflictPolicy.SUPERSEDE, ConflictPolicy.KEEP_BOTH,
                   ConflictPolicy.FLAG, ConflictPolicy.REINFORCE):
        pols = dict(DEFAULT_POLICIES)
        pols["preference"] = TypePolicy(None, False, policy)
        engine = PolicyEngine(pols)
        existing = _pref("a", authority=1.0, days_ago=1)
        incoming = _pref("b", authority=0.1)
        assert engine.resolve(existing, incoming).policy is policy


def test_reinforce_authority_weighting_unchanged():
    """The pre-existing use of authority (REINFORCE confidence blend) must
    produce the same numbers as before."""
    engine = PolicyEngine()
    # weight = 0.5 authority; bump = c_new * weight * 0.5 = 0.8*0.5*0.5 = 0.2
    # result = 0.5 + (1-0.5)*0.2 = 0.6
    got = engine.reinforce_confidence(0.5, 0.8, [Source("d", authority=0.5)])
    assert abs(got - 0.6) < 1e-9
