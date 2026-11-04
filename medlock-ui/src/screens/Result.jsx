import Frame from '../components/Frame.jsx'

// Every verdict uses color + symbol + text, so it still reads for
// colorblind users and on a dim screen.

const VIEWS = {
  pass: { symbol: '✓', heading: 'Ready to inject', cls: 'result-pass' },
  fix: { symbol: '!', heading: 'Needs a fix', cls: 'result-fix' },
  unable: { symbol: '?', heading: "Couldn't check", cls: 'result-unable' },
}

export default function Result({ result, onContinue, onRetry, ...frame }) {
  // Anything unexpected from the backend is treated as "unable", never as a pass.
  const view = VIEWS[result.verdict] ?? VIEWS.unable
  const isPass = result.verdict === 'pass'

  return (
    <Frame
      {...frame}
      onBack={null}
      primary={
        isPass ? (
          <button className="btn btn-primary" onClick={onContinue}>Continue</button>
        ) : (
          <button className="btn btn-primary" onClick={onRetry}>
            {result.verdict === 'fix' ? 'Check again' : 'Try again'}
          </button>
        )
      }
      secondary={
        result.verdict === 'unable' && (
          <button className="btn btn-secondary" onClick={() => alert('Clinic contact goes here')}>
            Contact clinic
          </button>
        )
      }
    >
      <div className={`result ${view.cls}`} role="status">
        <div className="result-head">
          <div className="result-symbol" aria-hidden>{view.symbol}</div>
          <div>
            <h1 className="result-heading">{view.heading}</h1>
            {!isPass && <p className="result-reason">{result.reason}</p>}
          </div>
        </div>
        {result.action && <p className="body-text">{result.action}</p>}
        {isPass && <p className="body-text">Volume and air checks passed.</p>}
      </div>
    </Frame>
  )
}
