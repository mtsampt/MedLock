import { useEffect, useState } from 'react'
import Frame from '../components/Frame.jsx'
import { PROTOCOL } from '../protocol.js'

// Placeholder dose time: 2 hours from page load.
// Replace with the time from the patient's medication profile.
const DOSE_TIME = new Date(Date.now() + 2 * 60 * 60 * 1000)

function formatCountdown(ms) {
  if (ms <= 0) return 'Due now'
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  return `in ${h}h ${String(m).padStart(2, '0')}m`
}

export default function Start({ onBegin, ...frame }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(t)
  }, [])

  return (
    <Frame
      {...frame}
      title={PROTOCOL.medication}
      primary={<button className="btn btn-primary" onClick={onBegin}>Begin</button>}
    >
      <div className="dose-card">
        <div className="dose-time">
          <span className="info-label">Dose time</span>
          <span className="info-value">
            {DOSE_TIME.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
          </span>
        </div>
        <span className="pill">{formatCountdown(DOSE_TIME - now)}</span>
      </div>
      <p className="body-text">Takes about 10 minutes.</p>
    </Frame>
  )
}
