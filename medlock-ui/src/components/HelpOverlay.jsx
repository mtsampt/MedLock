export default function HelpOverlay({ onClose }) {
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Help">
      <div className="overlay-card">
        <h2 className="title">Need help?</h2>
        <div className="image-placeholder small">Video: how to prepare this step</div>
        <div className="overlay-actions">
          <button className="btn btn-secondary" onClick={() => alert('Clinic phone number goes here')}>
            Call the clinic
          </button>
          <button className="btn btn-primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
