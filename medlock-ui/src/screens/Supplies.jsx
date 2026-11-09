import Frame from '../components/Frame.jsx'
export default function Supplies({ item, index, total, missing, onConfirm, onMissing, ...frame }) {
  return <Frame {...frame} title={missing ? `Get the ${item.label.toLowerCase()}` : item.label}
    primary={missing ? <button className="btn btn-primary" data-action="confirm" onClick={onConfirm}>I have it now</button> : null}>
    <p className="eyebrow">Manual confirmation · {index + 1} of {total}</p>
    {missing ? <p className="body-text">Find this item before continuing.</p> : <>
      <p className="body-text">Do you have this?</p>
      <div className="choice-row"><button className="btn btn-choice" data-action="confirm" onClick={onConfirm}>✓ Yes</button><button className="btn btn-choice" data-action="missing" onClick={onMissing}>✕ No</button></div>
    </>}
  </Frame>
}
