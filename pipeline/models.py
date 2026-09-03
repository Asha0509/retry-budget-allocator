"""Shared schemas for the retry budget allocator pipeline (PRD Sec 4).

Every stage returns a StageTrace alongside its result so the dashboard can
render the pipeline as it executes (PRD Sec 6.1) - built in from Stage 1
rather than retrofitted later.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict


class FailureCause(str, Enum):
    """Cause classes a failed payment can be sorted into (PRD Sec 4, Stage 2)."""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    MANDATE_REVOKED = "mandate_revoked"
    MANDATE_EXPIRED = "mandate_expired"
    AMOUNT_EXCEEDS_MANDATE = "amount_exceeds_mandate"
    AFA_REQUIRED = "afa_required"
    BANK_TECHNICAL = "bank_technical"
    UNKNOWN = "unknown"


class RazorpayError(BaseModel):
    """The raw Razorpay error object, carried through the pipeline unmodified.

    Only code/description/source/step/reason are typed (PRD Sec 4, Stage 2).
    extra="allow" keeps any other fields Razorpay sends (metadata, field, ...)
    so the raw payload is never discarded after classification.
    """

    model_config = ConfigDict(extra="allow")

    code: str | None = None
    description: str | None = None
    source: str | None = None
    step: str | None = None
    reason: str | None = None


class StageTrace(BaseModel):
    """One pipeline stage's execution record (PRD Sec 6.1 - executing pipeline view)."""

    stage: str
    input_summary: str
    output_summary: str
    elapsed_ms: float
    skipped: bool = False
    skip_reason: str | None = None


T = TypeVar("T")


def run_stage(stage: str, input_summary: str, fn: Callable[[], tuple[T, str]]) -> tuple[T, StageTrace]:
    """Time a stage's work and package the result with its StageTrace.

    `fn` returns (result, output_summary). Shared by every pipeline stage so
    tracing is consistent without each stage re-implementing timing.
    """
    start = time.perf_counter()
    result, output_summary = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000
    trace = StageTrace(
        stage=stage,
        input_summary=input_summary,
        output_summary=output_summary,
        elapsed_ms=elapsed_ms,
    )
    return result, trace
