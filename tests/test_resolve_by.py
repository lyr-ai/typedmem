"""Per-type REPLACE guards: ``TypePolicy.resolve_by``.

Guard semantics, not priority order: an incoming memory may REPLACE the
existing one only if it is no weaker on *every* listed key. The default,
``("effective_from", "confidence")``, reproduces the historical rule exactly;
the authority veto stays a separate, policy-independent guard that runs first.
"""

from datetime import timedelta

import pytest

from typedmem import (
    DEFAULT_RESOLVE_BY,
    ConflictPolicy,
    DomainProfile,
    InMemoryStore,
    Memory,
    PolicyEngine,
    Source,
    SQLiteMemoryStore,
    TypePolicy,
    TypeSpec,
)
from typedmem.policy import DEFAULT_POLICIES
from typedmem.schema import _now


def _engine(resolve_by=None, policy=ConflictPolicy.REPLACE):
    pols = dict(DEFAULT_POLICIES)
    kw = {} if resolve_by is None else {"resolve_by": resolve_by}
    pols["preference"] = TypePolicy(None, False, policy, **kw)
    return PolicyEngine(pols)


def _pref(content, *, confidence=1.0, days_ago=0, authority=None):
    return Memory(
        "preference", content, subject="drink", confidence=confidence,
        timestamp=_now() - timedelta(days=days_ago),
        sources=[] if authority is None else [Source("doc", authority=authority)],
    )


EXISTING = dict(confidence=0.9, days_ago=1)
# (label, incoming kwargs)
CASES = {
    "newer+stronger": dict(confidence=0.95, days_ago=0),
    "newer+weaker":   dict(confidence=0.4,  days_ago=0),
    "older+stronger": dict(confidence=0.95, days_ago=2),
    "older+weaker":   dict(confidence=0.4,  days_ago=2),
}


def _outcomes(resolve_by):
    engine = _engine(resolve_by)
    return {
        label: engine.resolve(_pref("a", **EXISTING), _pref("b", **kw)).policy
        for label, kw in CASES.items()
    }


# ── default reproduces the historical rule ───────────────────────────────────
def test_default_is_effective_from_and_confidence():
    assert TypePolicy(None, False, ConflictPolicy.REPLACE).resolve_by == DEFAULT_RESOLVE_BY
    assert DEFAULT_RESOLVE_BY == ("effective_from", "confidence")
    for t, p in DEFAULT_POLICIES.items():
        assert p.resolve_by == DEFAULT_RESOLVE_BY, t


def test_default_guard_matches_pre_v09_behaviour():
    R, I = ConflictPolicy.REPLACE, ConflictPolicy.IGNORE
    assert _outcomes(None) == {
        "newer+stronger": R,
        "newer+weaker":   I,   # confidence is a guard, not a tie-breaker
        "older+stronger": I,
        "older+weaker":   I,
    }


# ── guard semantics for custom sets ─────────────────────────────────────────
def test_single_key_guards():
    R, I = ConflictPolicy.REPLACE, ConflictPolicy.IGNORE
    assert _outcomes(("effective_from",)) == {
        "newer+stronger": R, "newer+weaker": R, "older+stronger": I, "older+weaker": I,
    }
    assert _outcomes(("confidence",)) == {
        "newer+stronger": R, "newer+weaker": I, "older+stronger": R, "older+weaker": I,
    }


def test_empty_resolve_by_always_replaces():
    assert set(_outcomes(()).values()) == {ConflictPolicy.REPLACE}


def test_order_is_irrelevant():
    assert _outcomes(("confidence", "effective_from")) == _outcomes(("effective_from", "confidence"))


def test_ignore_reason_wording_unchanged():
    action = _engine(("confidence",)).resolve(_pref("a", confidence=0.9), _pref("b", confidence=0.4))
    assert action.policy is ConflictPolicy.IGNORE
    assert action.notes == "incoming weaker than existing for replace"


# ── authority veto is independent of resolve_by ─────────────────────────────
def test_authority_veto_runs_before_and_regardless_of_resolve_by():
    for resolve_by in ((), ("effective_from",), ("confidence",), DEFAULT_RESOLVE_BY):
        engine = _engine(resolve_by)
        action = engine.resolve(
            _pref("explicit", confidence=0.7, days_ago=730, authority=1.0),
            _pref("inferred", confidence=0.95, days_ago=0, authority=0.3),
        )
        assert action.policy is ConflictPolicy.IGNORE, resolve_by
        assert "authority" in action.notes


def test_resolve_by_only_consulted_under_replace():
    for policy in (ConflictPolicy.SUPERSEDE, ConflictPolicy.KEEP_BOTH,
                   ConflictPolicy.FLAG, ConflictPolicy.REINFORCE):
        engine = _engine(("confidence",), policy=policy)
        action = engine.resolve(_pref("a", confidence=0.9), _pref("b", confidence=0.1))
        assert action.policy is policy


# ── validation ──────────────────────────────────────────────────────────────
def test_unknown_and_duplicate_keys_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown resolve_by key"):
        TypePolicy(None, False, ConflictPolicy.REPLACE, resolve_by=("authority",))
    with pytest.raises(ValueError, match="unknown resolve_by key"):
        TypePolicy(None, False, ConflictPolicy.REPLACE, resolve_by=("timestamp",))
    with pytest.raises(ValueError, match="duplicate"):
        TypePolicy(None, False, ConflictPolicy.REPLACE, resolve_by=("confidence", "confidence"))


def test_list_normalized_to_tuple_and_hashable():
    p = TypePolicy(None, False, ConflictPolicy.REPLACE, resolve_by=["confidence"])
    assert p.resolve_by == ("confidence",)
    hash(p)  # frozen dataclass stays hashable after normalization


# ── TypeSpec / profile plumbing ─────────────────────────────────────────────
def test_typespec_none_means_policy_default_and_is_omitted_from_dict():
    spec = TypeSpec(name="preference", conflict_policy=ConflictPolicy.REPLACE)
    assert spec.resolve_by is None
    assert spec.to_policy().resolve_by == DEFAULT_RESOLVE_BY
    assert "resolve_by" not in spec.to_dict()
    assert TypeSpec.from_dict(spec.to_dict()) == spec


def test_typespec_explicit_resolve_by_round_trips():
    spec = TypeSpec(name="preference", conflict_policy=ConflictPolicy.REPLACE,
                    resolve_by=["effective_from"])
    assert spec.resolve_by == ("effective_from",)
    assert spec.to_policy().resolve_by == ("effective_from",)
    d = spec.to_dict()
    assert d["resolve_by"] == ["effective_from"]
    assert TypeSpec.from_dict(d) == spec


def test_profile_with_bad_resolve_by_fails_at_load_time():
    with pytest.raises(ValueError, match="unknown resolve_by key"):
        DomainProfile.from_dict({
            "name": "p",
            "types": {"preference": {"conflict_policy": "replace", "resolve_by": ["recency"]}},
        })


def test_builtin_profiles_unchanged():
    for name in ("core", "personal", "child_development", "research_paper", "engineering_design"):
        for t, spec in DomainProfile.builtin(name).all_types().items():
            assert spec.resolve_by is None, (name, t)
            assert spec.to_policy().resolve_by == DEFAULT_RESOLVE_BY, (name, t)


# ── end to end through a profile-bound store ────────────────────────────────
def test_profile_resolve_by_changes_store_outcome(tmp_path):
    profile = DomainProfile.from_dict({
        "name": "newest-wins",
        "types": {"preference": {"conflict_policy": "replace", "resolve_by": ["effective_from"]}},
    })
    with SQLiteMemoryStore.for_profile(profile, path=tmp_path / "m.db") as store:
        kept = store.add(_pref("tea", confidence=0.9, days_ago=1))
        store.add(_pref("coffee", confidence=0.4, days_ago=0))   # newer but weaker
        assert store.get(kept.id).content == "coffee"            # replaced under this profile
        assert store.get(kept.id).version == 2

    default = InMemoryStore()
    kept = default.add(_pref("tea", confidence=0.9, days_ago=1))
    default.add(_pref("coffee", confidence=0.4, days_ago=0))
    assert default.get(kept.id).content == "tea"                # ignored under the default
