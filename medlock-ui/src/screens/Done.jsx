import Frame from '../components/Frame.jsx'
export default function Done({ onFinish, ...frame }) {
  return <Frame {...frame} onBack={null} title="Bench check recorded" primary={<button className="btn btn-primary" data-action="reset" onClick={onFinish}>Finish</button>}>
    <p className="body-text">This prototype result does not authorize an injection.</p>
  </Frame>
}
