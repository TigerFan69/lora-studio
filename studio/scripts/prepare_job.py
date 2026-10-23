#!/usr/bin/env python3
"""Generate a fresh offline Schnell config. This does not launch training."""
import argparse,sys,yaml
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import resolve_models,build_config,audit
p=argparse.ArgumentParser(description=__doc__)
for name in ['toolkit','dataset','trigger','name','config']: p.add_argument('--'+name,required=True)
p.add_argument('--template');p.add_argument('--steps',type=int,default=2000);a=p.parse_args()
target=Path(a.config)
if target.exists(): p.error('Config already exists; choose a new path')
report=audit(a.dataset,a.trigger)
if not report['count'] or any(not r['caption'].strip() for r in report['images']): p.error('Images and nonempty captions are required')
base,adapter=resolve_models(a.toolkit,a.template)
c=build_config(a.name,a.dataset,Path(a.toolkit)/'output/lora_studio',base,adapter,a.steps)
target.parent.mkdir(parents=True,exist_ok=True);target.write_text(yaml.safe_dump(c,sort_keys=False));print(target.resolve())
