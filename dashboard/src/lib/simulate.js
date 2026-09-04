const API_BASE = 'http://localhost:8000'

export async function fetchPersonas() {
  const res = await fetch(`${API_BASE}/api/personas`)
  if (!res.ok) throw new Error(`GET /api/personas: HTTP ${res.status}`)
  return res.json()
}

export async function runSimulation(body) {
  const res = await fetch(`${API_BASE}/api/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `POST /api/simulate: HTTP ${res.status}`)
  }
  return res.json()
}

/** Adapts the live API response into the same payment shape Story/DecisionTraceView
 * already consume for batch payments - `allocator` (the simulated outcome) is
 * deliberately null, since a live run never touches eval/outcome_model.py (Sec 5.1). */
export function toPaymentShape(apiResponse) {
  return {
    payment_id: apiResponse.payment_id,
    cause: apiResponse.allocator_decision.cause,
    amount: apiResponse.amount,
    failure_time: apiResponse.failure_time,
    raw_error: apiResponse.raw_error,
    allocator: null,
    allocator_decisions: [apiResponse.allocator_decision],
    allocator_stage_traces: [apiResponse.allocator_stage_traces],
    explanation: apiResponse.explanation,
    baseline_decision: apiResponse.baseline_decision,
    decisions_differ: apiResponse.decisions_differ,
  }
}

export const FAILURE_CAUSES = [
  'insufficient_funds',
  'mandate_revoked',
  'mandate_expired',
  'amount_exceeds_mandate',
  'afa_required',
  'bank_technical',
  'unknown',
]
