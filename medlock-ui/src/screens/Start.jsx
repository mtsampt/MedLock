import Frame from '../components/Frame.jsx'
export default function Start({ onBegin, medication, ...frame }) {
  return <Frame {...frame} title={medication} primary={<button className="btn btn-primary" data-action="begin" onClick={onBegin}>Begin</button>}>
    <p className="body-text">Bench preparation flow. Camera results are experimental.</p>
    <p className="body-text">No dose time is configured.</p>
  </Frame>
}
