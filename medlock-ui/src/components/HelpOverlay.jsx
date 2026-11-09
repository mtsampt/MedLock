export default function HelpOverlay({ onClose, onReset }) {
  return <div className="overlay"><div className="overlay-card" role="dialog" aria-modal="true" aria-label="Station help">
    <h1 className="title">Station help</h1>
    <p className="body-text">Keep the full syringe barrel visible and still. Retry if seating, focus or capture fails. Volume needs calibration.</p>
    <div className="overlay-actions"><button className="btn btn-secondary" data-action="reset" onClick={onReset}>Reset flow</button><button className="btn btn-primary" data-action="close_help" onClick={onClose}>Back</button></div>
  </div></div>
}
