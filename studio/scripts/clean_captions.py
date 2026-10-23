#!/usr/bin/env python3
"""Preview caption normalization; --apply makes timestamped backups before writing."""
import argparse,json,sys,shutil,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import clean_caption,image_files
p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset');p.add_argument('--trigger',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
folder=Path(a.dataset);changes=[];backup=folder.parent/(folder.name+'_caption_backup_'+uuid.uuid4().hex[:8])
for image in image_files(folder):
 cap=image.with_suffix('.txt')
 if not cap.exists(): continue
 old=cap.read_text(encoding='utf-8',errors='replace');new=clean_caption(old,a.trigger)
 if old!=new:
  changes.append(dict(file=cap.name,before=old,after=new))
  if a.apply:
   backup.mkdir(exist_ok=True);shutil.copy2(cap,backup/cap.name);cap.write_text(new)
print(json.dumps(dict(applied=a.apply,backup=str(backup) if a.apply and changes else None,changes=changes),indent=2))
