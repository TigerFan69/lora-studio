#!/usr/bin/env python3
"""Package only the explicit release source inventory, never settings or runtime data."""
import argparse, hashlib, zipfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');a=p.parse_args()
root=Path(__file__).resolve().parents[1]; target=Path(a.output).resolve()
if target.exists():p.error('Output already exists; choose a new filename')
manifest=root/'SHA256SUMS'
files=[root/line.split('  ',1)[1] for line in manifest.read_text().splitlines()]+[manifest]
for f in files:
 if f.is_symlink() or not f.is_file() or not f.resolve().is_relative_to(root):raise ValueError('Invalid release path')
target.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
 for f in files:z.write(f,'LoRA-Studio/'+str(f.relative_to(root)))
print(target); print('SHA256',hashlib.sha256(target.read_bytes()).hexdigest())
