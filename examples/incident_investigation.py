"""An agent investigating a production incident: what happens to memory as
new information arrives.

The agent decides what new information means (which type and subject it
files it under). TypedMem governs what happens to memory next: reinforcement,
conflict, supersession, and a replayable history of every change.

TypedMem records how memory changed, not why the agent reasoned from one memory
to another. If an application needs decision rationale ("decision D was made
because of evidence E"), it must record those links explicitly.
"""
from typedmem import Memory
from typedmem.policy import ConflictPolicy, PolicyEngine
from typedmem.profiles.base import DomainProfile, TypeSpec
from typedmem.source import Source
from typedmem.stores.memory import InMemoryStore

# The agent's filing decision matters: TypedMem doesn't read content. Records
# with the same type and subject share a slot, and the type's policy decides.
# A contradicting statement filed as `evidence` on the same subject would be
# merged in as reinforcement.
profile = DomainProfile(name="incident", types={
    "evidence":   TypeSpec("evidence",   conflict_policy=ConflictPolicy.REINFORCE),
    "assessment": TypeSpec("assessment", conflict_policy=ConflictPolicy.FLAG),
    "decision":   TypeSpec("decision",   conflict_policy=ConflictPolicy.SUPERSEDE),
})
store = InMemoryStore(policy=PolicyEngine.from_profile(profile), profile=profile)


def add(type, subject, content, source, confidence=1.0):
    return store.add(Memory(type=type, subject=subject, content=content,
                            confidence=confidence, sources=[Source(source)]))


# ── Track 1: claims and evidence ──────────────────────────────────────────
print("CLAIMS AND EVIDENCE")
e = add("evidence", "logging.cert_errors",
        "Certificate errors are associated with logging failures", "runtime_telemetry", 0.6)
e = add("evidence", "logging.cert_errors",
        "Support cases report certificate-related connection errors", "support_cases", 0.6)
e = store.get(e.id)
print(f"  one record, {len(e.sources)} sources: {[s.document_id for s in e.sources]}, "
      f"confidence {e.confidence:.2f}")

a1 = add("assessment", "logging.certificate", "The certificate is causing client failures", "agent")
a2 = add("assessment", "logging.certificate", "The certificate is valid", "cert_validation")
print("  conflict, both kept:", [sorted(m.content for m in g) for g in store.contradictions()])
print("  still unresolved:", bool(store.get(a1.id).metadata.get("conflicts_with")))

# ── Track 2: the investigation decision ───────────────────────────────────
print("\nINVESTIGATION DECISION")
d1 = add("decision", "logging.investigation_path", "Investigate certificate failure", "agent")
add("evidence", "logging.connectivity",
    "Failures correlate with loss of connectivity to the logging service", "runtime_telemetry", 0.8)
d2 = add("decision", "logging.investigation_path", "Investigate logging-service connectivity", "agent")
print("  current:", [m.content for m in store.all() if m.type == "decision"])
print("  kept as history:", store.get(d1.id).content, "-> superseded by the new decision:",
      store.get(d1.id).superseded_by == d2.id)

# ── How did the investigation memory change? (event order, not causes) ───
print("\nHOW THE INVESTIGATION MEMORY CHANGED")
for i, ev in enumerate(store.timeline(), 1):
    print(f"  {i}. {ev.action:11} {ev.type:10} {ev.subject}")

# ── Replay: the state at any point, rebuilt from the log ──────────────────
from typedmem.replay import replay
events = store.timeline()
print("\nREPLAY")
print("  full log rebuilds the current state:",
      {k: v.content for k, v in store.replay().items()} ==
      {m.id: m.content for m in store.all(include_superseded=True)})
before = next(i for i, ev in enumerate(events) if ev.action == "superseded")
past = replay(events[:before])
print("  before the revision, the decision was:",
      [m.content for m in past.values() if m.type == "decision" and not m.superseded_by])
