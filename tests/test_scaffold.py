"""Placeholder so CI passes on the scaffold commit.

Replace with the compliance invariant tests (PRD Sec 7, build order step 2):
  - never more than 3 retry attempts per mandate
  - never schedule inside a peak window (10:00-13:00, 17:00-21:30)
  - never more than one successful debit per token per billing cycle
"""


def test_scaffold_imports():
    import pipeline  # noqa: F401
