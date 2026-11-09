"""Evaluate recorded physical bench samples against report targets; never promote replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from medlock_device.trials import evaluate, read_jsonl
from medlock_device.volume import VolumeEstimator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trials',type=Path)
    p.add_argument('--calibration',type=Path)
    p.add_argument('--setup-id',help='Required with calibration; must match the actual test setup.')
    p.add_argument('--min-latency-trials',type=int)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    try:
        calibration=VolumeEstimator(args.calibration,args.setup_id) if args.calibration else None
        result=evaluate(read_jsonl(args.trials),calibration=calibration.calibration if calibration else None,
                        calibration_version=calibration.version if calibration else None,min_latency_trials=args.min_latency_trials)
        result['trial_file_sha256']=hashlib.sha256(args.trials.read_bytes()).hexdigest()
        result['calibration_sha256']=calibration.version if calibration else None
        with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    except (ValueError,OSError) as exc:p.error(str(exc))
    print(json.dumps({key:value['status'] for key,value in result['criteria'].items()},indent=2))


if __name__=='__main__':main()
