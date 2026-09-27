"""The README is a contract: every code block marked ``<!-- contract -->`` runs
against a fresh store, and its real output must match the README.

- ``console`` blocks: each ``$ typedmem ...`` line is run through the CLI;
  the lines after it, up to the next ``$``, are its expected output (stdout
  and stderr). ``$ pip ...`` lines are skipped.
- ``python`` blocks are executed. A line ending in ``# <literal>`` asserts
  that the expression on it evaluates to that literal.

The only normalisation: today's date in the actual output is replaced by the
date the README shows for "now", so the README doesn't go stale each day.
Every other date is compared exactly.
"""

import ast
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

import pytest

from typedmem.cli import main

README = Path(__file__).resolve().parents[1] / "README.md"
README_TODAY = "2026-09-27"
BLOCK = re.compile(r"<!-- contract[^>]*-->\s*```(\w+)\n(.*?)```", re.S)


def blocks():
    found = BLOCK.findall(README.read_text())
    assert found, "README has no contract blocks"
    return [pytest.param(lang, body, id=f"{i}-{lang}") for i, (lang, body) in enumerate(found)]


def steps(body: str):
    """[(argv, expected_output)] for a console block."""
    out, cmd, expect = [], None, []
    for line in body.splitlines():
        if line.startswith("$ "):
            if cmd is not None:
                out.append((cmd, "\n".join(expect).strip("\n")))
            cmd, expect = line[2:], []
        elif cmd is not None:
            expect.append(line.rstrip())
    if cmd is not None:
        out.append((cmd, "\n".join(expect).strip("\n")))
    return [(shlex.split(c, comments=True), e) for c, e in out]


@pytest.mark.parametrize("lang,body", blocks())
def test_readme_block(lang, body, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    today = datetime.now(timezone.utc).date().isoformat()
    if lang == "console":
        ran = 0
        for argv, expected in steps(body):
            if argv[0] == "pip":
                continue
            assert argv[0] == "typedmem", argv
            main(["--store", str(tmp_path / "readme.db"), *argv[1:]])
            cap = capsys.readouterr()
            actual = "\n".join(l.rstrip() for l in (cap.out + cap.err).splitlines())
            assert actual.replace(today, README_TODAY) == expected, " ".join(argv)
            ran += 1
        assert ran
    elif lang == "python":
        ns: dict = {}
        for line in body.splitlines():
            code, _, comment = line.partition("#")
            if comment.strip() and code.strip():
                assert eval(code, ns) == ast.literal_eval(comment.strip()), line
            elif code.strip():
                exec(code, ns)
    else:
        pytest.fail(f"unsupported contract block language: {lang}")
