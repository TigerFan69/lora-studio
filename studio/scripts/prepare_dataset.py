#!/usr/bin/env python3
"""Prepare a new dataset without modifying source files."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import prepare
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source');p.add_argument('output');p.add_argument('--trigger',required=True)
p.add_argument('--mode',choices=['preserve','square'],default='preserve')
p.add_argument('--max-size',type=int,choices=[512,768,1024,2048],default=2048)
p.add_argument('--no-clean',action='store_true')
a=p.parse_args();print(json.dumps(prepare(a.source,a.output,a.trigger,a.mode,a.max_size,not a.no_clean),indent=2))
