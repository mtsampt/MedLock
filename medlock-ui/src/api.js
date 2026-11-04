// Single place the UI talks to the backend.
//
// Set VITE_API_URL (e.g. in a .env file) to point at the real FastAPI
// server. With no URL, the UI uses the mock below, which the dev panel
// controls, so you can build every screen before the hardware works.
//
// API contract (agree on this with the backend owner):
//   GET  /supplies  -> { holders: { [supplyId]: { present: bool, correct: bool } } }
//   POST /check     -> { verdict: "pass" | "fix" | "unable", reason: str, action: str,
//                        volume_ml: number | null, air_ml: number | null }
//   POST /log       body { event: str, at: ISO string } -> { ok: true }

const API_URL = import.meta.env.VITE_API_URL

// ---- Mock backend --------------------------------------------------------

export const mock = {
  holders: {
    diluent: { present: true, correct: true },
    powder: { present: true, correct: true },
    syringe: { present: true, correct: true },
    needle: { present: false, correct: true },
    wipes: { present: true, correct: true },
  },
  nextVerdict: 'pass',
  listeners: new Set(),
  set(patch) {
    Object.assign(this, patch)
    this.listeners.forEach((fn) => fn())
  },
}

const MOCK_RESULTS = {
  pass: { verdict: 'pass', reason: 'Volume and air checks passed.', action: '', volume_ml: 1.0, air_ml: 0.0 },
  fix: {
    verdict: 'fix',
    reason: 'Air bubble detected',
    action: 'Hold the syringe needle-up, tap it so the bubble rises, then push the air out.',
    volume_ml: 0.92,
    air_ml: 0.14,
  },
  unable: {
    verdict: 'unable',
    reason: 'Syringe not seated correctly',
    action: 'Take the syringe out and press it fully into the dock.',
    volume_ml: null,
    air_ml: null,
  },
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

// ---- Public API ----------------------------------------------------------

export async function getSupplies() {
  if (API_URL) {
    const res = await fetch(`${API_URL}/supplies`)
    return res.json()
  }
  return { holders: structuredClone(mock.holders) }
}

export async function checkSyringe() {
  if (API_URL) {
    const res = await fetch(`${API_URL}/check`, { method: 'POST' })
    return res.json()
  }
  await wait(2000) // simulate camera + vision processing time
  return MOCK_RESULTS[mock.nextVerdict]
}

export async function logEvent(event) {
  const body = { event, at: new Date().toISOString() }
  if (API_URL) {
    await fetch(`${API_URL}/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return
  }
  console.log('[mock log]', body)
}
