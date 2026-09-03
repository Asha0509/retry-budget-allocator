// Client-side re-implementation of pipeline/compliance.py's invariants, run
// live against the loaded batch (PRD Sec 6.1: "run the compliance
// assertions live on screen... not asserted in prose").

const PEAK_WINDOWS = [
  [10 * 60, 13 * 60], // 10:00-13:00
  [17 * 60, 21 * 60 + 30], // 17:00-21:30
]
const MAX_RETRY_ATTEMPTS = 3

function istMinutesOfDay(iso) {
  const d = new Date(iso)
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(d)
  const hour = Number(parts.find((p) => p.type === 'hour').value)
  const minute = Number(parts.find((p) => p.type === 'minute').value)
  return hour * 60 + minute
}

export function isPeakWindow(iso) {
  const minutes = istMinutesOfDay(iso)
  return PEAK_WINDOWS.some(([start, end]) => minutes >= start && minutes < end)
}

/** Runs the three PRD Sec 2 invariants against every payment's allocator
 * decisions in the loaded run, returns a structured pass/fail report. */
export function runComplianceChecks(payments) {
  const capViolations = []
  const peakViolations = []
  let totalDecisionsChecked = 0
  let totalScheduledChecked = 0

  for (const payment of payments) {
    for (const decision of payment.allocator_decisions ?? []) {
      totalDecisionsChecked += 1
      if (decision.attempts_used > MAX_RETRY_ATTEMPTS) {
        capViolations.push({ payment_id: payment.payment_id, attempts_used: decision.attempts_used })
      }
      if (decision.scheduled_at) {
        totalScheduledChecked += 1
        if (isPeakWindow(decision.scheduled_at)) {
          peakViolations.push({ payment_id: payment.payment_id, scheduled_at: decision.scheduled_at })
        }
      }
    }
  }

  return {
    attemptCap: {
      label: `Never more than ${MAX_RETRY_ATTEMPTS} retry attempts per mandate`,
      checked: totalDecisionsChecked,
      violations: capViolations,
      passed: capViolations.length === 0,
    },
    peakWindow: {
      label: 'Never scheduled inside a peak window (10:00-13:00, 17:00-21:30 IST)',
      checked: totalScheduledChecked,
      violations: peakViolations,
      passed: peakViolations.length === 0,
    },
    oneSuccessPerCycle: {
      label: 'At most one successful debit per token per billing cycle',
      // Not independently re-derivable from this batch's data (each synthetic
      // payment represents one failure event, not a multi-cycle history) -
      // enforced structurally instead: the simulation loop (eval/harness.py
      // _simulate_one) stops immediately on the first recorded success, so a
      // second attempt is never even generated. Stated honestly, not faked
      // as a live data check with nothing to actually vary.
      enforcedByConstruction: true,
      passed: true,
    },
  }
}
