// Static copy shared by the landing page, the tutorial and the docs view.
// Numbers live in the saved run artifacts, never here (PRD Sec 6.2).

export const REPO = 'https://github.com/Asha0509/retry-budget-allocator'

export const DOCS = [
  { title: 'Results write-up', file: 'docs/RESULTS.md', note: 'Outcome model first, then every number, the sensitivity sweep and what did not work.' },
  { title: 'Architecture', file: 'docs/architecture.md', note: 'Pipeline, data flow and diagrams.' },
  { title: 'Product requirements', file: 'docs/prd.md', note: 'The spec every stage is checked against.' },
  { title: 'Data quality', file: 'docs/DATA_QUALITY.md', note: 'The data contract and the checks that gate the batch.' },
  { title: 'Build log', file: 'docs/build-log.md', note: 'What broke while building this and how it was fixed.' },
]

export const STAGES = [
  { n: 1, name: 'Ingest', plain: 'Read the failed payment and keep the bank’s raw error attached.', tech: 'Pydantic schema; raw payload is carried to the decision record.' },
  { n: 2, name: 'Classify', plain: 'Work out why it failed by looking the error up in a fixed table.', tech: 'Deterministic lookup over the Razorpay error object. Never a model.', ai: false },
  { n: 3, name: 'Priors', plain: 'Ask how likely a retry is to work for this kind of failure.', tech: 'Per-cause success priors with an explicit unrecoverable set.' },
  { n: 4, name: 'Funding window', plain: 'Guess when money is likely to arrive, and say how sure we are.', tech: 'Probabilistic; below the confidence threshold it falls back to 24h / 72h / 7d.' },
  { n: 5, name: 'Allocate', plain: 'Score every allowed time slot and keep all the scores, winners and losers.', tech: 'Expected-value scoring; all candidates returned with rejection reasons.' },
  { n: 6, name: 'Decide', plain: 'Pick one action: ask the customer, retry at a chosen time, or stop.', tech: 'Compliance invariants enforced here and re-checked live.' },
  { n: 7, name: 'Explain', plain: 'Write the plain-language reason and the customer message.', tech: 'The only model call. Off the critical path, with a template fallback.', ai: true },
]

export const INTERVENTIONS = [
  { key: 'notify', label: 'Ask the customer', when: 'The bank needs the customer to approve or re-confirm. A silent retry cannot work.', color: '#f59e0b' },
  { key: 'retry', label: 'Retry at a chosen time', when: 'Money is likely to arrive, or the bank hiccup is temporary. Pick a legal, well-timed slot.', color: '#34d399' },
  { key: 'stop', label: 'Stop early', when: 'The permission is gone or expired. More attempts only waste the scarce budget.', color: '#f87171' },
]

// Cause -> branch shown in the hero diagram. Mirrors the per-cause actions in
// the saved batch run; the Live Simulator computes the real decision.
export const CAUSE_BRANCH = {
  insufficient_funds: 'retry',
  bank_technical: 'retry',
  afa_required: 'notify',
  unknown: 'notify',
  mandate_revoked: 'stop',
  mandate_expired: 'stop',
  amount_exceeds_mandate: 'stop',
}

export const INVARIANTS = [
  { title: 'At most 3 retries', plain: 'A payment gets one original try plus three retries, never more.', tech: 'NPCI cap, asserted on every scheduled attempt.' },
  { title: 'Never at peak hours', plain: 'No retry is scheduled in the busy windows when banks are most loaded.', tech: '10:00-13:00 and 17:00-21:30 IST.' },
  { title: 'One debit per cycle', plain: 'The customer is never charged twice in the same billing month.', tech: 'One successful debit per token per billing cycle.' },
]

export const GLOSSARY = [
  ['AutoPay', 'A permission a customer gives once so a business can pull a recurring payment (a subscription, an EMI) from their bank account.'],
  ['Mandate', 'The record of that permission: how much, how often, until when. It can be revoked or expire.'],
  ['NPCI', 'The body that runs UPI in India. It limits how many times a failed recurring debit may be retried.'],
  ['Retry budget', 'The 3 retries a payment is allowed. Spend them badly and you cannot get them back.'],
  ['Peak window', 'Busy banking hours when retries are not allowed.'],
  ['Funding window', 'The days when the customer’s account is likely to have money, such as just after payday. It is inferred, never known.'],
  ['Baseline', 'A fixed schedule that retries at set intervals regardless of why the payment failed. The thing we compare against.'],
  ['Outcome model', 'The declared rules we use to decide whether a simulated retry succeeds. We wrote it, so results are about spending a budget well under that model, not real recovery rates.'],
]
