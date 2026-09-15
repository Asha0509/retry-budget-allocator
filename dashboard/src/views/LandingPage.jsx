import { formatMoney } from '../lib/format.js'

// Snapshot of `pytest --collect-only -q` (2026-09-15) - not wired live,
// since that would need new backend infrastructure just for one landing
// page number. Update this if the suite grows meaningfully.
const TEST_COUNT = 327

const COMPLIANCE_INVARIANTS = [
  'Never more than 3 retry attempts per mandate',
  'Never scheduled inside a peak window (10:00-13:00, 17:00-21:30 IST)',
  'Never more than one successful debit per token per billing cycle',
]

function StatTile({ label, value, detail }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  )
}

export default function LandingPage({ run, onEnterDashboard }) {
  const table = run?.results_table
  const baseline = table?.baseline
  const allocator = table?.allocator

  const attemptsSaved = baseline && allocator ? baseline.attempts_spent - allocator.attempts_spent : null
  const attemptsSavedPct =
    baseline && allocator ? Math.round((attemptsSaved / baseline.attempts_spent) * 100) : null

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Retry Budget Allocator</p>

      <h1 className="mt-2 text-3xl font-semibold leading-snug text-slate-900">
        A fixed retry schedule treats this as a scheduling problem. Three
        non-renewable NPCI retry attempts make it a constrained allocation
        problem.
      </h1>

      <p className="mt-4 text-base text-slate-700">
        {baseline && allocator ? (
          <>
            The cause-aware allocator spends {attemptsSavedPct}% fewer retry
            attempts than a fixed schedule ({allocator.attempts_spent} vs{' '}
            {baseline.attempts_spent}) — but recovers fewer payments doing it
            ({allocator.payments_recovered} vs {baseline.payments_recovered}).
            See the breakeven analysis for when that trade is worth it.
          </>
        ) : (
          'Loading the batch result…'
        )}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-2">
        <StatTile
          label="Attempts saved vs. fixed schedule"
          value={attemptsSaved !== null ? `${attemptsSaved} (${attemptsSavedPct}%)` : '—'}
          detail={baseline && allocator ? `${allocator.attempts_spent} vs ${baseline.attempts_spent}` : null}
        />
        <StatTile
          label="Payments recovered vs. fixed schedule"
          value={allocator && baseline ? `${allocator.payments_recovered} vs ${baseline.payments_recovered}` : '—'}
          detail="Baseline wins here, plainly stated - see the breakeven for when the allocator's savings are worth it anyway."
        />
        <StatTile
          label="Compliance invariants enforced"
          value={COMPLIANCE_INVARIANTS.length}
          detail={COMPLIANCE_INVARIANTS.join(' · ')}
        />
        <StatTile label="Automated tests" value={TEST_COUNT} detail="98% line coverage on pipeline/, enforced in CI" />
      </div>

      {baseline && allocator && (
        <p className="mt-4 text-xs text-slate-400">
          {formatMoney(allocator.amount_recovered_paise)} recovered by the allocator vs{' '}
          {formatMoney(baseline.amount_recovered_paise)} by the fixed schedule, across {run.n} synthesized
          payments (seed {run.seed}).
        </p>
      )}

      <p className="mt-6 text-sm text-slate-600">
        What's real: the pipeline runs live against real input in the Live Simulator tab, and 4 real Razorpay
        test-API mandate-creation routes have been tried (all currently gated behind an account activation). What's
        simulated: whether any given retry succeeds - drawn from a frozen, declared outcome model, never observed
        from real customer behavior. See the README for the full breakdown.
      </p>

      <button
        onClick={onEnterDashboard}
        className="mt-8 rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
      >
        Open the interactive dashboard →
      </button>
    </div>
  )
}
