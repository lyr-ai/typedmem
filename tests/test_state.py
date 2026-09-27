"""States: design/0002-changing-facts.md, acceptance tests 1–8.

Test 1 (the README first screen) is ``test_readme_contract.py``; its core
rules are also checked here against every backend."""

from datetime import datetime, timedelta, timezone

import pytest

from typedmem import (
    AgentMemory,
    DomainProfile,
    InMemoryStore,
    JSONLMemoryStore,
    Memory,
    PolicyEngine,
    SQLiteMemoryStore,
    StateConflict,
)
from typedmem.profiles import BUILTIN_PROFILES


def d(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "jsonl", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        s = InMemoryStore()
    elif request.param == "jsonl":
        s = JSONLMemoryStore(tmp_path / "m.jsonl")
    else:
        s = SQLiteMemoryStore(tmp_path / "m.db")
    yield s
    s.close()


def values(store, key="alice.employer"):
    return [(e.status, e.value) for e in store.state_history(key)]


# 1. set → set → get → history
def test_later_value_supersedes_and_keeps_history(store):
    r1 = store.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    r2 = store.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    assert (r1.outcome, r1.previous) == ("new", None)
    assert (r2.outcome, r2.previous, r2.current) == ("changed", "OpenAI", "Anthropic")
    assert store.get_state("alice.employer") == "Anthropic"
    assert values(store) == [("current", "Anthropic"), ("previous", "OpenAI")]
    old = store.state_history("alice.employer")[1]
    assert (old.valid_from, old.valid_to) == (d("2021-01-01"), d("2024-01-01"))
    # nothing erased, and the index agrees: only the current value is active
    assert [m.content for m in store.all()] == ["Anthropic"]
    assert len(store.all(include_superseded=True)) == 2


# 2. the same value again is corroboration, not a change
def test_same_value_adds_source_without_new_history(store):
    store.set_state("alice.employer", "Anthropic", source="cli")
    r = store.set_state("alice.employer", "Anthropic", source="email from Alice")
    assert r.outcome == "unchanged"
    assert values(store) == [("current", "Anthropic")]
    assert [s.document_id for s in r.entry.sources] == ["cli", "email from Alice"]
    again = store.set_state("alice.employer", "Anthropic", source="email from Alice")
    assert again.outcome == "unchanged" and len(again.entry.sources) == 2


# 3. validity time, not arrival order
def test_late_arriving_past_value_lands_in_history(store):
    store.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    store.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    r = store.set_state("alice.employer", "Google", valid_from=d("2022-06-01"))
    assert (r.outcome, r.current) == ("past", "Anthropic")
    assert store.get_state("alice.employer") == "Anthropic"
    hist = store.state_history("alice.employer")
    assert [e.value for e in reversed(hist)] == ["OpenAI", "Google", "Anthropic"]
    assert [(e.valid_from, e.valid_to) for e in reversed(hist)] == [
        (d("2021-01-01"), d("2022-06-01")),
        (d("2022-06-01"), d("2024-01-01")),
        (d("2024-01-01"), None),
    ]
    assert store.get_state("alice.employer", as_of=d("2023-01-01")) == "Google"


# 4. same start, different values: a conflict, and get() never picks one
def test_simultaneous_disagreement_is_a_conflict(store):
    store.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    r = store.set_state("alice.employer", "OpenAI", valid_from=d("2024-01-01"),
                        source="agent inference")
    assert (r.outcome, r.current) == ("conflict", None)
    with pytest.raises(StateConflict) as exc:
        store.get_state("alice.employer")
    assert sorted(e.value for e in exc.value.entries) == ["Anthropic", "OpenAI"]
    assert all(e.status == "conflict" for e in exc.value.entries)
    [cluster] = store.contradictions()
    assert sorted(m.content for m in cluster) == ["Anthropic", "OpenAI"]


# 5. later but weaker: a conflict, not a silent overwrite or a silent ignore
def test_later_weaker_value_is_a_conflict(store):
    store.set_state("alice.employer", "Anthropic", source="user", valid_from=d("2024-01-01"))
    r = store.set_state("alice.employer", "OpenAI", source="agent inference",
                        authority=0.3, valid_from=d("2025-01-01"))
    assert r.outcome == "conflict"
    with pytest.raises(StateConflict):
        store.get_state("alice.employer")
    # before the disputed change the state is settled
    assert store.get_state("alice.employer", as_of=d("2024-06-01")) == "Anthropic"
    # a later *stronger* value supersedes a weaker one normally
    store.set_state("bob.city", "Paris", source="agent", authority=0.3, valid_from=d("2024-01-01"))
    assert store.set_state("bob.city", "Rome", source="user",
                           valid_from=d("2025-01-01")).outcome == "changed"


# 6. a stronger later value resolves the conflict
def test_stronger_later_value_resolves_conflict(store):
    store.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    store.set_state("alice.employer", "OpenAI", authority=0.3, valid_from=d("2025-01-01"))
    weak = store.set_state("alice.employer", "Meta", authority=0.3, valid_from=d("2025-06-01"))
    assert weak.outcome == "conflict"                     # still not entitled to win
    r = store.set_state("alice.employer", "OpenAI", source="email from Alice",
                        valid_from=d("2026-01-01"))
    assert r.outcome == "changed"
    # Meta (later, as strong as OpenAI) ended OpenAI; only Anthropic and Meta
    # were still simultaneously plausible (0.9.0 wrongly kept OpenAI too).
    assert set(r.resolved_conflict) == {"Anthropic", "Meta"}
    assert store.get_state("alice.employer") == "OpenAI"
    assert store.contradictions() == []
    assert [s for s, _ in values(store)] == ["current"] + ["previous"] * 3


# 4b. simultaneous disagreement ends the value before it (fixed in 0.9.1)
def test_simultaneous_new_values_end_the_earlier_value(store):
    store.set_state("account.plan", "Free", source="signup", valid_from=d("2026-01-05"))
    store.set_state("account.plan", "Enterprise", source="billing", valid_from=d("2026-09-01"))
    r = store.set_state("account.plan", "Pro", source="crm", valid_from=d("2026-09-01"))
    assert r.outcome == "conflict"
    with pytest.raises(StateConflict) as exc:
        store.get_state("account.plan")
    assert sorted(e.value for e in exc.value.entries) == ["Enterprise", "Pro"]
    hist = {e.value: e for e in store.state_history("account.plan")}
    assert hist["Free"].status == "previous"
    assert hist["Free"].valid_to == d("2026-09-01")
    assert set(hist["Enterprise"].conflicts_with) == {"Pro"}
    assert store.get_state("account.plan", as_of=d("2026-06-01")) == "Free"
    [cluster] = store.contradictions()
    assert sorted(m.content for m in cluster) == ["Enterprise", "Pro"]


# 4c. ... but weaker simultaneous claims can't silently end a stronger value
def test_weaker_simultaneous_claims_do_not_end_a_stronger_value(store):
    store.set_state("account.plan", "Free", source="billing", valid_from=d("2026-01-05"))
    store.set_state("account.plan", "Enterprise", source="agent", authority=0.4,
                    valid_from=d("2026-09-01"))
    store.set_state("account.plan", "Pro", source="crm", authority=0.4,
                    valid_from=d("2026-09-01"))
    with pytest.raises(StateConflict) as exc:
        store.get_state("account.plan")
    assert sorted(e.value for e in exc.value.entries) == ["Enterprise", "Free", "Pro"]
    # a mixed epoch ends only what it is at least as strong as
    store.set_state("team.lead", "Ana", source="hr", valid_from=d("2026-01-01"))
    store.set_state("team.lead", "Bo", source="wiki", authority=0.5, valid_from=d("2026-03-01"))
    store.set_state("team.lead", "Cy", source="slack", authority=0.7, valid_from=d("2026-06-01"))
    with pytest.raises(StateConflict) as exc:
        store.get_state("team.lead")
    assert sorted(e.value for e in exc.value.entries) == ["Ana", "Cy"]   # Cy ended Bo, not Ana


# 7. the event log replays to exactly the stored state
def test_state_changes_replay_exactly(store):
    store.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    store.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    store.set_state("alice.employer", "Google", valid_from=d("2022-06-01"))
    store.set_state("alice.employer", "Anthropic", source="email")
    store.set_state("alice.employer", "Meta", authority=0.2)
    store.set_state("alice.employer", "Anthropic", source="hr", valid_to=d("2099-01-01"))
    replayed = store.replay()
    stored = {m.id: m.to_dict() for m in store.all(include_superseded=True)}
    assert {i: m.to_dict() for i, m in replayed.items()} == stored


# 8. keys are case-insensitive; states work under every profile
@pytest.mark.parametrize("profile", sorted(BUILTIN_PROFILES))
def test_states_under_every_profile(profile):
    mem = AgentMemory(profile=profile)
    mem.set("Alice.Employer", " OpenAI ", valid_from=d("2021-01-01"))
    mem.set("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    assert mem.get("ALICE.EMPLOYER") == "Anthropic"
    assert [e.value for e in mem.history("alice.employer")] == ["Anthropic", "OpenAI"]
    mem.recall("where does Alice work")   # decay/retrieval must accept the state type


# ── edges the rules imply ────────────────────────────────────────────────
def test_unset_expired_and_scheduled(store):
    assert store.get_state("alice.employer") is None
    assert store.state_history("alice.employer") == []
    store.set_state("alice.city", "Tokyo", valid_from=d("2020-01-01"), valid_to=d("2023-01-01"))
    assert store.get_state("alice.city") is None                    # ended
    assert store.get_state("alice.city", as_of=d("2022-01-01")) == "Tokyo"
    future = datetime.now(timezone.utc) + timedelta(days=30)
    store.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    r = store.set_state("alice.employer", "Anthropic", valid_from=future)
    assert (r.outcome, r.current) == ("scheduled", "OpenAI")
    assert values(store) == [("scheduled", "Anthropic"), ("current", "OpenAI")]
    assert store.get_state("alice.employer", as_of=future) == "Anthropic"


def test_states_are_isolated_by_workspace_and_key(store):
    store.set_state("alice.employer", "OpenAI", workspace="a")
    store.set_state("alice.employer", "Anthropic", workspace="b")
    store.set_state("bob.employer", "Google", workspace="a")
    assert store.get_state("alice.employer", workspace="a") == "OpenAI"
    assert store.get_state("alice.employer", workspace="b") == "Anthropic"
    assert store.get_state("bob.employer", workspace="a") == "Google"


def test_state_memories_only_through_set(store):
    with pytest.raises(ValueError, match="set_state"):
        store.add(Memory(type="state", content="OpenAI", subject="alice.employer"))
    with pytest.raises(ValueError):
        store.set_state("  ", "x")
    with pytest.raises(ValueError):
        store.set_state("alice.employer", "")


def test_policy_engine_knows_state_under_profiles():
    for name in BUILTIN_PROFILES:
        engine = PolicyEngine.from_profile(DomainProfile.builtin(name))
        assert engine.policy_for("state").half_life_days is None


@pytest.mark.parametrize("name", ["m.jsonl", "m.db"])
def test_state_survives_reopen(tmp_path, name):
    cls = JSONLMemoryStore if name.endswith("jsonl") else SQLiteMemoryStore
    s = cls(tmp_path / name)
    s.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    s.set_state("alice.employer", "Anthropic", valid_from=d("2024-01-01"))
    s.set_state("alice.employer", "Meta", authority=0.3, valid_from=d("2025-01-01"))
    before = [e.to_dict() for e in s.state_history("alice.employer")]
    s.close()
    s = cls(tmp_path / name)
    assert [e.to_dict() for e in s.state_history("alice.employer")] == before
    with pytest.raises(StateConflict):
        s.get_state("alice.employer")
    assert len(s.contradictions()) == 1
    assert len(s.replay()) == 3
    s.close()


@pytest.mark.xfail(strict=True, reason=(
    "known issue (design 0002): list/all() read the superseded_by index, which is "
    "written as of the last set; get/history resolve as of now"))
def test_list_agrees_with_get_after_a_scheduled_value_takes_effect():
    import time
    store = InMemoryStore()
    store.set_state("alice.employer", "OpenAI", valid_from=d("2021-01-01"))
    store.set_state("alice.employer", "Anthropic",
                    valid_from=datetime.now(timezone.utc) + timedelta(milliseconds=30))
    time.sleep(0.06)
    assert store.get_state("alice.employer") == "Anthropic"
    assert [m.content for m in store.all()] == ["Anthropic"]


def test_set_reports_confirming_a_historical_value(tmp_path, capsys):   # issue #9
    from typedmem.cli import main
    db = ["--store", str(tmp_path / "m.db")]
    main(db + ["set", "account.plan", "Pro", "--valid-from", "2026-04-01", "--source", "billing"])
    main(db + ["set", "account.plan", "Enterprise", "--valid-from", "2026-09-01", "--source", "billing"])
    capsys.readouterr()
    main(db + ["set", "account.plan", "Pro", "--valid-from", "2026-04-01", "--source", "support ticket"])
    assert capsys.readouterr().out.strip() == (
        "account.plan: added source to historical value Pro (from 2026-04-01); current is Enterprise")
    main(db + ["set", "account.plan", "Pro", "--valid-from", "2026-04-01", "--source", "support ticket"])
    assert capsys.readouterr().out.strip() == (
        "account.plan: Pro (from 2026-04-01) is already recorded as a historical value; current is Enterprise")
    main(db + ["set", "account.plan", "Enterprise", "--valid-from", "2026-09-01", "--source", "crm"])
    assert capsys.readouterr().out.strip() == "account.plan = Enterprise  (unchanged; source added)"
    main(db + ["set", "account.plan", "Enterprise", "--valid-from", "2026-09-01", "--source", "crm"])
    assert capsys.readouterr().out.strip() == "account.plan = Enterprise  (unchanged)"


def test_set_result_says_whether_a_source_was_added():
    store = InMemoryStore()
    store.set_state("k", "v", source="a")
    assert store.set_state("k", "v", source="b").source_added is True
    assert store.set_state("k", "v", source="b").source_added is False
