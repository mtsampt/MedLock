"""Run on the training laptop, never needed on the Pi."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import torch
from PIL import Image
from medlock_lab.imaging import PREPROCESS_VERSION, tensor_array
from medlock_lab.model import backbone
from medlock_lab.store import Store


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=Path('medlock_lab/data'))
    p.add_argument('--output', type=Path, default=Path('outputs/pi-bundle'))
    args = p.parse_args()
    store = Store(args.data)
    model = store.active_model()
    if not model:
        p.error('Train a model in the laptop lab first.')
    if args.output.exists():
        p.error('Output already exists. Choose a new directory to preserve old bundles.')
    out = args.output
    out.mkdir(parents=True)
    try:
        net = backbone(store)
        torch.onnx.export(net, torch.zeros(1, 3, 224, 224), str(out/'features.onnx'),
                          input_names=['image'], output_names=['features'], opset_version=12,
                          dynamo=False)
        # Some exporters emit aliases of identical constants as Identity nodes;
        # OpenCV 4.x importers require them to be resolved explicitly.
        import onnx
        graph = onnx.load(str(out/'features.onnx'))
        aliases = {}
        for node in list(graph.graph.node):
            for i, name in enumerate(node.input):
                while name in aliases:
                    name = aliases[name]
                node.input[i] = name
            if node.op_type == 'Identity':
                aliases[node.output[0]] = node.input[0]
                graph.graph.node.remove(node)
        onnx.checker.check_model(graph)
        onnx.save(graph, str(out/'features.onnx'))
        (out/'classifier.json').write_text(json.dumps(model['parameters']))
        manifest = {k:model[k] for k in ['version','training_count','threshold','architecture']}
        manifest.update(preprocess_version=PREPROCESS_VERSION, runtime='OpenCV DNN + NumPy; CPU',
                        input_shape=[1,3,224,224], hardware_tested=False,
                        sha256={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
                                for name in ['features.onnx','classifier.json']})
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
        from medlock_device.runtime import Engine
        engine = Engine(out)
        errors=[]
        for row in store.all(labeled=True):
            im=Image.open(store.root/'processed'/f'{row["id"]}.png').convert('RGB')
            a=tensor_array(im)[None]
            with torch.inference_mode():
                expected=net(torch.from_numpy(a)).numpy().reshape(-1).astype(np.float64)
            head=model['parameters']
            z=np.dot((expected-np.array(head['mean']))/head['scale'],head['coef'])+head['intercept']
            score=float(1/(1+np.exp(-np.clip(z,-40,40))))
            actual=engine.predict(im)['air_score']
            errors.append(abs(score-actual))
            if abs(score-actual)>1e-4 or (score>=model['threshold'])!=(actual>=model['threshold']):
                raise RuntimeError('OpenCV/PyTorch prediction parity failed.')
        report={'images_checked':len(errors),'max_score_difference':max(errors),
                'environment':'training laptop; not a Raspberry Pi benchmark'}
        (out/'parity.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'bundle':str(out),'size_mb':round(sum(f.stat().st_size for f in out.iterdir())/1e6,2),**report},indent=2))
    except Exception:
        shutil.rmtree(out)
        raise


if __name__ == '__main__':
    main()
