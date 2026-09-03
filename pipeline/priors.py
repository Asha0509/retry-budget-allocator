"""Stage 3 - recoverability priors (PRD Sec 4).

Each FailureCause carries a fixed recoverability score and a recommended
action shape, grounded in PRD Sec 2's published data. Deterministic lookup,
same as Stage 2 - no model call, no learned weights.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from pipeline.models import FailureCause, StageTrace, run_stage

ActionShape = Literal["notify", "retry", "stop"]


class RecoverabilityPrior(BaseModel):
    """Stage 3 output for one cause: how likely a retry is to succeed, and how."""

    cause: FailureCause
    recoverability: float
    action_shape: ActionShape
    rationale: str


# PRD Sec 4 Stage 3 + Sec 2 published data:
# - mandate_revoked/mandate_expired/amount_exceeds_mandate: a retry against a
#   dead or too-small mandate cannot succeed, ever - stop, spend nothing.
# - insufficient_funds: the dominant failure cause (~20M AutoPay revocations/
#   month per NPCI data), recoverable but only once the account is funded -
#   timing-sensitive, handled by Stage 4/5's window choice.
# - bank_technical: transient infra failure, published spaced-retry recovery
#   (15-20%) applies most cleanly here, short-horizon retry.
# - afa_required: NPCI/RBI mandates fresh customer authentication above the
#   AFA threshold - a silent retry cannot supply that, so the action is
#   notify (ask the customer to act), not retry.
# - unknown: cause didn't match any known pattern - treated conservatively,
#   low recoverability, notify rather than spend a scarce attempt blind.
_PRIORS: dict[FailureCause, RecoverabilityPrior] = {
    FailureCause.INSUFFICIENT_FUNDS: RecoverabilityPrior(
        cause=FailureCause.INSUFFICIENT_FUNDS,
        recoverability=0.7,
        action_shape="retry",
        rationale="Dominant, timing-sensitive cause - recoverable once funded (PRD Sec 2).",
    ),
    FailureCause.BANK_TECHNICAL: RecoverabilityPrior(
        cause=FailureCause.BANK_TECHNICAL,
        recoverability=0.6,
        action_shape="retry",
        rationale="Transient infra failure - short-horizon retry recovers it (PRD Sec 2).",
    ),
    FailureCause.MANDATE_REVOKED: RecoverabilityPrior(
        cause=FailureCause.MANDATE_REVOKED,
        recoverability=0.0,
        action_shape="stop",
        rationale="No mandate to charge against - retry cannot succeed.",
    ),
    FailureCause.MANDATE_EXPIRED: RecoverabilityPrior(
        cause=FailureCause.MANDATE_EXPIRED,
        recoverability=0.0,
        action_shape="stop",
        rationale="Mandate lapsed - retry cannot succeed without re-authorization.",
    ),
    FailureCause.AMOUNT_EXCEEDS_MANDATE: RecoverabilityPrior(
        cause=FailureCause.AMOUNT_EXCEEDS_MANDATE,
        recoverability=0.0,
        action_shape="stop",
        rationale="Amount is structurally above the mandate cap - retry cannot succeed unchanged.",
    ),
    FailureCause.AFA_REQUIRED: RecoverabilityPrior(
        cause=FailureCause.AFA_REQUIRED,
        recoverability=0.0,
        action_shape="notify",
        rationale="NPCI/RBI requires fresh customer authentication - a silent retry can't supply it.",
    ),
    FailureCause.UNKNOWN: RecoverabilityPrior(
        cause=FailureCause.UNKNOWN,
        recoverability=0.2,
        action_shape="notify",
        rationale="Unclassified - conservative low score, notify rather than spend a blind attempt.",
    ),
}


def get_prior(cause: FailureCause) -> RecoverabilityPrior:
    """Look up the fixed recoverability prior for a cause (PRD Sec 4, Stage 3)."""
    return _PRIORS[cause]


def run_priors(cause: FailureCause) -> tuple[RecoverabilityPrior, StageTrace]:
    """Stage 3 entry point: look up the prior and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"cause={cause.value}"

    def _work() -> tuple[RecoverabilityPrior, str]:
        prior = get_prior(cause)
        return prior, f"recoverability={prior.recoverability} action_shape={prior.action_shape}"

    return run_stage("priors", input_summary, _work)
