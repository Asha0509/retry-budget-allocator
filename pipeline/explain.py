"""Stage 7 - LLM explanation layer (PRD Sec 4).

The only place in this codebase an LLM is called. Generates the
plain-language `reasoning_plain` string and customer-facing notification
copy (English + Hinglish, per Track 3's listed direction) from an
ALREADY-DECIDED RecoveryDecision. Never decides whether to retry, when to
retry, or whether to stop - the decision passed in is final. Kept off the
critical path: any failure (network, auth, malformed response) falls back to
a deterministic template so a provider outage degrades explanation quality,
not pipeline execution (CLAUDE.md hard constraint).

Model/endpoint/key are read from .env (EXPLANATION_MODEL, LLM_BASE_URL,
LLM_API_KEY) so a rate-limited free-tier provider can be swapped without a
code change.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from pipeline.decision import RecoveryDecision, _template_reasoning_plain
from pipeline.models import Action, StageTrace, run_stage

# Explicit path, not a bare load_dotenv() upward search - on a slow
# filesystem (e.g. WSL's /mnt/c) that search is a real, measurable delay.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = logging.getLogger("pipeline.explain")

_SYSTEM_PROMPT = (
    "You write short, plain-language explanations of automated payment-retry decisions, "
    "for two audiences at once: a compliance officer auditing the decision, and the customer "
    "being notified. Never use jargon like NPCI, mandate, or AutoPay without plain words first. "
    "Be concise - one or two sentences per field. Respond with ONLY a JSON object, no markdown fences, "
    'no commentary, with exactly these string keys: "reasoning_plain", "notification_copy_en", '
    '"notification_copy_hinglish" (the English message rewritten in Hinglish - Hindi-English '
    "code-mixed, the way Indian customers commonly write SMS/WhatsApp messages)."
)

_TEMPLATE_NOTIFICATION_EN: dict[Action, str] = {
    "retry": "We'll automatically retry your payment soon - no action is needed from you right now.",
    "notify": "Your payment needs your attention - please check your payment method to avoid it failing again.",
    "stop": "We couldn't process your payment automatically. Please set up your payment method again.",
}
_TEMPLATE_NOTIFICATION_HINGLISH: dict[Action, str] = {
    "retry": "Aapka payment thodi der mein phir se try hoga - abhi kuch karne ki zaroorat nahi hai.",
    "notify": "Aapke payment mein thodi dikkat hai - please apna payment method check kar lijiye.",
    "stop": "Hum aapka payment process nahi kar paaye. Please apna payment method dobara set up karein.",
}


class ExplanationResult(BaseModel):
    reasoning_plain: str
    notification_copy_en: str
    notification_copy_hinglish: str
    generated_by: str  # "llm" or "template_fallback"


def _client() -> OpenAI:
    return OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])


def _model() -> str:
    return os.environ.get("EXPLANATION_MODEL", "z-ai/glm-4.7-flash:free")


def _prompt_for(decision: RecoveryDecision) -> str:
    schedule_note = f", scheduled at {decision.scheduled_at}." if decision.scheduled_at else "."
    return (
        f"Payment {decision.payment_id} for INR {decision.amount / 100:.2f} failed. "
        f"Cause: {decision.cause.value} (classifier confidence {decision.cause_confidence}). "
        f"Decision: {decision.action}{schedule_note} "
        f"Technical reasoning: {decision.reasoning_technical}"
    )


def _parse_json_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    data = json.loads(text)
    for key in ("reasoning_plain", "notification_copy_en", "notification_copy_hinglish"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"LLM response missing or empty key {key!r}")
    return data


def _fallback_explanation(decision: RecoveryDecision) -> ExplanationResult:
    return ExplanationResult(
        reasoning_plain=_template_reasoning_plain(decision.cause, decision.action),
        notification_copy_en=_TEMPLATE_NOTIFICATION_EN[decision.action],
        notification_copy_hinglish=_TEMPLATE_NOTIFICATION_HINGLISH[decision.action],
        generated_by="template_fallback",
    )


def generate_explanation(decision: RecoveryDecision, client: OpenAI | None = None) -> ExplanationResult:
    """Stage 7: generate plain-language reasoning + notification copy (PRD Sec 4).

    `client` is injectable for testing without a network dependency; defaults
    to a real OpenRouter-backed client built from .env.
    """
    try:
        active_client = client or _client()
        response = active_client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _prompt_for(decision)},
            ],
            temperature=0.3,
            max_tokens=1000,  # some free-tier models spend real tokens "reasoning" before the JSON answer
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty content (response may have been truncated - see finish_reason)")
        parsed = _parse_json_response(content)
        return ExplanationResult(
            reasoning_plain=parsed["reasoning_plain"],
            notification_copy_en=parsed["notification_copy_en"],
            notification_copy_hinglish=parsed["notification_copy_hinglish"],
            generated_by="llm",
        )
    except Exception as exc:  # noqa: BLE001 - any LLM/network/parsing failure must degrade to a template, never crash the pipeline
        log.error("LLM explanation failed for %s, falling back to template: %s", decision.payment_id, exc)
        return _fallback_explanation(decision)


def run_explanation(decision: RecoveryDecision, client: OpenAI | None = None) -> tuple[ExplanationResult, StageTrace]:
    """Stage 7 entry point: explain and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"payment_id={decision.payment_id!r} action={decision.action}"

    def _work() -> tuple[ExplanationResult, str]:
        result = generate_explanation(decision, client)
        return result, f"generated_by={result.generated_by}"

    return run_stage("explain", input_summary, _work)
