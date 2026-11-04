"""Assemble a portable deployment folder without Mac packages or training data."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=root/'outputs/medlock-pi-deployment')
out=parser.parse_args().output.resolve()
if out.exists():
    raise SystemExit('Deployment folder already exists; preserve or move it before rebuilding.')
out.mkdir()
shutil.copytree(root/'medlock_device',out/'medlock_device',ignore=shutil.ignore_patterns('__pycache__'))
(out/'medlock_lab').mkdir()
for name in ['__init__.py','imaging.py']:
    shutil.copy2(root/'medlock_lab'/name,out/'medlock_lab'/name)
shutil.copytree(root/'outputs/pi-bundle',out/'model')
(out/'replay').mkdir()
for name in ['001.JPG','004.JPG','007.JPG']:
    shutil.copy2(root/'outputs/medlock-pilot-2026-10-21/images'/name,out/'replay'/name)
shutil.copy2(root/'medlock_device/README.md',out/'README.md')
shutil.copy2(root/'medlock_device/TOUCHSCREEN.md',out/'TOUCHSCREEN.md')
(out/'FILES.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file()))
shutil.make_archive(str(out),'gztar',root_dir=out.parent,base_dir=out.name)
print(json.dumps({'folder':str(out),'archive':str(out)+'.tar.gz'},indent=2))
