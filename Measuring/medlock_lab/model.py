"""Frozen MobileNetV2 embeddings + balanced, regularized logistic regression."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .imaging import PREPROCESS_VERSION, tensor_array
from .store import now

_backbone = None
_inference_lock = threading.Lock()


def backbone(store):
    global _backbone
    if _backbone is None:
        import torch
        from torchvision.models import MobileNet_V2_Weights, mobilenet_v2
        torch.set_num_threads(4)
        weights=MobileNet_V2_Weights.IMAGENET1K_V2
        path=store.root/'weights'/Path(weights.url).name
        if not path.exists():
            temp=path.with_suffix('.download')
            subprocess.run(['curl','--fail','--location','--retry','2','--max-time','180',weights.url,'-o',str(temp)],check=True)
            expected=path.stem.rsplit('-',1)[-1]
            if not hashlib.sha256(temp.read_bytes()).hexdigest().startswith(expected):
                temp.unlink(missing_ok=True)
                raise RuntimeError('Pretrained weight checksum failed.')
            os.replace(temp,path)
        net=mobilenet_v2(weights=None)
        net.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
        net.classifier=torch.nn.Identity()
        net.eval()
        for p in net.parameters(): p.requires_grad_(False)
        _backbone=net
    return _backbone


def features(store, rows, progress=None):
    import torch
    output=[]
    with _inference_lock:
        net=backbone(store)
        for i,r in enumerate(rows):
            path=store.root/'features'/f'{r["pixel_hash"]}-{PREPROCESS_VERSION}.npy'
            if path.exists():
                f=np.load(path,allow_pickle=False)
            else:
                im=Image.open(store.root/'processed'/f'{r["id"]}.png').convert('RGB')
                with torch.inference_mode():
                    f=net(torch.from_numpy(tensor_array(im)).unsqueeze(0)).numpy()[0]
                np.save(path,f,allow_pickle=False)
            output.append(f)
            if progress: progress(15+int(50*(i+1)/len(rows)),f'Extracting image features · {i+1}/{len(rows)}')
    return np.stack(output)


def classifier():
    # All normalization is fit inside each training fold, never on held-out rows.
    return make_pipeline(StandardScaler(), LogisticRegression(C=.03,class_weight='balanced',max_iter=1000,random_state=42))


def evaluate(x,y,rows):
    sessions=sorted(set(r['session'] for r in rows))
    if len(sessions)>1:
        groups=np.array([r['session'] for r in rows]); kind='Leave-session-out'
    else:
        groups=np.array([r['eval_group'] for r in rows]); kind='Leave-fill-block-out (same session)'
    predictions=np.full(len(y),-1,dtype=int)
    folds=[]
    for group in sorted(set(groups)):
        test=groups==group; train=~test
        if len(set(y[train]))<2 or not train.any(): continue
        fit=classifier().fit(x[train],y[train])
        predictions[test]=fit.predict(x[test])
        folds.append({'group':str(group),'train_count':int(train.sum()),'test_count':int(test.sum()),'train_ids':[r['id'] for r,t in zip(rows,train) if t],'test_ids':[r['id'] for r,t in zip(rows,test) if t]})
    valid=predictions>=0
    if not valid.any() or len(set(y[valid]))<2:
        return {'kind':kind,'available':False,'reason':'Need independent groups with both classes in the training folds.','folds':folds}
    tn,fp,fn,tp=confusion_matrix(y[valid],predictions[valid],labels=[0,1]).ravel()
    return {
        'kind':kind,'available':True,'tested':int(valid.sum()),'total':len(y),
        'balanced_accuracy':round(float(balanced_accuracy_score(y[valid],predictions[valid])),4),
        'air_recall':round(float(tp/(tp+fn)),4) if tp+fn else None,
        'missed_air':int(fn),'false_air':int(fp),
        'matrix':{'true_no_air':int(tn),'false_air':int(fp),'missed_air':int(fn),'true_air':int(tp)},
        'folds':folds,'warning':'Exploratory grouped check. Not a validated independent test; no Pi-camera data.',
        'predictions':[{'id':r['id'],'actual':r['label'],'prediction':('air' if p else 'no_air') if p>=0 else None} for r,p in zip(rows,predictions)]}


def train(store, progress=lambda p,m: None):
    started=time.time()
    rows=store.all(labeled=True)
    if len(rows)<4 or len(set(r['label'] for r in rows))<2:
        raise ValueError('Training needs labeled examples of both air and no air.')
    snapshot={r['id']:r['revision'] for r in rows}
    progress(10,'Snapshot saved. Preparing labeled images…')
    x=features(store,rows,progress)
    y=np.array([r['label']=='air' for r in rows],dtype=int)
    progress(70,'Checking held-out groups…')
    evaluation=evaluate(x,y,rows)
    fit=classifier().fit(x,y)
    scale,head=fit.steps[0][1],fit.steps[1][1]
    version='v-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:4]
    folder=store.root/'models'/version;folder.mkdir()
    parameters={'mean':scale.mean_.tolist(),'scale':scale.scale_.tolist(),'coef':head.coef_[0].tolist(),'intercept':float(head.intercept_[0]),'preprocess_version':PREPROCESS_VERSION}
    (folder/'classifier.json').write_text(json.dumps(parameters))
    progress(85,'Exporting standalone CPU model…')
    import torch
    class DeploymentModel(torch.nn.Module):
        def __init__(self,net):
            super().__init__(); self.net=net
            self.register_buffer('mean',torch.tensor(scale.mean_,dtype=torch.float32))
            self.register_buffer('scale',torch.tensor(scale.scale_,dtype=torch.float32))
            self.register_buffer('coef',torch.tensor(head.coef_[0],dtype=torch.float32))
            self.register_buffer('intercept',torch.tensor(head.intercept_[0],dtype=torch.float32))
        def forward(self,inputs):
            f=self.net(inputs)
            return torch.sigmoid((((f-self.mean)/self.scale)*self.coef).sum(1)+self.intercept)
    with _inference_lock,torch.inference_mode():
        deployed=DeploymentModel(backbone(store)).eval()
        traced=torch.jit.trace(deployed,torch.zeros(1,3,224,224))
        traced.save(str(folder/'model_cpu.pt'))
    metadata={
        'version':version,'trained_at':now(),'training_count':len(rows),
        'air_count':int(y.sum()),'no_air_count':int((1-y).sum()),
        'snapshot':snapshot,'architecture':'MobileNetV2 ImageNet V2 features + balanced logistic regression',
        'preprocess_version':PREPROCESS_VERSION,'evaluation':evaluation,
        'seconds':round(time.time()-started,2),'parameters':parameters,
        'threshold':.5,'export':'model_cpu.pt',
        'limitations':['27-image, single-session pilot at initialization.','Scores are uncalibrated model outputs, not safety probabilities.','Supports similar portrait, tip-down syringe images.','Not tested on Raspberry Pi or final device camera.']}
    (folder/'report.json').write_text(json.dumps(metadata,indent=2))
    store.activate(metadata)
    progress(100,'Model ready')
    return metadata


def predict(store,row):
    model=store.active_model()
    if not model: raise ValueError('Train the first model before predicting.')
    started=time.time()
    x=features(store,[row])[0].astype(np.float64)
    p=model['parameters']
    z=np.dot((x-np.array(p['mean']))/np.array(p['scale']),np.array(p['coef']))+p['intercept']
    score=float(1/(1+np.exp(-np.clip(z,-40,40))))
    return {'label':'air' if score>=model['threshold'] else 'no_air',
            'air_score':round(score,5),'model_version':model['version'],
            'seen_in_training':row['id'] in model['snapshot'],
            'seconds':round(time.time()-started,3),'score_note':'Uncalibrated model score; not a safety probability.'}
