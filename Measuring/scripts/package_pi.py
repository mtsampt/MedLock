"""Assemble the unified offline Pi application, without training dependencies."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess


def package(out, ui, include_replay=True):
    root = Path(__file__).resolve().parents[1]
    repo = root.parent
    if out.exists():
        raise ValueError('Deployment folder already exists; preserve or move it before rebuilding.')
    if not (ui/'index.html').is_file():
        raise ValueError('Build medlock-ui first (npm ci && npm run build).')
    # Verify the deployable model before copying it, including hashes and preprocessing.
    import sys
    sys.path.insert(0, str(root))
    from medlock_device.runtime import Engine
    Engine(root/'outputs/pi-bundle')
    out.mkdir(parents=True)
    shutil.copytree(root/'medlock_device',out/'medlock_device',ignore=shutil.ignore_patterns('__pycache__','ui','static'))
    shutil.copytree(ui,out/'medlock_device/ui')
    (out/'medlock_lab').mkdir()
    for name in ['__init__.py','imaging.py']:
        shutil.copy2(root/'medlock_lab'/name,out/'medlock_lab'/name)
    shutil.copytree(root/'outputs/pi-bundle',out/'model')
    if include_replay:
        (out/'replay').mkdir()
        for name in ['001.JPG','004.JPG','007.JPG']:
            shutil.copy2(root/'outputs/medlock-pilot-2026-10-21/images'/name,out/'replay'/name)
    shutil.copytree(repo/'deploy',out/'deploy')
    (out/'scripts').mkdir()
    for name in ['calibrate_volume.py','record_trial.py','evaluate_trials.py']:
        shutil.copy2(root/'scripts'/name,out/'scripts'/name)
    (out/'docs').mkdir()
    for name in ['INTEGRATION.md','API.md','BASELINE.md','VERIFICATION.md','REPORT_ALIGNMENT.md','HARDWARE_ACCEPTANCE.md','BENCH_TRIALS.md']:
        shutil.copy2(repo/'docs'/name,out/'docs'/name)
    shutil.copytree(repo/'docs/evidence',out/'docs/evidence')
    shutil.copy2(root/'requirements-device.txt',out/'requirements-device.txt')
    (out/'README.md').write_text((repo/'docs/INTEGRATION.md').read_text().replace('](BENCH_TRIALS.md)', '](docs/BENCH_TRIALS.md)'))
    (out/'TOUCHSCREEN.md').write_text((root/'medlock_device/TOUCHSCREEN.md').read_text().replace('../../docs/', 'docs/'))
    for name in ['README.md','TOUCHSCREEN.md']:
        target = out/'medlock_device'/name
        target.write_text(target.read_text().replace('../../docs/', '../docs/'))
    revision = None
    dirty = None
    try:
        revision = subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
        dirty = bool(subprocess.run(['git','status','--porcelain'],cwd=repo,capture_output=True,text=True,check=True).stdout.strip())
    except (OSError,subprocess.CalledProcessError):
        pass
    (out/'BUILD.json').write_text(json.dumps({'application':'medlock-unified-station','source_revision':revision,'source_dirty':dirty,'replay_included':include_replay,'volume_calibration_included':False},indent=2)+'\n')
    (out/'FILES.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file()))
    shutil.make_archive(str(out),'gztar',root_dir=out.parent,base_dir=out.name)
    return {'folder':str(out),'archive':str(out)+'.tar.gz'}


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=root.parent/'deployment/medlock-pi')
    parser.add_argument('--ui',type=Path,default=root.parent/'medlock-ui/dist')
    parser.add_argument('--without-replay',action='store_true')
    args=parser.parse_args()
    print(json.dumps(package(args.output.resolve(),args.ui.resolve(),not args.without_replay),indent=2))


if __name__=='__main__':main()
