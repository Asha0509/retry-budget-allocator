"""Faithfulness eval for the Stage 7 explanation layer (PRD Sec 4 Stage 7, Sec 6.4).

Stage 7 is the only place a model writes anything, so it is the one output
that can state something the decision record doesn't support. Every check
here is a deterministic rule over (decision, explanation) - no model grades
another model - so a failure points at a specific sentence and a specific
rule:

  action_matches      the copy describes the action that was decided (a stop
                      never promises a retry; a retry says it will try again)
  amounts_match       any rupee amount mentioned equals the decision's amount
  times_match         any clock time or date mentioned matches scheduled_at
  no_customer_jargon  notifications avoid NPCI / mandate / AutoPay / error codes
  jargon_explained    reasoning_plain only uses those terms inside brackets,
                      after the plain words (PRD Sec 6 presentation rule)
  no_internal_leak    no payment/token ids, scores or window labels
  sms_length          each notification fits one 160-character SMS
  hinglish_present    the Hinglish copy is Hindi-English, not the English again

Sources:
  template  every allocator decision in the run, explained by the
            deterministic fallback (no network; what ships when the model is down)
  cached    the explanations cached in the run artifact (PRD Sec 6.2)
  llm       fresh model output for one decision per (cause, action) - needs
            LIVE_LLM=1 plus LLM_BASE_URL / LLM_API_KEY, and refuses otherwise

  python -m eval.explanation_eval --source template
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.decision import RecoveryDecision
from pipeline.explain import (
    ExplanationResult,
    _fallback_explanation,
    generate_explanation,
)

log = logging.getLogger("eval.explanation_eval")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
LOGS_DIR = ROOT / "logs"
IST = ZoneInfo("Asia/Kolkata")
SMS_LIMIT = 160

_JARGON = re.compile(r"\b(npci|mandates?|e-mandate|auto-?pay|token|gateway|peak window)\b", re.IGNORECASE)
_ERROR_CODE = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b")
_SNAKE_CASE = re.compile(r"\b[a-z]+_[a-z_]+\b")
_AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b", re.IGNORECASE)
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_DATE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})[a-z]*\b|\b({_MONTHS})[a-z]*\.?\s+(\d{{1,2}})\b", re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_WINDOW_LABEL = re.compile(r"\b\d+h(?:_shifted)?\b")
_RETRY_EN = re.compile(r"\b(retry|retried|try (?:it |this |your payment |the payment )?again|another attempt|attempt (?:it|the payment) again)\b", re.IGNORECASE)
_RETRY_PROMISE = re.compile(r"\b(?:we(?:'ll| will)|will)\s+(?:automatically\s+)?(?:retry|try (?:it |this |your payment |the payment )?again)\b|\bautomatically retry\b", re.IGNORECASE)
_CALL_TO_ACTION = re.compile(r"\b(please|update|check|approve|set up|contact|add|top up|authori[sz]e|confirm)\b", re.IGNORECASE)
_RETRY_HI = re.compile(r"\b(phir se|dobara try|retry|try hoga|try karenge|try kiya jayega)\b", re.IGNORECASE)
_HINDI_WORDS = {"hai", "hain", "aap", "aapka", "aapke", "aapki", "kar", "karein", "kijiye", "nahi", "ho", "hoga",
                "mein", "ki", "ka", "ke", "phir", "dobara", "abhi", "zaroorat", "thodi", "paaye", "hum", "apna", "chuka"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _customer_texts(exp: ExplanationResult) -> dict[str, str]:
    return {"notification_copy_en": exp.notification_copy_en, "notification_copy_hinglish": exp.notification_copy_hinglish}


def _all_texts(exp: ExplanationResult) -> dict[str, str]:
    return {"reasoning_plain": exp.reasoning_plain, **_customer_texts(exp)}


def check_action(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """The copy must describe the decided action, never a different one."""
    en = f"{exp.reasoning_plain} {exp.notification_copy_en}"
    if decision.action == "retry":
        if not _RETRY_EN.search(en):
            return Check("action_matches", False, "retry decided, but the English copy never says it will try again")
        if not _RETRY_HI.search(exp.notification_copy_hinglish):
            return Check("action_matches", False, "retry decided, but the Hinglish copy never says it will try again")
        return Check("action_matches", True)
    promise = _RETRY_PROMISE.search(f"{en} {exp.notification_copy_hinglish}")
    if promise:
        return Check("action_matches", False, f"{decision.action} decided, but the copy promises a retry: {promise.group(0)!r}")
    already_paid = decision.billing_cycle_successes >= 1
    if not already_paid and not _CALL_TO_ACTION.search(exp.notification_copy_en):
        return Check("action_matches", False, f"{decision.action} decided, but the customer is never asked to do anything")
    return Check("action_matches", True)


def check_amounts(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """Any rupee figure in any text must be the decision's own amount."""
    expected = decision.amount / 100
    for field, text in _all_texts(exp).items():
        for raw in _AMOUNT.findall(text):
            value = float(raw.replace(",", ""))
            if abs(value - expected) > 0.5:
                return Check("amounts_match", False, f"{field} mentions ₹{raw}, decision amount is ₹{expected:.2f}")
    return Check("amounts_match", True)


def _clock_minutes(match: re.Match) -> int:
    if match.group(3):
        hour = int(match.group(1)) % 12 + (12 if match.group(3).lower() == "pm" else 0)
        return hour * 60 + int(match.group(2) or 0)
    return int(match.group(4)) * 60 + int(match.group(5))


def _mentioned_dates(text: str) -> list[tuple[int, str]]:
    out = []
    for m in _DATE.finditer(text):
        day, month = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        out.append((int(day), month[:3].lower()))
    return out


def check_times(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """Clock times, dates and weekdays mentioned must match scheduled_at (IST); none allowed without one."""
    when = decision.scheduled_at.astimezone(IST) if decision.scheduled_at else None
    for field, text in _all_texts(exp).items():
        found = [m.group(0) for m in _CLOCK.finditer(text)] + [m.group(0) for m in _DATE.finditer(text)] + _WEEKDAY.findall(text)
        if found and when is None:
            return Check("times_match", False, f"{field} mentions {found[0]!r} but nothing is scheduled")
        if when is None:
            continue
        for m in _CLOCK.finditer(text):
            if _clock_minutes(m) != when.hour * 60 + when.minute:
                return Check("times_match", False, f"{field} says {m.group(0)!r}, scheduled for {when:%H:%M} IST")
        for day, month in _mentioned_dates(text):
            if (day, month) != (when.day, when.strftime("%b").lower()):
                return Check("times_match", False, f"{field} names {day} {month}, scheduled for {when:%d %b}")
        for weekday in _WEEKDAY.findall(text):
            if weekday.lower() != when.strftime("%A").lower():
                return Check("times_match", False, f"{field} says {weekday}, scheduled for a {when:%A}")
    return Check("times_match", True)


def check_customer_jargon(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """Customer notifications must be readable without payments vocabulary."""
    for field, text in _customer_texts(exp).items():
        for pattern in (_JARGON, _ERROR_CODE, _SNAKE_CASE):
            m = pattern.search(text)
            if m:
                return Check("no_customer_jargon", False, f"{field} uses {m.group(0)!r}")
    return Check("no_customer_jargon", True)


def check_jargon_explained(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """reasoning_plain may name NPCI/mandate/AutoPay only in brackets, after the plain words."""
    unbracketed = re.sub(r"\([^)]*\)", "", exp.reasoning_plain)
    for pattern in (_JARGON, _ERROR_CODE, _SNAKE_CASE):
        m = pattern.search(unbracketed)
        if m:
            return Check("jargon_explained", False, f"reasoning_plain uses {m.group(0)!r} without plain words first")
    return Check("jargon_explained", True)


def check_internal_leak(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """No identifiers or allocator internals in any text."""
    for field, text in _all_texts(exp).items():
        for needle in (decision.payment_id, decision.token_id):
            if needle and needle in text:
                return Check("no_internal_leak", False, f"{field} contains the id {needle!r}")
        m = _WINDOW_LABEL.search(text) or re.search(r"\b(score|confidence|recoverability)\b", text, re.IGNORECASE)
        if m:
            return Check("no_internal_leak", False, f"{field} exposes {m.group(0)!r}")
    return Check("no_internal_leak", True)


def check_sms_length(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """Each notification fits one SMS segment."""
    for field, text in _customer_texts(exp).items():
        if len(text) > SMS_LIMIT:
            return Check("sms_length", False, f"{field} is {len(text)} characters (limit {SMS_LIMIT})")
    return Check("sms_length", True)


def check_hinglish(decision: RecoveryDecision, exp: ExplanationResult) -> Check:
    """The Hinglish copy is code-mixed Hindi-English, not the English repeated."""
    words = set(re.findall(r"[a-z]+", exp.notification_copy_hinglish.lower()))
    if exp.notification_copy_hinglish.strip() == exp.notification_copy_en.strip():
        return Check("hinglish_present", False, "Hinglish copy is identical to the English copy")
    if len(words & _HINDI_WORDS) < 2:
        return Check("hinglish_present", False, "Hinglish copy has fewer than 2 common Hindi words")
    return Check("hinglish_present", True)


CHECKS: tuple[Callable[[RecoveryDecision, ExplanationResult], Check], ...] = (
    check_action, check_amounts, check_times, check_customer_jargon, check_jargon_explained,
    check_internal_leak, check_sms_length, check_hinglish,
)
CHECK_NAMES = ("action_matches", "amounts_match", "times_match", "no_customer_jargon", "jargon_explained",
               "no_internal_leak", "sms_length", "hinglish_present")


def evaluate_one(decision: RecoveryDecision, exp: ExplanationResult) -> dict:
    """Run every check on one explanation; returns a JSON-ready row."""
    checks = [c(decision, exp) for c in CHECKS]
    return {
        "payment_id": decision.payment_id,
        "cause": decision.cause.value,
        "action": decision.action,
        "attempts_used": decision.attempts_used,
        "generated_by": exp.generated_by,
        "passed": all(c.passed for c in checks),
        "failed_checks": [asdict(c) for c in checks if not c.passed],
        "texts": _all_texts(exp),
    }


def summarise(rows: list[dict]) -> dict:
    """Pass rates overall, per check and per action."""
    n = len(rows)
    per_check = {}
    for check_name in CHECK_NAMES:
        failed = sum(1 for r in rows if any(f["name"] == check_name for f in r["failed_checks"]))
        per_check[check_name] = {"failed": failed, "pass_rate": round(1 - failed / n, 4) if n else None}
    by_action: dict[str, dict] = {}
    for r in rows:
        a = by_action.setdefault(r["action"], {"n": 0, "passed": 0})
        a["n"] += 1
        a["passed"] += r["passed"]
    return {
        "n": n,
        "pass_rate": round(sum(r["passed"] for r in rows) / n, 4) if n else None,
        "per_check": per_check,
        "by_action": by_action,
    }


def _decisions(run: dict) -> list[tuple[dict, RecoveryDecision]]:
    return [(p, RecoveryDecision(**d)) for p in run["payments"] for d in p.get("allocator_decisions", [])]


def rows_from_template(run: dict) -> list[dict]:
    return [evaluate_one(d, _fallback_explanation(d)) for _, d in _decisions(run)]


def rows_from_cache(run: dict) -> list[dict]:
    rows = []
    for p in run["payments"]:
        if p.get("explanation") and p.get("allocator_decisions"):
            rows.append(evaluate_one(RecoveryDecision(**p["allocator_decisions"][0]), ExplanationResult(**p["explanation"])))
    return rows


def rows_from_llm(run: dict) -> list[dict]:
    """Fresh model output for one decision per (cause, action). Refuses unless LIVE_LLM=1."""
    if os.environ.get("LIVE_LLM") != "1":
        raise RuntimeError("--source llm makes real model calls: set LIVE_LLM=1 (and LLM_BASE_URL / LLM_API_KEY) to opt in")
    seen: set[tuple[str, str, bool]] = set()
    rows = []
    for _, d in _decisions(run):
        key = (d.cause.value, d.action, d.billing_cycle_successes >= 1)
        if key in seen:
            continue
        seen.add(key)
        rows.append(evaluate_one(d, generate_explanation(d)))
    return rows


SOURCES: dict[str, Callable[[dict], list[dict]]] = {"template": rows_from_template, "cached": rows_from_cache, "llm": rows_from_llm}


def latest_run_path() -> Path:
    runs = sorted(RESULTS_DIR.glob("run_*.json"))
    if not runs:
        raise FileNotFoundError("no eval/results/run_*.json - run `python -m eval.harness` first")
    return runs[-1]


def run_eval(source: str, run_path: Path) -> dict:
    """Evaluate one source against one run artifact and write eval/results/explanation_eval_<source>.json."""
    run = json.loads(run_path.read_text())
    rows = SOURCES[source](run)
    if source == "llm":
        fallbacks = [r for r in rows if r["generated_by"] != "llm"]
        rows = [r for r in rows if r["generated_by"] == "llm"]
    else:
        fallbacks = []
    report = {
        "source": source,
        "run_id": run["run_id"],
        "evaluated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "checks": {name: c.__doc__.strip().splitlines()[0] for name, c in zip(CHECK_NAMES, CHECKS)},
        **summarise(rows),
        "model_fallbacks": len(fallbacks),
        "failures": [r for r in rows if not r["passed"]][:25],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"explanation_eval_{source}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    _log(report, out)
    return report


def _log(report: dict, out: Path) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    event = {"event": "explanation_eval_completed", "source": report["source"], "run_id": report["run_id"],
             "n": report["n"], "pass_rate": report["pass_rate"], "model_fallbacks": report["model_fallbacks"],
             "failed_checks": {k: v["failed"] for k, v in report["per_check"].items() if v["failed"]},
             "ts": report["evaluated_at"], "output": str(out.relative_to(ROOT))}
    with (LOGS_DIR / "explanation_eval.jsonl").open("a") as f:
        f.write(json.dumps(event) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(SOURCES), default="template")
    parser.add_argument("--run", type=Path, default=None, help="run artifact (default: newest eval/results/run_*.json)")
    args = parser.parse_args()
    report = run_eval(args.source, args.run or latest_run_path())
    log.info("explanation eval (%s): %s of %d passed every check", args.source, report["pass_rate"], report["n"])
    for name, stats in report["per_check"].items():
        log.info("  %-20s pass rate %s", name, stats["pass_rate"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
