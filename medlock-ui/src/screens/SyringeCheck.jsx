import { useState } from 'react'
import Frame from '../components/Frame.jsx'
import { checkSyringe } from '../api.js'

// Two states: waiting for the patient to dock the syringe, then checking.

export default function SyringeCheck({ onResult, ...frame }) {
  const [checking, setChecking] = useState(false)

  const run = async () => {
    setChecking(true)
    try {
      onResult(await checkSyringe())
    } catch {
      // Network or backend failure is never a pass.
      onResult({ verdict: 'unable', reason: 'The station could not complete the check', action: 'Try again. If it keeps happening, contact your clinic.' })
    } finally {
      setChecking(false)
    }
  }

  return (
    <Frame
      {...frame}
      onBack={checking ? null : frame.onBack}
      title={checking ? 'Checking your syringe…' : 'Place the syringe in the dock'}
      primary={
        <button className="btn btn-primary" onClick={run} disabled={checking}>
          {checking ? 'Checking…' : 'Check syringe'}
        </button>
      }
    >
      {checking ? (
        <div className="checking">
          <div className="spinner" aria-hidden />
          <p className="body-text">Keep the syringe still. This takes a few seconds.</p>
        </div>
      ) : (
        <p className="body-text">Press it in until it clicks. Keep the needle cap on.</p>
      )}
    </Frame>
  )
}
