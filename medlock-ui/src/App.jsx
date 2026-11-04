import { useState } from 'react'
import { PROTOCOL } from './protocol.js'
import { logEvent } from './api.js'
import Start from './screens/Start.jsx'
import Supplies from './screens/Supplies.jsx'
import PrepStep from './screens/PrepStep.jsx'
import SyringeCheck from './screens/SyringeCheck.jsx'
import Result from './screens/Result.jsx'
import Done from './screens/Done.jsx'
import HelpOverlay from './components/HelpOverlay.jsx'
import DevPanel from './components/DevPanel.jsx'

// The whole patient flow, in order. Each entry is one screen.
// Result is not in this list: it is reached only from SyringeCheck.
const FLOW = [
  { kind: 'start' },
  { kind: 'supplies' },
  ...PROTOCOL.prepSteps.map((step) => ({ kind: 'prep', step })),
  { kind: 'check' },
  { kind: 'done' },
]
const TOTAL_STEPS = FLOW.length - 1 // "Start" is not counted as a step

export default function App() {
  const [index, setIndex] = useState(0)
  const [result, setResult] = useState(null) // last syringe check result
  const [helpOpen, setHelpOpen] = useState(false)

  const screen = FLOW[index]
  const next = () => setIndex((i) => Math.min(i + 1, FLOW.length - 1))
  const back = () => {
    setResult(null)
    setIndex((i) => Math.max(i - 1, 0))
  }
  const restart = () => {
    setResult(null)
    setIndex(0)
  }

  const frameProps = {
    step: index,
    totalSteps: TOTAL_STEPS,
    onBack: index > 0 ? back : null,
    onHelp: () => setHelpOpen(true),
  }

  let content
  if (result) {
    content = (
      <Result
        {...frameProps}
        result={result}
        onContinue={() => {
          logEvent('check_passed')
          setResult(null)
          next()
        }}
        onRetry={() => setResult(null)} // back to the syringe check screen
      />
    )
  } else if (screen.kind === 'start') {
    content = <Start {...frameProps} onBegin={() => { logEvent('session_started'); next() }} />
  } else if (screen.kind === 'supplies') {
    content = <Supplies {...frameProps} onContinue={next} />
  } else if (screen.kind === 'prep') {
    content = <PrepStep {...frameProps} step={index} prep={screen.step} onNext={next} />
  } else if (screen.kind === 'check') {
    content = <SyringeCheck {...frameProps} onResult={(r) => { logEvent(`check_${r.verdict}`); setResult(r) }} />
  } else if (screen.kind === 'done') {
    content = <Done {...frameProps} onFinish={restart} />
  }

  return (
    <div className="stage">
      <div className="device">
        {content}
        {helpOpen && <HelpOverlay onClose={() => setHelpOpen(false)} />}
      </div>
      {!import.meta.env.VITE_API_URL && (
        <DevPanel screenIndex={index} flow={FLOW} onJump={(i) => { setResult(null); setIndex(i) }} />
      )}
    </div>
  )
}
