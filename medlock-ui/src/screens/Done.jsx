import { useState } from 'react'
import Frame, { useResetFocus } from '../components/Frame.jsx'
import { logEvent } from '../api.js'

export default function Done({ onFinish, ...frame }) {
  const [answer, setAnswer] = useState(null) // { injected: bool, at: Date }
  useResetFocus([answer])

  const record = (injected) => {
    const at = new Date()
    logEvent(injected ? 'injection_confirmed' : 'injection_not_done')
    setAnswer({ injected, at })
  }

  if (answer) {
    return (
      <Frame
        {...frame}
        onBack={null}
        title={answer.injected ? 'All done' : 'Okay, nothing was recorded as taken'}
        primary={<button className="btn btn-primary" onClick={onFinish}>Finish</button>}
      >
        <p className="body-text">
          Logged at {answer.at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.
          {!answer.injected && ' If you need help, contact your clinic.'}
        </p>
      </Frame>
    )
  }

  return (
    <Frame {...frame} title="Did you inject the medication?">
      <div className="choice-row">
        <button className="btn btn-choice" onClick={() => record(true)}><span className="choice-symbol" aria-hidden>✓</span> Yes</button>
        <button className="btn btn-choice" onClick={() => record(false)}><span className="choice-symbol" aria-hidden>✕</span> No</button>
      </div>
    </Frame>
  )
}
