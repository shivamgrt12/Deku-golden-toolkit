import shutil
import sys
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOLDEN / "lib"))

REFERENCE = GOLDEN.parent / "genkit" / "reference-tasks" / "1b21d4ac-055a-52e7-b754-0620f337b0d4"

STUB_SOLVE = """#!/usr/bin/env bash
echo "solve.sh: MECHANICALLY-GREEN, NO-SOLUTION -- no reference app yet" >&2
exit 1
"""


@pytest.fixture
def reference(tmp_path):
    """A private copy of the verified reference task (its app scored oracle 1.0).

    The exemplar predates genkit's [metadata.services] table (it carries only
    service_profile = "P1-db"), and the current harness selects adapters from it.
    The copy is brought up to the current contract; G0 catches the original
    shape (test_g0_catches_an_undeclared_slot).
    """
    dest = tmp_path / "reference"
    shutil.copytree(REFERENCE, dest, ignore=shutil.ignore_patterns("_handoff"))
    toml = dest / "task.toml"
    toml.write_text(toml.read_text().rstrip("\n") + '\n\n[metadata.services]\nbackend = "postgres"\n')
    return dest


@pytest.fixture
def unsolved(reference):
    """The same bundle in the state genkit hands over: no app, stub solve.sh."""
    shutil.rmtree(reference / "solution" / "app")
    (reference / "solution" / "solve.sh").write_text(STUB_SOLVE)
    return reference
