"""Enforces PRD Sec 5.1's hard constraint mechanically: the allocator (or any
pipeline stage) must never import eval.outcome_model - otherwise evaluating
the allocator against that model would be circular. A convention-only rule
rots; this greps the actual source.
"""

import ast
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"


def _imports_outcome_model(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any("outcome_model" in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "outcome_model" in module or any(alias.name == "outcome_model" for alias in node.names):
                return True
    return False


def test_pipeline_never_imports_outcome_model() -> None:
    offenders = [str(p) for p in PIPELINE_DIR.glob("*.py") if _imports_outcome_model(p)]
    assert offenders == [], f"pipeline/ must never import eval.outcome_model (Sec 5.1): {offenders}"
