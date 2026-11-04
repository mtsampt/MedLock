from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from .imaging import ImageProblem
from .store import Store


def public_model(model):
    if not model: return None
    report={k:v for k,v in model.items() if k not in {'parameters','snapshot'}}
    report['evaluation']={k:v for k,v in model['evaluation'].items() if k not in {'folds','predictions'}}
    return report


def create_app(data_root=None, *, predictor=None, trainer=None):
    from .model import predict, train
    predictor=predictor or predict; trainer=trainer or train
    app=Flask(__name__,static_folder='static',static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH']=20*1024*1024
    store=Store(Path(data_root) if data_root else Path(__file__).parent/'data')
    app.config['STORE']=store
    training_lock=threading.Lock()
    state_lock=threading.Lock()
    job={'state':'idle','progress':0,'message':'Ready'}

    @app.before_request
    def same_origin():
        if request.method in {'POST','PUT','DELETE','PATCH'}:
            origin=request.headers.get('Origin')
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error='This local app only accepts changes from its own window.'),403

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'"
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc,HTTPException):
            message='File is too large. Upload a photo smaller than 20 MB.' if exc.code==413 else exc.description
            return jsonify(error=message),exc.code
        if isinstance(exc,(ImageProblem,ValueError)):
            return jsonify(error=str(exc)),422
        if isinstance(exc,KeyError): return jsonify(error='Photo not found.'),404
        traceback.print_exc()
        return jsonify(error='The operation failed. Your existing labels and model are preserved. See the server log.'),500

    @app.get('/')
    def index(): return app.send_static_file('index.html')

    @app.get('/api/status')
    def status():
        with state_lock: current=job.copy()
        return jsonify(counts=store.counts(),model=public_model(store.active_model()),job=current)

    @app.get('/api/images')
    def images():
        model=store.active_model();snapshot=model.get('snapshot',{}) if model else {}
        return jsonify(images=[{
            'id':r['id'],'name':r['name'],'label':r['label'],'session':r['session'],
            'source':r['source'],'pending':r['label'] is not None and snapshot.get(r['id'])!=r['revision'],
            'label_basis':r['label_basis'],
            'preview_url':f'/api/images/{r["id"]}/preview',
            'processed_url':f'/api/images/{r["id"]}/processed',
        } for r in store.all()])

    @app.get('/api/images/<image_id>/<kind>')
    def image(image_id,kind):
        row=store.get(image_id)
        if not row: raise KeyError(image_id)
        if kind=='inspect':
            return jsonify(id=row['id'],name=row['name'],label=row['label'],duplicate=True,
                cleaning=json.loads(row['cleaning']),prediction=predictor(store,row) if store.active_model() else None,
                preview_url=f'/api/images/{row["id"]}/preview',processed_url=f'/api/images/{row["id"]}/processed')
        if kind=='preview': return send_file(store.root/'previews'/f'{image_id}.jpg',mimetype='image/jpeg')
        if kind=='processed': return send_file(store.root/'processed'/f'{image_id}.png',mimetype='image/png')
        raise KeyError(kind)

    @app.post('/api/upload')
    def upload():
        file=request.files.get('image')
        if not file or not file.filename: raise ValueError('Choose an image first.')
        session=request.form.get('session','Session 02').strip()[:80] or 'Session 02'
        row,duplicate=store.add(file.read(),file.filename,session=session)
        result=predictor(store,row) if store.active_model() else None
        return jsonify(id=row['id'],name=row['name'],label=row['label'],duplicate=duplicate,
            cleaning=json.loads(row['cleaning']),prediction=result,
            preview_url=f'/api/images/{row["id"]}/preview',processed_url=f'/api/images/{row["id"]}/processed')

    @app.post('/api/images/<image_id>/label')
    def label(image_id):
        body=request.get_json(silent=True) or {}
        row=store.label(image_id,body.get('label'))
        return jsonify(id=row['id'],label=row['label'],counts=store.counts())

    @app.post('/api/train')
    def start_training():
        if not training_lock.acquire(blocking=False):
            return jsonify(error='Training is already running.'),409
        if store.counts()['pending']==0 and store.active_model():
            training_lock.release()
            return jsonify(error='No new or corrected labels to train with.'),409
        counts=store.counts()
        if not counts['air'] or not counts['no_air']:
            training_lock.release()
            raise ValueError('Add examples of both air and no air first.')
        def progress(p,m):
            with state_lock: job.update(state='running',progress=p,message=m)
        def work():
            try:
                trainer(store,progress)
                with state_lock: job.update(state='complete',progress=100,message='New model is ready. Drop a photo to test it.')
            except Exception as exc:
                traceback.print_exc()
                with state_lock: job.update(state='failed',progress=0,message=f'Training failed: {exc}. Previous model kept.')
            finally: training_lock.release()
        progress(1,'Starting a new training snapshot…')
        threading.Thread(target=work,daemon=True,name='model-training').start()
        return jsonify(started=True),202

    @app.get('/api/download/<kind>')
    def download(kind):
        if kind=='labels':
            store.export_labels()
            return send_file(store.root/'labels.csv',as_attachment=True,download_name='medlock-labels.csv')
        model=store.active_model()
        if not model: raise ValueError('No model has been trained yet.')
        folder=store.root/'models'/model['version']
        if kind=='model': return send_file(folder/'model_cpu.pt',as_attachment=True,download_name='medlock-model-cpu.pt')
        if kind=='report': return send_file(folder/'report.json',as_attachment=True,download_name='medlock-training-report.json')
        raise KeyError(kind)

    return app
