import { useCallback, useEffect, useRef, useState } from 'react'
import { getState, sendAction, logEvent } from './api.js'
import Frame from './components/Frame.jsx'
import Start from './screens/Start.jsx'
import Supplies from './screens/Supplies.jsx'
import PrepStep from './screens/PrepStep.jsx'
import SyringeCheck from './screens/SyringeCheck.jsx'
import Result from './screens/Result.jsx'
import Done from './screens/Done.jsx'
import HelpOverlay from './components/HelpOverlay.jsx'

export default function App() {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const sending = useRef(false)
  const sequence = useRef(0)
  const applied = useRef(0)
  const acknowledged = useRef(null)
  const accept = useCallback((next, requestId) => {
    if (requestId < applied.current) return
    applied.current = requestId
    setState((previous) => previous?.session_id === next.session_id && previous.revision > next.revision ? previous : next)
    setError('')
  }, [])
  const refresh = useCallback(async () => {
    if (sending.current) return
    const id = ++sequence.current
    try { accept(await getState(), id) }
    catch (failure) { if (id >= applied.current) setError(failure.message) }
  }, [accept])
  useEffect(() => {
    let alive = true
    let timer
    const poll = async () => {
      if (!alive) return
      await refresh()
      if (alive) timer = setTimeout(poll, 500)
    }
    poll()
    return () => { alive = false; clearTimeout(timer) }
  }, [refresh])
  const act = async (action) => {
    if (!state || sending.current) return
    sending.current = true
    setPending(true)
    const id = ++sequence.current
    try { accept(await sendAction(action, state), id) }
    catch (failure) { setError(failure.message) }
    finally { sending.current = false; setPending(false) }
  }
  useEffect(() => {
    if (state?.focus_action) document.querySelector(`[data-action="${state.focus_action}"]`)?.focus({ preventScroll: true })
  }, [state?.focus_action, state?.revision])
  useEffect(() => {
    if (state?.screen !== 'result' || !state.check_id || acknowledged.current === state.check_id) return
    let secondFrame
    const frame = requestAnimationFrame(() => { secondFrame = requestAnimationFrame(() => {
      acknowledged.current = state.check_id
      logEvent('result_displayed', state.check_id).catch(failure => setError(failure.message))
    }) })
    return () => { cancelAnimationFrame(frame); cancelAnimationFrame(secondFrame) }
  }, [state?.screen, state?.check_id])
  const protocol = state?.protocol
  const step = !state || state.screen === 'start' ? 0 : state.screen === 'supplies' ? 1 : state.screen === 'prep' ? state.prep_index + 2 : protocol.prep_steps.length + 2
  const frame = { step, totalSteps: (protocol?.prep_steps.length || 0) + 2,
    onHelp: () => act('help'), onBack: ['supplies', 'prep', 'check'].includes(state?.screen) ? () => act('back') : null }
  let content
  if (!state) content = <Frame title="Connecting to station…"><p className="body-text">Waiting for the local controller.</p></Frame>
  else if (state.screen === 'start') content = <Start {...frame} medication={protocol.medication} onBegin={() => act('begin')} />
  else if (state.screen === 'supplies') content = <Supplies {...frame} item={protocol.supplies[state.supply_index]} index={state.supply_index} total={protocol.supplies.length} missing={state.missing} onConfirm={() => act('confirm')} onMissing={() => act('missing')} />
  else if (state.screen === 'prep') content = <PrepStep {...frame} prep={protocol.prep_steps[state.prep_index]} onNext={() => act('next')} />
  else if (['check', 'checking'].includes(state.screen)) content = <SyringeCheck {...frame} checking={state.screen === 'checking'} simulated={state.simulated} seated={state.seated} hardwareSeat={state.hardware_seat} onSeat={() => act('seat')} onCheck={() => act('capture')} />
  else if (state.screen === 'result') content = <Result {...frame} result={state.result} onContinue={() => act('complete')} onRetry={() => act('retry')} onReset={() => act('reset')} />
  else content = <Done {...frame} onFinish={() => act('reset')} />
  return <div className="stage">
    <div className="device" aria-busy={pending}>
      <fieldset className="station-controls" disabled={pending || Boolean(error) || state?.help_open}>{content}</fieldset>
      {state?.help_open && !error && <HelpOverlay onClose={() => act('close_help')} onReset={() => act('reset')} />}
      {error && <div className="overlay"><div className="overlay-card" role="alert">
        <h1 className="title">Station unavailable</h1><p className="body-text">{error}</p>
        <button className="btn btn-primary" onClick={refresh}>Reconnect</button>
      </div></div>}
    </div>
    <p className="station-mode">{state?.simulated ? 'PHOTO REPLAY · simulated seating' : 'HARDWARE · local processing'} · Bench prototype</p>
  </div>
}
