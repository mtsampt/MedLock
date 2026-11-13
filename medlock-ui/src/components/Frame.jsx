import { useEffect } from 'react'

// When the screen changes, move the knob/keyboard starting point back to the
// top of the device, so the next turn always lands on Help, then the body
// buttons, then the footer. (blur() alone keeps the old starting point.)
export function useResetFocus(deps) {
  useEffect(() => {
    document.querySelector('.device')?.focus({ preventScroll: true })
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
}

// Shared layout for every screen: progress bar on top, Help top-right,
// one instruction in the middle, Back bottom-left, primary action bottom-right.

export default function Frame({ step, totalSteps, onBack, onHelp, title, children, primary, secondary }) {
  return (
    <div className="frame">
      <header className="frame-top">
        {step > 0 ? (
          <div className="progress" aria-label={`Step ${step} of ${totalSteps}`}>
            <span className="progress-label">Step {step} of {totalSteps}</span>
            <div className="progress-track">
              {Array.from({ length: totalSteps }, (_, i) => (
                <span key={i} className={i < step ? 'progress-seg done' : 'progress-seg'} />
              ))}
            </div>
          </div>
        ) : (
          <span className="brand">MedLock</span>
        )}
        {onHelp && (
          <button className="btn btn-ghost" onClick={onHelp}>? Help</button>
        )}
      </header>

      <main className="frame-body">
        {title && <h1 className="title">{title}</h1>}
        {children}
      </main>

      <footer className="frame-bottom">
        {onBack ? <button className="btn btn-secondary" onClick={onBack}>← Back</button> : <span />}
        <div className="frame-actions">
          {secondary}
          {primary}
        </div>
      </footer>
    </div>
  )
}
