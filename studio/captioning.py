"""Local Florence caption drafts. No automatic model installation or caption replacement."""
import hashlib, json, urllib.request, uuid
from pathlib import Path
from core import atomic_json, read_json, safe_child
MODEL='MiaoshouAI/Florence-2-large-PromptGen-v2.0'
URL='http://127.0.0.1:8188'
def call(route, data=None):
    req=urllib.request.Request(URL+route, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def preflight(root):
    model=Path(root)/'models/LLM'/MODEL.split('/')[-1]
    if not (model/'model.safetensors').is_file():raise ValueError('Florence PromptGen model is not installed in ComfyUI. See the guide.')
    info=call('/object_info')
    for name in ('LoadImage','DownloadAndLoadFlorence2Model','Florence2Run','easy showAnything'):
        if name not in info:raise ValueError('Missing ComfyUI node: '+name)
def graph(filename,seed):
    return {'27':{'class_type':'LoadImage','inputs':{'image':filename}},
      '3':{'class_type':'DownloadAndLoadFlorence2Model','inputs':{'model':MODEL,'precision':'bf16','convert_to_safetensors':False}},
      '2':{'class_type':'Florence2Run','inputs':{'image':['27',0],'florence2_model':['3',0],'text_input':'','task':'more_detailed_caption','fill_mask':True,'keep_model_loaded':False,'max_new_tokens':1024,'num_beams':3,'do_sample':True,'output_mask_select':'','seed':seed}},
      '4':{'class_type':'easy showAnything','inputs':{'anything':['2',2]}}}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def apply_draft(project,run,name,text):
    row=next((r for r in run['results'] if r['name']==name),None)
    if row is None:raise ValueError('Draft not found')
    cap=safe_child(project/'source',name).with_suffix('.txt')
    if row.get('applied'):raise ValueError('This draft has already been applied')
    if digest(cap)!=row['original_hash']:raise ValueError('Caption changed since generation. Review it and generate a new draft.')
    if not text.strip() or len(text)>12000:raise ValueError('Caption must contain 1–12000 characters')
    if cap.exists():
        backup=project/'caption_backups';backup.mkdir(exist_ok=True)
        (backup/(uuid.uuid4().hex+'_'+cap.name)).write_bytes(cap.read_bytes())
    tmp=cap.with_name('.'+uuid.uuid4().hex+'.tmp');tmp.write_text(text.strip()+'\n',encoding='utf-8');tmp.replace(cap)
    d=read_json(project/'project.json');d['prepared']=None;atomic_json(project/'project.json',d)
    row['applied']=True
