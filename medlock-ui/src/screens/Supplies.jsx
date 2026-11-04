import { useState } from 'react'
import Frame from '../components/Frame.jsx'
import { PROTOCOL } from '../protocol.js'

// The patient confirms each supply themselves, one item per screen.
// Answering "No" shows what to get before moving on.

const ITEMS = PROTOCOL.supplies

export default function Supplies({ onContinue, ...frame }) {
  const [index, setIndex] = useState(0) // ITEMS.length means every item is confirmed
  const [missing, setMissing] = useState(false)
  const item = ITEMS[index]

  const have = () => {
    setMissing(false)
    setIndex((i) => i + 1)
  }
  const back = () => {
    if (missing) setMissing(false)
    else if (index > 0) setIndex((i) => i - 1)
    else frame.onBack?.()
  }

  if (index === ITEMS.length) {
    return (
      <Frame
        {...frame}
        onBack={back}
        title="All supplies ready"
        primary={<button className="btn btn-primary" onClick={onContinue}>Continue</button>}
      >
        <p className="confirm">
          <span className="confirm-symbol" aria-hidden>✓</span>
          You have all {ITEMS.length} items.
        </p>
      </Frame>
    )
  }

  if (missing) {
    return (
      <Frame
        {...frame}
        onBack={back}
        title={`Get the ${item.label.toLowerCase()}`}
        primary={<button className="btn btn-primary" onClick={have}>I have it now</button>}
      >
        <p className="body-text">You need this to prepare the shot. Can't find it? Tap Help to contact your clinic.</p>
      </Frame>
    )
  }

  return (
    <Frame {...frame} onBack={back}>
      <p className="eyebrow">Do you have this? · {index + 1} of {ITEMS.length}</p>
      <h1 className="title title-lg">{item.label}</h1>
      <div className="choice-row">
        <button className="btn btn-choice" onClick={have}><span className="choice-symbol" aria-hidden>✓</span> Yes</button>
        <button className="btn btn-choice" onClick={() => setMissing(true)}><span className="choice-symbol" aria-hidden>✕</span> No</button>
      </div>
    </Frame>
  )
}
