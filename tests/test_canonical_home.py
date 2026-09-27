"""TypedMem lives at github.com/lyr-ai/typedmem. No file may point at the old
home, so a stale link can't hide deep in the docs.

Allowed: CHANGELOG.md, which records where past releases were published."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_OWNER = "canis" + "-minor"          # split so this file doesn't match itself
ALLOWED = {"CHANGELOG.md"}
SKIP_DIRS = {".git", ".venv", "venv", "build", "dist", "node_modules", "__pycache__",
             ".pytest_cache", "site"}


def files():
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if p.is_dir() or any(part in SKIP_DIRS or part.endswith(".egg-info")
                             for part in rel.parts):
            continue
        yield rel, p


def test_no_references_to_the_old_home():
    stale = []
    for rel, p in files():
        if str(rel) in ALLOWED:
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        stale += [f"{rel}:{i}" for i, line in enumerate(text.splitlines(), 1)
                  if OLD_OWNER in line.lower()]
    assert not stale, f"references to the old home ({OLD_OWNER}): {stale}"
