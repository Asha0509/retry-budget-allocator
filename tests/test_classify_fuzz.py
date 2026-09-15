"""Property-based fuzzing of Stage 2 classification (PRD Sec 4) - Part C2.

Supplements the manual fail-open audit (docs/build-log.md, 2026-09-14) with
hypothesis generating hundreds of malformed/unrecognised error payloads,
rather than a handful of hand-picked cases. The invariant under test: when
classification genuinely can't place a cause, the system must fail toward
the safer of its three real actions.

This system has three actions, not two - notify, retry, stop - and the safe
answer for "recognised nothing" is specifically NOTIFY, not either of the
other two:
  - Not RETRY: spending one of 3 non-renewable NPCI attempts on a cause the
    classifier couldn't even place would be gambling the budget blind.
  - Not STOP: silently giving up abandons a payment whose true
    recoverability is genuinely unknown - it might have been fixable, and
    the customer would never find out something needs their attention.
  - NOTIFY costs zero retry attempts and tells the customer something needs
    action, without asserting a recoverability verdict the classifier
    doesn't actually have evidence for.

pipeline.priors.get_prior(FailureCause.UNKNOWN) already encodes this
(action_shape="notify") - this test proves it holds for a wide, generated
space of unrecognised inputs, not just the one hand-written fixture.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.classify import classify_cause
from pipeline.models import RazorpayError
from pipeline.priors import get_prior

# None or arbitrary text (including empty, unicode, control chars, very
# long strings) - the full space of what a malformed/unrecognised/missing
# reason or description field could contain.
_maybe_text = st.one_of(st.none(), st.text(max_size=500))


@given(reason=_maybe_text, description=_maybe_text, code=_maybe_text)
@settings(max_examples=500)
def test_unrecognized_input_never_reads_as_permission_to_retry_or_as_terminal_stop(
    reason: str | None, description: str | None, code: str | None
) -> None:
    error = RazorpayError(reason=reason, description=description, code=code)
    result = classify_cause(error)
    prior = get_prior(result.cause)

    if result.confidence == 0.0:
        # Genuinely unrecognized (no reason match, no description-keyword
        # match) - must fail toward notify, never retry or stop.
        assert prior.action_shape == "notify", (
            f"unrecognized input classified as {result.cause} produced "
            f"action_shape={prior.action_shape!r}, not 'notify'"
        )


@given(reason=_maybe_text, description=_maybe_text, code=_maybe_text)
@settings(max_examples=500)
def test_classification_never_raises_on_arbitrary_text_input(
    reason: str | None, description: str | None, code: str | None
) -> None:
    # No-crash property: classify_cause must handle any string/None
    # combination without an exception - a money-path stage raising on
    # unexpected but validly-typed input is its own kind of failure.
    error = RazorpayError(reason=reason, description=description, code=code)
    classify_cause(error)


@given(reason=st.text(max_size=500), description=st.text(max_size=500))
@settings(max_examples=200)
def test_confidence_is_always_one_of_three_declared_values(reason: str, description: str) -> None:
    # This classifier is deterministic lookup, never inference - confidence
    # should only ever be one of the three values the code actually
    # assigns (1.0 exact match, 0.6 keyword fallback, 0.0 no match), never
    # some other value a bug could produce.
    error = RazorpayError(reason=reason, description=description)
    result = classify_cause(error)
    assert result.confidence in (0.0, 0.6, 1.0)
