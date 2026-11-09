import Frame from '../components/Frame.jsx'
export default function Result({ result, onContinue, onRetry, onReset, ...frame }) {
  const pass = result.verdict === 'pass'
  const air = result.air_detected === true && result.verdict === 'fix'
  const noAirOnly = result.reason_code === 'volume_unverified'
  const heading = pass ? 'Bench checks passed' : air ? 'Visible air detected' : noAirOnly ? 'No visible air' : result.verdict === 'fix' ? 'Needs adjustment' : 'Unable to verify'
  const detail = noAirOnly ? 'Volume not verified.' : pass ? 'Experimental result; not injection clearance.' : result.reason
  return <Frame {...frame} onBack={null}
    primary={<button className="btn btn-primary" data-action={pass ? "complete" : "retry"} onClick={pass ? onContinue : onRetry}>{pass ? 'Continue' : 'Check again'}</button>}
    secondary={<button className="btn btn-secondary" data-action="reset" onClick={onReset}>Reset</button>}>
    <div className={`result result-${result.verdict}`} role="status">
      <div className="result-head"><span className="result-symbol" aria-hidden>{pass ? '✓' : air ? '!' : '?'}</span><h1 className="result-heading">{heading}</h1></div>
      <p className="result-reason">{detail}</p>
      {result.volume_ml != null && <p className="body-text">Barrel volume: {result.volume_ml.toFixed(2)} mL</p>}
    </div>
  </Frame>
}
