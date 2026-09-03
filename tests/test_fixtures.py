"""Sanity check: every captured fixture (PRD Sec 5.0) classifies as its filename claims.

This is exactly what Sec 5.0 asks step 3 to surface before the batch
generator is written - a real mismatch here would mean classify.py's rules
don't actually match the schema Sec 5.0 requires the batch to replay.
"""

import json
from pathlib import Path

import pytest

from pipeline.classify import classify_cause
from pipeline.models import FailureCause, RazorpayError

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
FIXTURE_FILES = sorted(p for p in FIXTURES_DIR.glob("*.json") if not p.name.startswith("_"))


@pytest.mark.parametrize("fixture_path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixture_classifies_as_its_filename(fixture_path: Path) -> None:
    data = json.loads(fixture_path.read_text())
    data.pop("_fixture_source", None)
    error = RazorpayError(**data)
    result = classify_cause(error)
    assert result.cause == FailureCause(fixture_path.stem)


def test_every_failure_cause_has_a_fixture() -> None:
    covered = {p.stem for p in FIXTURE_FILES}
    assert covered == {c.value for c in FailureCause}
