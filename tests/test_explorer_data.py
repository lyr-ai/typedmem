"""The Temporal Truth Explorer draws only what TypedMem answers (design 0003
§13). Regenerating its data from the real API must reproduce the committed
docs/explorer/data.js exactly. If this fails, the product and the explorer
disagree: rerun `python tools/explorer_data.py` and look at what changed."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    spec = importlib.util.spec_from_file_location("explorer_data", ROOT / "tools" / "explorer_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_explorer_data_matches_the_product():
    committed = (ROOT / "docs" / "explorer" / "data.js").read_text()
    assert load_generator().build() == committed


def test_explorer_scenarios_say_what_design_0003_promises():
    import json
    text = load_generator().build()
    data = {s["key"]: s for s in json.loads(text[text.index("{"):text.rindex("}") + 1])["scenarios"]}
    change, late, conflict = data["change"], data["late"], data["conflict"]
    assert change["final"]["current"] == "Enterprise"
    assert [h["value"] for h in change["final"]["history"]] == ["Enterprise", "Pro", "Free"]
    # arrived last, wasn't true last
    assert late["steps"][-1]["value"] == "Pro" and late["steps"][-1]["outcome"] == "past"
    assert late["final"]["current"] == "Enterprise"
    # no winner when get() raises StateConflict; the earlier value is history
    assert conflict["final"]["current"] is None
    assert conflict["final"]["conflict"] == ["Enterprise", "Pro"]
    assert {h["value"]: h["status"] for h in conflict["final"]["history"]}["Free"] == "previous"


def test_a_version_bump_alone_does_not_change_the_data(monkeypatch):
    import typedmem
    gen = load_generator()
    before = gen.build()
    monkeypatch.setattr(typedmem, "__version__", "99.0.0")
    assert gen.build() == before
