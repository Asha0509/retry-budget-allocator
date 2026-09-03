// Plain-language labels (CLAUDE.md presentation rule: understandable by
// someone who has never heard of NPCI, mandates, or AutoPay).

export const CAUSE_LABELS = {
  insufficient_funds: 'Not enough money in the account',
  mandate_revoked: 'Customer turned off automatic payments',
  mandate_expired: 'Automatic payment permission expired',
  amount_exceeds_mandate: 'Amount is higher than what was approved',
  afa_required: 'Bank needs the customer to re-confirm',
  bank_technical: 'Bank had a temporary technical problem',
  unknown: "We couldn't tell why it failed",
}

export const ACTION_LABELS = {
  retry: 'Try again later',
  notify: 'Ask the customer to act',
  stop: 'Stop trying',
}

export const ACTION_COLORS = {
  retry: 'bg-blue-100 text-blue-800 border-blue-200',
  notify: 'bg-amber-100 text-amber-800 border-amber-200',
  stop: 'bg-rose-100 text-rose-800 border-rose-200',
}

export function formatMoney(paise) {
  const rupees = paise / 100
  return `₹${rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }) + ' IST'
}

export function causeLabel(cause) {
  return CAUSE_LABELS[cause] ?? cause
}

export function actionLabel(action) {
  return ACTION_LABELS[action] ?? action
}
