import { useJson } from '../lib/useJson.js'

// Stage 7 faithfulness eval (eval/explanation_eval.py, PRD Sec 4 / Sec 6.4):
// deterministic checks that each explanation says what the decision did.

const CHECK_TEXT = {
  action_matches: 'Describes the decision that was actually made',
  amounts_match: 'Mentions no amount other than the real one',
  times_match: 'Mentions no time or date other than the scheduled one',
  no_customer_jargon: 'Customer messages avoid payments jargon',
  jargon_explained: 'Technical terms only after plain words',
  no_internal_leak: 'No internal ids, scores or labels',
  sms_length: 'Each message fits one SMS',
  hinglish_present: 'Hinglish message is really Hinglish',
}

const SOURCE_TEXT = {
  template: 'Fallback text (used whenever the model is unavailable), for every decision',
  cached: 'Explanations cached in the saved run',
  llm: 'Fresh model output, one per kind of decision',
}

function pct(v) {
  return v === null || v === undefined ? '–' : `${Math.round(v * 100)}%`
}

function Source({ report }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">{SOURCE_TEXT[report.source] ?? report.source}</p>
        <p className={`text-sm font-semibold ${report.pass_rate === 1 ? 'text-emerald-700' : 'text-rose-700'}`}>
          {Math.round(report.pass_rate * report.n)} of {report.n} pass every check
        </p>
      </div>
      {report.model_fallbacks > 0 && (
        <p className="text-xs text-slate-500">{report.model_fallbacks} model calls failed and fell back to the template (not counted above).</p>
      )}
      {report.failures.length > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-slate-500">What failed ({report.failures.length})</summary>
          <ul className="mt-2 space-y-2">
            {report.failures.slice(0, 6).map((f, i) => (
              <li key={i} className="rounded bg-rose-50 p-2">
                <span className="font-mono text-slate-500">{f.payment_id}</span> · {f.failed_checks.map((c) => c.detail).join('; ')}
                <div className="mt-1 text-slate-700">“{f.texts.reasoning_plain}”</div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export default function ExplanationEvalPanel() {
  const template = useJson('/data/explanation_eval_template.json')
  const cached = useJson('/data/explanation_eval_cached.json')
  const llm = useJson('/data/explanation_eval_llm.json')
  const reports = [template.data, cached.data, llm.data].filter(Boolean)
  if (template.loading) return null
  if (!reports.length) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No explanation eval results found. Run <code>python -m eval.explanation_eval</code> and copy the output into dashboard/public/data/.
      </div>
    )
  }
  const main = template.data ?? reports[0]
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Do the explanations tell the truth? Checked by fixed rules, not by another model
      </h3>
      <p className="mt-1 text-sm text-slate-600">
        The language model only writes the explanation and the customer message, after the decision is made. These checks compare
        every one against its decision record.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {Object.entries(main.per_check).map(([name, s]) => (
          <div key={name} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
            <span className="text-slate-700">{CHECK_TEXT[name] ?? name}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.failed ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {pct(s.pass_rate)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-2">
        {reports.map((r) => <Source key={r.source} report={r} />)}
      </div>
      {!llm.data && (
        <p className="mt-2 text-xs text-slate-500">
          The fresh-model run needs an API key and runs only when opted in (<code>LIVE_LLM=1 python -m eval.explanation_eval --source llm</code>), so it
          isn't part of this saved demo yet.
        </p>
      )}
    </div>
  )
}
