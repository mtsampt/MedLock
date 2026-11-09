"""Record one completed station check with independently measured bench labels."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from medlock_device.trials import append_trial, get_state, make_trial, read_jsonl


def boolean(value):
    if value not in ('true','false'): raise argparse.ArgumentTypeError('Use true or false.')
    return value=='true'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--station',default='http://127.0.0.1:8767')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--test',action='append',required=True,choices=['volume','air','combined','latency','unsupported'])
    p.add_argument('--collection-session',required=True)
    p.add_argument('--syringe-id',required=True)
    p.add_argument('--supported',required=True,type=boolean)
    p.add_argument('--expected-valid',type=boolean)
    p.add_argument('--reference-volume-ml',type=float)
    p.add_argument('--reference-air-ml',type=float)
    p.add_argument('--blinded',action='store_true',help='Declare that reference labels came from the blinded test protocol.')
    p.add_argument('--capture-root',type=Path)
    p.add_argument('--events',type=Path,help='Station session-events.jsonl for display acknowledgement timings.')
    p.add_argument('--trial-id')
    args=p.parse_args()
    try:
        row=make_trial(get_state(args.station),tests=args.test,collection_session=args.collection_session,
                       syringe_id=args.syringe_id,supported=args.supported,expected_valid=args.expected_valid,
                       reference_volume_ml=args.reference_volume_ml,reference_air_ml=args.reference_air_ml,
                       blinded=args.blinded,capture_root=args.capture_root,
                       events=read_jsonl(args.events) if args.events else [],trial_id=args.trial_id)
        append_trial(args.output,row)
    except (ValueError,OSError) as exc:p.error(str(exc))
    print(json.dumps({'trial_id':row['trial_id'],'check_id':row['check_id'],'evidence':row['evidence'],'output':str(args.output)},indent=2))


if __name__=='__main__':main()
