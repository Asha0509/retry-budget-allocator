import { useEffect, useState } from 'react'

// Reads saved run artifacts from public/data/ - never a live API call (PRD
// Sec 6.2 demo-reliability requirement). The files are static copies of the
// real eval/results/*.json produced by eval/harness.py and eval/sensitivity.py.
export function useRunData() {
  const [state, setState] = useState({ loading: true, error: null, run: null, sensitivity: null })

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetch('/data/latest_run.json').then((r) => {
        if (!r.ok) throw new Error(`latest_run.json: HTTP ${r.status}`)
        return r.json()
      }),
      fetch('/data/sensitivity.json').then((r) => {
        if (!r.ok) throw new Error(`sensitivity.json: HTTP ${r.status}`)
        return r.json()
      }),
    ])
      .then(([run, sensitivity]) => {
        if (!cancelled) setState({ loading: false, error: null, run, sensitivity })
      })
      .catch((error) => {
        if (!cancelled) setState({ loading: false, error, run: null, sensitivity: null })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
