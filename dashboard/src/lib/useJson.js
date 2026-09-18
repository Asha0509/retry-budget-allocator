import { useEffect, useState } from 'react'

// Optional saved artifacts from public/data/ (PRD Sec 6.2: never a live call).
// Unlike useRunData, a missing file is not fatal - the panel that needs it
// says what to run instead.
export function useJson(path) {
  const [state, setState] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    let cancelled = false
    fetch(path)
      .then((r) => {
        if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => !cancelled && setState({ loading: false, error: null, data }))
      .catch((error) => !cancelled && setState({ loading: false, error, data: null }))
    return () => {
      cancelled = true
    }
  }, [path])
  return state
}
