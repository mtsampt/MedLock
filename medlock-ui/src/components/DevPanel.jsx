import { useEffect, useState } from 'react'
import { mock } from '../api.js'

// Development-only controls that stand in for the hardware.
// Hidden automatically once VITE_API_URL points at the real backend.

export default function DevPanel({ screenIndex, flow, onJump }) {
  const [, force] = useState(0)
  useEffect(() => {
    const fn = () => force((n) => n + 1)
    mock.listeners.add(fn)
    return () => mock.listeners.delete(fn)
  }, [])

  const label = (s) => (s.kind === 'prep' ? s.step.title : s.kind)

  return (
    <aside className="dev">
      <h3>Dev panel (fake hardware)</h3>

      <section>
        <h4>Jump to screen</h4>
        <select value={screenIndex} onChange={(e) => onJump(Number(e.target.value))}>
          {flow.map((s, i) => (
            <option key={i} value={i}>{i}. {label(s)}</option>
          ))}
        </select>
      </section>

      <section>
        <h4>Next syringe check returns</h4>
        {['pass', 'fix', 'unable'].map((v) => (
          <label key={v} className="dev-radio">
            <input type="radio" name="verdict" checked={mock.nextVerdict === v} onChange={() => mock.set({ nextVerdict: v })} />
            {v}
          </label>
        ))}
      </section>
    </aside>
  )
}
