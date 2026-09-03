"""Unit tests for Stage 7 LLM explanation layer (PRD Sec 4, Sec 7 build step 10).

Every test here mocks the LLM client - no network dependency in CI, per
CLAUDE.md's demo-reliability requirement. A separate manual smoke test (not a
pytest, see docs/build-log.md) confirms the real OpenRouter integration.
"""

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from pipeline.allocator import allocate
from pipeline.classify import classify_cause
from pipeline.decision import run_decision
from pipeline.explain import generate_explanation, run_explanation
from pipeline.models import RazorpayError
from pipeline.priors import get_prior

IST = ZoneInfo("Asia/Kolkata")


def _sample_decision():
    error = RazorpayError(reason="insufficient_funds", description="not enough funds")
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0)
    decision, _ = run_decision("pay_1", "token_1", 50000, error, classification, prior, allocation)
    return decision


def _mock_client(content: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    client.chat.completions.create.return_value = response
    return client


def test_successful_llm_response_is_parsed() -> None:
    content = (
        '{"reasoning_plain": "We will retry once your account is likely funded.", '
        '"notification_copy_en": "We will try your payment again soon.", '
        '"notification_copy_hinglish": "Aapka payment phir se try hoga."}'
    )
    result = generate_explanation(_sample_decision(), client=_mock_client(content))
    assert result.generated_by == "llm"
    assert result.reasoning_plain == "We will retry once your account is likely funded."
    assert "Aapka" in result.notification_copy_hinglish


def test_llm_response_wrapped_in_markdown_fence_is_parsed() -> None:
    content = (
        '```json\n{"reasoning_plain": "x", "notification_copy_en": "y", "notification_copy_hinglish": "z"}\n```'
    )
    result = generate_explanation(_sample_decision(), client=_mock_client(content))
    assert result.generated_by == "llm"
    assert result.reasoning_plain == "x"


def test_malformed_json_falls_back_to_template() -> None:
    result = generate_explanation(_sample_decision(), client=_mock_client("not json at all"))
    assert result.generated_by == "template_fallback"
    assert result.reasoning_plain != ""


def test_missing_required_key_falls_back_to_template() -> None:
    content = '{"reasoning_plain": "x", "notification_copy_en": "y"}'  # missing hinglish key
    result = generate_explanation(_sample_decision(), client=_mock_client(content))
    assert result.generated_by == "template_fallback"


def test_empty_string_value_falls_back_to_template() -> None:
    content = '{"reasoning_plain": "", "notification_copy_en": "y", "notification_copy_hinglish": "z"}'
    result = generate_explanation(_sample_decision(), client=_mock_client(content))
    assert result.generated_by == "template_fallback"


def test_client_raising_an_exception_falls_back_to_template() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = ConnectionError("provider unreachable")
    result = generate_explanation(_sample_decision(), client=client)
    assert result.generated_by == "template_fallback"
    assert result.reasoning_plain != ""
    assert result.notification_copy_en != ""
    assert result.notification_copy_hinglish != ""


def test_fallback_is_deterministic_for_the_same_decision() -> None:
    decision = _sample_decision()
    client = MagicMock()
    client.chat.completions.create.side_effect = TimeoutError("slow provider")
    a = generate_explanation(decision, client=client)
    b = generate_explanation(decision, client=client)
    assert a == b


def test_run_explanation_returns_stage_trace() -> None:
    result, trace = run_explanation(_sample_decision(), client=_mock_client("bad json"))
    assert trace.stage == "explain"
    assert result.generated_by == "template_fallback"
    assert "generated_by=template_fallback" in trace.output_summary
