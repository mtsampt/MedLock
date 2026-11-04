import argparse
import json
from pathlib import Path

from .store import Store


def main():
    parser=argparse.ArgumentParser(description='MedLock local image lab')
    parser.add_argument('command',choices=['seed','train','serve'])
    parser.add_argument('--data',type=Path,default=Path(__file__).parent/'data')
    parser.add_argument('--manifest',type=Path,default=Path(__file__).parent.parent/'outputs/medlock-pilot-2026-10-21/manifest.json')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    store=Store(args.data)
    if args.command=='seed':
        print(json.dumps({'added':store.seed(args.manifest),'counts':store.counts()}))
    elif args.command=='train':
        from .model import train
        report=train(store,lambda p,m:print(f'{p}% {m}',flush=True))
        print(json.dumps({k:v for k,v in report.items() if k not in {'parameters','snapshot'}}))
    else:
        from .app import create_app
        create_app(args.data).run(host='127.0.0.1',port=args.port,threaded=True,debug=False,use_reloader=False)


if __name__=='__main__': main()
