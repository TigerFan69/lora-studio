#!/usr/bin/env python3
"""Optional local vision captioning. Uses an already-installed Ollama vision model only."""
import argparse,base64,io,json,sys,urllib.request,uuid,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import image_files,clean_caption
from PIL import Image,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset');p.add_argument('--model',required=True);p.add_argument('--trigger',required=True);p.add_argument('--overwrite',action='store_true');a=p.parse_args()
URL='http://127.0.0.1:11434'
def post(path,data,timeout=600):
 req=urllib.request.Request(URL+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
with urllib.request.urlopen(URL+'/api/tags',timeout=5) as r: installed={m['name'] for m in json.load(r).get('models',[])}
if a.model not in installed:sys.exit('Model is not installed. No download was attempted.')
info=post('/api/show',{'model':a.model},10)
if 'vision' not in info.get('capabilities',[]):sys.exit('Choose an installed vision-capable model; text-only models cannot caption images.')
for proc in Path('/proc').glob('[0-9]*'):
 try:
  if any(x==b'run.py' or x.endswith(b'/ai-toolkit/run.py') for x in (proc/'cmdline').read_bytes().split(b'\0')):sys.exit('Stop training before using GPU captioning.')
 except OSError:pass
backup=Path(a.dataset).resolve().parent/('caption_backup_'+uuid.uuid4().hex[:8])
try:
 for image in image_files(a.dataset):
  caption=image.with_suffix('.txt')
  if caption.exists() and caption.read_text(errors='replace').strip() and not a.overwrite:continue
  with Image.open(image) as im:
   im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1536,1536));buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=90)
  response=post('/api/generate',dict(model=a.model,stream=False,keep_alive='5m',options={'temperature':0.2},
     prompt='Describe only clearly visible content in this image for an image-training caption, in 40 to 100 words. Describe hairstyle, clothing, pose, framing, lighting and setting. Do not infer identity, personality, exact age, ethnicity or unseen body details. No preamble, no lists, no speculation.',
     images=[base64.b64encode(buffer.getvalue()).decode()]))
  text=response.get('response','').strip()
  if not text:raise RuntimeError('Model returned an empty caption for '+image.name)
  if caption.exists():backup.mkdir(exist_ok=True);shutil.copy2(caption,backup/caption.name)
  caption.write_text(clean_caption(text,a.trigger));print('Captioned',image.name,flush=True)
finally:
 try:post('/api/generate',{'model':a.model,'keep_alive':0},30)
 except Exception:pass
print('Review every generated caption before preparation and training. Backups:',backup)
