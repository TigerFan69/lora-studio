#!/usr/bin/env python3
"""Compatibility command: explicit square crop, safe output, preserved captions."""
import argparse,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import prepare
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('output');p.add_argument('--trigger',required=True);p.add_argument('--size',type=int,choices=[512,768,1024,2048],default=512);a=p.parse_args()
print(json.dumps(prepare(a.source,a.output,a.trigger,'square',a.size,False),indent=2))
