// Real-time link to the MedLock station (python -m station).
//
// The station pushes its state-machine state over Server-Sent Events, so the UI
// reacts the moment the hardware changes (syringe inserted/removed, measuring,
// result). Enabled by `npm run build:station` or `npm run dev:station`;
// otherwise the UI keeps using the mock in api.js.

import { useCallback, useEffect, useState } from 'react'

export const STATION_MODE = import.meta.env.VITE_STATION === 'true'
const BASE = import.meta.env.VITE_STATION_URL ?? '' // '' = same origin (or Vite's /api proxy)

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  return res.ok
}

// Snapshot shape (see station/controller.py):
//   { revision, state: 'IDLE'|'SEATED'|'MEASURING'|'RESULT'|'ERROR'|'SHUTDOWN',
//     seated, sim_seat, result: { verdict, reason, action, volume_ml, air_ml, volume_checked } | null }
export function useStation() {
  const [snap, setSnap] = useState(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!STATION_MODE) return undefined
    const es = new EventSource(`${BASE}/api/events`)
    es.onmessage = (e) => {
      try {
        setSnap(JSON.parse(e.data)) // one ordered stream: newest message wins
        setConnected(true)
      } catch {
        /* ignore a malformed frame */
      }
    }
    es.onerror = () => setConnected(false) // EventSource reconnects by itself
    return () => es.close()
  }, [])

  const measure = useCallback(() => post('/api/measure'), [])
  const acknowledge = useCallback(() => post('/api/acknowledge'), [])
  const setSeat = useCallback((seated) => post('/api/sim/seat', { seated }), [])

  return { enabled: STATION_MODE, connected, snap, measure, acknowledge, setSeat }
}
