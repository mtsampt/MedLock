import Frame from '../components/Frame.jsx'

// One preparation action per screen. Content comes from protocol.js.

export default function PrepStep({ prep, onNext, ...frame }) {
  return (
    <Frame
      {...frame}
      title={prep.title}
      primary={<button className="btn btn-primary" data-action="next" onClick={onNext}>Done, next</button>}
    >
      <p className="body-text">{prep.detail}</p>
      {prep.warning && (
        <div className="callout callout-warn" role="alert">
          <span aria-hidden>⚠</span> {prep.warning}
        </div>
      )}
    </Frame>
  )
}
