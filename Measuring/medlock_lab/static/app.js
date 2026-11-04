const $=id=>document.getElementById(id);
let current=null, statusData=null, library=[], busy=false, previousJob='idle';
const labelName=label=>label==='air'?'Air':label==='no_air'?'No visible air':'Unlabeled';
async function api(path,options={}){const r=await fetch(path,options);let data;try{data=await r.json()}catch{throw new Error('The local server did not return a valid response.')}if(!r.ok)throw new Error(data.error||'Request failed.');return data;}
let toastTimer;
function toast(message,error=false){$('toast').textContent=message;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
function setBusy(value){busy=value;$('dropzone').setAttribute('aria-busy',String(value));$('label-air').disabled=value||!current;$('label-no-air').disabled=value||!current;}
async function refresh(){
 try{
  const s=await api('/api/status');statusData=s;
  $('count-total').textContent=s.counts.air+s.counts.no_air;$('count-air').textContent=s.counts.air;$('count-no-air').textContent=s.counts.no_air;
  $('pending-badge').textContent=s.counts.pending;$('train').disabled=s.job.state==='running'||s.counts.pending===0;
  $('train-hint').textContent=s.job.state==='running'?'Training in the background…':s.counts.pending?`${s.counts.pending} new or corrected label${s.counts.pending===1?'':'s'} ready`:'All saved labels are in the current model';
  $('model-count').textContent=s.model?`${s.model.training_count} photos`:'No model';
  $('model-age').textContent=s.model?`Trained ${new Date(s.model.trained_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`:'Add labels to begin';
  const e=s.model?.evaluation;
  $('evaluation-description').textContent=e?.available?`${e.kind}: ${e.tested} photos checked with their group excluded from training. These are exploratory results, not independent validation.`:e?.reason||'No model has been trained yet.';
  $('eval-missed').textContent=e?.available?e.missed_air:'—';$('eval-false').textContent=e?.available?e.false_air:'—';
  $('job-panel').hidden=s.job.state==='idle';$('job-message').textContent=s.job.message;$('job-progress').value=s.job.progress;$('job-percent').textContent=s.job.state==='failed'?'Failed':`${s.job.progress}%`;$('job-spinner').hidden=s.job.state!=='running';
  if(previousJob==='running'&&s.job.state==='complete'){toast('Training complete. The new model is active.');await refreshLibrary();}
  if(previousJob==='running'&&s.job.state==='failed')toast(s.job.message,true);
  previousJob=s.job.state;
 }catch(e){$('train-hint').textContent='Local server unavailable. Restart the Image Lab.';}
}
async function refreshLibrary(){const result=await api('/api/images');library=result.images;$('library-count').textContent=library.length;renderLibrary();}
function renderLibrary(){const filter=$('filter').value;const shown=library.filter(r=>filter==='all'||filter==='pending'&&r.pending||filter==='unlabeled'&&!r.label||r.label===filter);$('library').replaceChildren();$('library-empty').hidden=!!shown.length;for(const r of shown){const button=document.createElement('button');button.className='photo-card'+(!r.label?' unlabeled':'');button.setAttribute('aria-label',`${r.name}, ${labelName(r.label)}. Open for review.`);const img=document.createElement('img');img.src=r.processed_url;img.alt='';img.loading='lazy';const body=document.createElement('div');body.className='card-body';const name=document.createElement('span');name.className='card-name';name.textContent=r.name;const label=document.createElement('span');label.className='card-label';const dot=document.createElement('i');dot.className=`legend-dot ${r.label==='air'?'air':'clear'}`;label.append(dot,document.createTextNode(labelName(r.label)));if(r.pending){const pending=document.createElement('i');pending.className='pending-dot';pending.title='Not yet included in the active model';label.append(pending)}body.append(name,label);button.append(img,body);button.addEventListener('click',async()=>{try{const response=await fetch(r.preview_url);const blob=await response.blob();await upload(new File([blob],r.name,{type:'image/jpeg'}),r)}catch(e){toast(e.message,true)}});$('library').append(button);}}
async function upload(file,existing=null){
 if(busy)return;
 if(file.size>20*1024*1024){toast('Choose a photo smaller than 20 MB.',true);return;}
 setBusy(true);current=null;$('label-air').disabled=true;$('label-no-air').disabled=true;$('upload-status').textContent='Cleaning & predicting…';$('filename').textContent=file.name;$('label-feedback').textContent='';
 $('result').hidden=true;$('result-empty').hidden=false;$('result-empty').querySelector('h3').textContent='Looking closer…';
 try{
  let result;
  if(existing){result=await api(`/api/images/${existing.id}/inspect`);}
  else{const form=new FormData();form.append('image',file);form.append('session',$('session').value);result=await api('/api/upload',{method:'POST',body:form});}
  current=result;$('drop-empty').hidden=true;$('original-preview').hidden=false;$('original-preview').src=result.preview_url;$('replace-hint').hidden=false;
  $('result-empty').hidden=true;$('result').hidden=false;$('cleaned-preview').src=result.processed_url;
  $('prediction-version').textContent=result.prediction?result.prediction.model_version.split('-').slice(-1)[0]:'No model';
  const p=result.prediction;$('prediction-label').textContent=p?labelName(p.label):'Train a model first';$('prediction-symbol').textContent=p?.label==='air'?'◌':'✓';$('prediction-symbol').className='prediction-symbol'+(p?.label==='air'?' air':'');
  $('prediction-time').textContent=p?`${p.seconds.toFixed(2)} s · experimental prediction`:'';
  $('air-score').textContent=p?p.air_score.toFixed(2):'—';$('score-meter').value=p?.air_score||0;
  $('seen-notice').hidden=!result.duplicate&&!p?.seen_in_training;
  $('seen-notice').textContent=p?.seen_in_training?'Already used to train this model. This prediction is not an independent test.':result.duplicate?'This exact image is already in your library. It will not be added twice.':'';
  $('quality-note').textContent=result.cleaning.warnings.join(' ')||'Check the crop before confirming a label.';
  $('upload-status').textContent='Ready to label';paintLabel(result.label);
  await refreshLibrary();await refresh();
 }catch(e){$('upload-status').textContent='Could not process';$('result').hidden=true;$('result-empty').hidden=false;$('result-empty').querySelector('h3').textContent='Try a clearer photo.';toast(e.message,true);}
 finally{setBusy(false);$('file').value='';}
}
function paintLabel(label){$('label-air').classList.toggle('selected',label==='air');$('label-no-air').classList.toggle('selected',label==='no_air');$('label-air').setAttribute('aria-pressed',String(label==='air'));$('label-no-air').setAttribute('aria-pressed',String(label==='no_air'));$('label-feedback').textContent=label?`Saved label: ${labelName(label)}. You can correct it with either button.`:'Your label is saved only when you choose a button.';}
async function saveLabel(label){if(!current||busy)return;setBusy(true);try{const r=await api(`/api/images/${current.id}/label`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label})});current.label=r.label;paintLabel(r.label);toast(`Saved as ${labelName(label)}. Train with new data when ready.`);await refresh();await refreshLibrary();}catch(e){toast(e.message,true)}finally{setBusy(false)}}
$('label-air').onclick=()=>saveLabel('air');$('label-no-air').onclick=()=>saveLabel('no_air');
$('dropzone').onclick=()=>{if(!busy)$('file').click()};$('dropzone').onkeydown=e=>{if(e.target===$('dropzone')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();if(!busy)$('file').click()}};
$('file').onchange=e=>{if(e.target.files[0])upload(e.target.files[0])};
for(const name of ['dragenter','dragover'])$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.add('dragging')});
for(const name of ['dragleave','drop'])$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.remove('dragging')});
$('dropzone').addEventListener('drop',e=>{if(e.dataTransfer.files.length>1)toast('One photo at a time. Please confirm each label.');if(e.dataTransfer.files[0])upload(e.dataTransfer.files[0])});
document.addEventListener('dragover',e=>e.preventDefault());document.addEventListener('drop',e=>e.preventDefault());
$('filter').onchange=renderLibrary;
$('train').onclick=async()=>{if($('train').disabled)return;$('train').disabled=true;try{await api('/api/train',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});previousJob='running';await refresh()}catch(e){toast(e.message,true);await refresh()}};
refresh();refreshLibrary().catch(e=>toast(e.message,true));setInterval(refresh,2000);
