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

// Three tokens, one already spent - the thesis in one glance before a
// single word of copy loads. Not decorative: this is the actual budget
// the rest of the page is about.
function AttemptBudgetMark() {
  return (
    <svg width="108" height="32" viewBox="0 0 108 32" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="3" fill="var(--accent)" />
      <path d="M9 16.5l4.5 4.5L23 11.5" stroke="var(--accent-ink)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="39" y="1" width="30" height="30" rx="3" stroke="#cbd5e1" strokeWidth="1.5" />
      <rect x="77" y="1" width="30" height="30" rx="3" stroke="#cbd5e1" strokeWidth="1.5" />
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3.5 8h9M8.5 3.5L13 8l-4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function StatCell({ label, value, detail, accent = false, border = true, topBorderOnMobile = false }) {
  return (
    <div
      className={`p-5 ${border ? 'sm:border-l sm:border-slate-200' : ''} first:border-l-0 ${
        topBorderOnMobile ? 'border-t border-slate-200 sm:border-t-0' : ''
      }`}
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-slate-500">{label}</p>
      <p className={`mt-1.5 font-mono text-[26px] font-medium leading-none tabular-nums ${accent ? 'text-[var(--accent)]' : 'text-slate-900'}`}>
        {value}
      </p>
      {detail && <p className="mt-2 text-[12.5px] leading-snug text-slate-500">{detail}</p>}
    </div>
  )
}

export default function LandingPage({ run, onEnterDashboard }) {
  const table = run?.results_table
  const baseline = table?.baseline
  const allocator = table?.allocator

  const attemptsSaved = baseline && allocator ? baseline.attempts_spent - allocator.attempts_spent : null
  const attemptsSavedPct = baseline && allocator ? Math.round((attemptsSaved / baseline.attempts_spent) * 100) : null

  return (
    <div style={{ fontFamily: 'var(--font-display)' }} className="min-h-screen bg-[#f8fafc]">
      <div className="mx-auto max-w-3xl px-5 py-14 sm:px-6">
        <div className="flex items-center justify-between gap-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-slate-500">Retry Budget Allocator</p>
          <AttemptBudgetMark />
        </div>

        <h1 className="mt-5 text-[2rem] font-semibold leading-[1.15] tracking-tight text-slate-900 sm:text-[2.375rem]">
          A fixed retry schedule treats this as a scheduling problem.
          <br className="hidden sm:block" /> Three non-renewable NPCI retry
          attempts make it a <span className="text-[var(--accent)]">constrained allocation problem</span>.
        </h1>

        <p style={{ fontFamily: 'ui-sans-serif, system-ui, sans-serif' }} className="mt-4 max-w-xl text-[15px] leading-relaxed text-slate-600">
          {baseline && allocator ? (
            <>
              The cause-aware allocator spends{' '}
              <span className="font-mono font-medium text-slate-900">{attemptsSavedPct}%</span> fewer retry attempts
              than a fixed schedule (
              <span className="font-mono tabular-nums text-slate-900">{allocator.attempts_spent}</span> vs{' '}
              <span className="font-mono tabular-nums text-slate-900">{baseline.attempts_spent}</span>) — but recovers
              fewer payments doing it (
              <span className="font-mono tabular-nums text-slate-900">{allocator.payments_recovered}</span> vs{' '}
              <span className="font-mono tabular-nums text-slate-900">{baseline.payments_recovered}</span>). The
              breakeven analysis below is where that trade actually gets decided.
            </>
          ) : (
            'Loading the batch result…'
          )}
        </p>

        <div className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
          <div className="grid grid-cols-2 sm:grid-cols-4">
            <StatCell
              label="Attempts saved"
              value={attemptsSaved !== null ? `${attemptsSaved}` : '—'}
              detail={attemptsSavedPct !== null ? `${attemptsSavedPct}% vs. fixed schedule` : null}
              accent
              border={false}
            />
            <StatCell
              label="Payments recovered"
              value={allocator && baseline ? `${allocator.payments_recovered}/${baseline.payments_recovered}` : '—'}
              detail="Baseline wins here — stated plainly."
            />
            <StatCell
              label="Compliance invariants"
              value={COMPLIANCE_INVARIANTS.length}
              detail="Enforced structurally, checked live."
              topBorderOnMobile
            />
            <StatCell label="Automated tests" value={TEST_COUNT} detail="98% coverage on pipeline/, in CI." topBorderOnMobile />
          </div>
          <div className="border-t border-slate-200 px-5 py-3">
            <p className="text-[12px] leading-snug text-slate-500">
              {COMPLIANCE_INVARIANTS.join('  ·  ')}
            </p>
          </div>
        </div>

        {baseline && allocator && (
          <p className="mt-3 font-mono text-[12px] tabular-nums text-slate-400">
            {formatMoney(allocator.amount_recovered_paise)} recovered by the allocator vs {formatMoney(baseline.amount_recovered_paise)} by
            the fixed schedule — {run.n} synthesized payments, seed {run.seed}.
          </p>
        )}

        <div className="mt-8 border-t border-slate-200 pt-6">
          <p style={{ fontFamily: 'ui-sans-serif, system-ui, sans-serif' }} className="text-[14px] leading-relaxed text-slate-600">
            <span className="font-mono text-[11px] font-medium uppercase tracking-wide text-slate-900">What&apos;s real </span>
            — the pipeline runs live against real input in the Live Simulator tab, and 4 real Razorpay test-API
            mandate-creation routes have been tried (all currently gated behind an account activation).{' '}
            <span className="font-mono text-[11px] font-medium uppercase tracking-wide text-slate-900">What&apos;s simulated</span> — whether
            any given retry succeeds, drawn from a frozen, declared outcome model, never observed from real customer
            behavior. Full breakdown in the README.
          </p>
        </div>

        <button
          onClick={onEnterDashboard}
          className="group mt-8 inline-flex items-center gap-2 rounded-md bg-slate-900 px-5 py-3 text-[14px] font-medium text-white transition hover:bg-[var(--accent)]"
        >
          Open the interactive dashboard
          <span className="transition-transform group-hover:translate-x-0.5">
            <ArrowIcon />
          </span>
        </button>
      </div>
    </div>
  )
}
