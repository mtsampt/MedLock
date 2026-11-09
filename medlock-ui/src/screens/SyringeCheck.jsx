import Frame from '../components/Frame.jsx'
export default function SyringeCheck({ checking, simulated, seated, hardwareSeat, onSeat, onCheck, ...frame }) {
  return <Frame {...frame} onBack={checking ? null : frame.onBack} backInHeader={simulated}
    title={checking ? 'Checking syringe…' : 'Place syringe in dock'}
    primary={<button className="btn btn-primary" data-action="capture" onClick={onCheck} disabled={checking}>Check syringe</button>}
    secondary={simulated && !checking ? <button className="btn btn-secondary" data-action="seat" onClick={onSeat}>{seated ? 'Unseat' : 'Seat (demo)'}</button> : null}>
    {checking ? <div className="checking"><div className="spinner" aria-hidden /><p className="body-text">Hold still while the camera checks.</p></div> : <p className="body-text">{simulated ? (seated ? 'Seated in simulation. Uses a saved photo.' : 'Tap Seat to simulate the dock sensor.') : hardwareSeat ? 'Keep the full barrel visible and hold still.' : 'Seat sensor unavailable. Configure hardware before checking.'}</p>}
  </Frame>
}
