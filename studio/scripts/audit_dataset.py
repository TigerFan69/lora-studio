#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import audit
p=argparse.ArgumentParser(description='Report missing captions, triggers, duplicates and image dimensions.');p.add_argument('dataset');p.add_argument('--trigger',required=True);a=p.parse_args();print(json.dumps(audit(a.dataset,a.trigger),indent=2))
