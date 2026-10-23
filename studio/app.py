import json, os, re, shutil, subprocess, sys, threading, uuid
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yaml
from core import (atomic_json, read_json, now, safe_child, image_files, audit, prepare,
                  resolve_models, build_config, redact, gpu_status, process_identity)

from training_profiles import profile, resolve_profile, profile_config, catalog

HERE = Path(__file__).resolve().parent
SETTINGS = Path(os.environ.get('LORA_STUDIO_SETTINGS', HERE/'settings.json'))
settings = read_json(SETTINGS)
TOOLKIT = Path(settings['toolkit']).resolve()
DATA = Path(settings.get('data', HERE/'data')).resolve()
PROJECTS, JOBS = DATA/'projects', DATA/'jobs'
for d in (PROJECTS,JOBS): d.mkdir(parents=True,exist_ok=True)
LOCK = threading.RLock()
app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
HOSTS = set(settings.get('hosts',['127.0.0.1:8765','localhost:8765']))
ACTIVE = {'queued','loading','running','stopping'}

@app.middleware('http')
async def boundary(request, call_next):
    host = request.headers.get('host','')
    if host not in HOSTS: return JSONResponse({'detail':'Host not allowed'},status_code=403)
    if request.method not in ('GET','HEAD'):
        origin = request.headers.get('origin')
        if request.headers.get('x-studio-request') != '1' or (origin and origin != f'{request.url.scheme}://{host}'):
            return JSONResponse({'detail':'Same-origin Studio request required'},status_code=403)
        try: size=int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'Invalid content length'},status_code=400)
        if size>512*1024*1024: return JSONResponse({'detail':'Upload limit: 512 MB per request'},status_code=413)
        if request.url.path=='/api/upload' and not request.headers.get('content-length'):
            return JSONResponse({'detail':'Upload needs a Content-Length header'},status_code=411)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin',
      'Content-Security-Policy':"default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'",
      'Cache-Control':'no-store'})
    if request.url.path == "/guide":
        response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc): return JSONResponse({'detail':str(exc)},status_code=400)

class NewProject(BaseModel):
    name: str = Field(min_length=1,max_length=80)
    trigger: str = Field(default='ohwx woman',min_length=1,max_length=100)
    source: str = 'my_dataset'
class Caption(BaseModel):
    text: str = Field(max_length=12000)
class Preparation(BaseModel):
    mode: str = 'preserve'
    max_size: int = 2048
    clean: bool = True
class JobInput(BaseModel):
    project: str
    profile_id: str = 'flux1-schnell'
    steps: int = 2000
    label: str = Field(default='character',max_length=40)


def project_path(pid):
    if not re.fullmatch(r'[a-f0-9]{12}',pid): raise HTTPException(404,'Project not found')
    p = PROJECTS/pid
    if not (p/'project.json').is_file(): raise HTTPException(404,'Project not found')
    return p

def job_path(jid):
    if not re.fullmatch(r'[a-f0-9]{12}',jid): raise HTTPException(404,'Job not found')
    p=JOBS/jid
    if not (p/'job.json').is_file(): raise HTTPException(404,'Job not found')
    return p

def job_record(path):
    d=read_json(path/'job.json')
    d.setdefault('profile_id','flux1-schnell')
    info=profile(d['profile_id'])
    d.setdefault('profile_label',info['label'])
    d.setdefault('family',info['family'])
    d.setdefault('inference',info['inference'])
    if d['status']=='queued' and not d.get('pid') and (datetime.now(timezone.utc)-datetime.fromisoformat(d.get('queued',d['created']))).total_seconds()>60:
        d.update(status='interrupted',error='Runner did not initialize. Create a fresh job; no automatic retry.')
    if d['status'] in ACTIVE:
        if d.get('pid') and process_identity(d['pid']) != d.get('identity'):
            d.update(status='interrupted',error='Runner is no longer active. Existing checkpoints are preserved.')
    logfile=path/'train.log'
    text=''
    if logfile.exists():
        with logfile.open('rb') as f:
            f.seek(max(0,logfile.stat().st_size-16000)); text=redact(f.read().decode('utf-8',errors='replace'))
    steps=re.findall(r'(\d+)/'+str(d['steps'])+r'\s+\[',text)
    d['step']=int(steps[-1]) if steps else (d['steps'] if d['status']=='completed' else 0)
    loss=re.findall(r'loss:\s*([\deE.+-]+)',text);d['loss']=loss[-1] if loss else None
    stages=['Loading transformer','Fusing in LoRA','Quantizing transformer','Loading T5','Quantizing T5',
            'Preparing Model','Caching text','UNLOADING TEXT ENCODER','Skipping first sample','Saved checkpoint']
    d['stage']=next((s for s in reversed(stages) if s in text),'Waiting for log')
    if d['step'] and d['status']=='loading': d['status']='running'
    d['log']=text.replace('\r','\n')[-16000:]
    out=Path(d['output'])/d['name']
    d['checkpoints']=[dict(name=p.name,bytes=p.stat().st_size,modified=p.stat().st_mtime,url=f"/api/jobs/{d['id']}/files/{p.name}")
                      for p in sorted(out.glob('*.safetensors')) if p.is_file() and not p.is_symlink()]
    return d

def projects_list():
    return [read_json(p) for p in sorted(PROJECTS.glob('*/project.json'),key=lambda p:p.stat().st_mtime,reverse=True)]

def jobs_list():
    return [job_record(p.parent) for p in sorted(JOBS.glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True)]

def new_project(name,trigger):
    trigger=' '.join(trigger.split())
    if not trigger: raise ValueError('Trigger cannot be empty')
    pid=uuid.uuid4().hex[:12]; p=PROJECTS/pid
    (p/'source').mkdir(parents=True)
    (p/'caption_backups').mkdir()
    d=dict(id=pid,name=name,trigger=trigger,created=now(),prepared=None)
    return p,d

def commit_project(p,d):
    report=audit(p/'source',d['trigger'])
    if not report['count']: raise ValueError('No supported images were found')
    d['image_count']=report['count'];atomic_json(p/'project.json',d)
    # Capture original captions independently of later edits.
    original=p/'original_captions'; original.mkdir()
    for f in (p/'source').glob('*.txt'): shutil.copy2(f,original/f.name)
    return d

@app.get('/api/training-profiles')
def training_profiles(): return catalog(TOOLKIT,settings)

@app.get('/api/state')
def state():
    existing=[]
    for folder in settings.get('existing_outputs',[]):
        root=Path(folder)
        if root.is_dir():
            for p in sorted(root.glob('*.safetensors')):
                if p.is_file() and not p.is_symlink(): existing.append(dict(name=p.name,bytes=p.stat().st_size,modified=p.stat().st_mtime))
    return dict(projects=projects_list(),jobs=jobs_list(),gpu=gpu_status(),
                disk_free_gb=round(shutil.disk_usage(TOOLKIT).free/1e9,1),existing=existing,
                removed_adapters=read_json(DATA/'removed_adapters.json') if (DATA/'removed_adapters.json').exists() else [],
                sources=list(settings.get('sources',{'my_dataset':'my_dataset','raw_images':'raw_images'})),
                note='Private single-operator tool. No model downloads or training start automatically.')

@app.post('/api/projects')
def import_project(body:NewProject):
    with LOCK:
        source_name=settings.get('sources',{'my_dataset':'my_dataset','raw_images':'raw_images'}).get(body.source)
        if not source_name: raise ValueError('Choose a configured source folder')
        source=(TOOLKIT/source_name).resolve()
        if TOOLKIT not in source.parents or not source.is_dir(): raise ValueError('Source folder unavailable')
        p,d=new_project(body.name,body.trigger)
        try:
            for f in image_files(source):
                shutil.copy2(f,p/'source'/f.name)
                cap=f.with_suffix('.txt')
                if cap.is_file() and not cap.is_symlink(): shutil.copy2(cap,p/'source'/cap.name)
            return commit_project(p,d)
        except Exception: shutil.rmtree(p);raise

@app.post('/api/upload')
async def upload(name:str=Form(...),trigger:str=Form(...),files:list[UploadFile]=File(...)):
    if len(files)>300 or len(name)>80 or len(trigger)>100: raise ValueError('Too many files or overly long project name')
    p,d=new_project(name,trigger)
    total=0;seen=set()
    try:
        for f in files:
            filename=f.filename or ''
            if filename.startswith('.'): continue
            target=safe_child(p/'source',filename)
            if target.suffix.lower() not in EXTS_AND_TXT: raise ValueError('Upload images and matching .txt captions only')
            if filename.casefold() in seen: raise ValueError('Duplicate filename in upload')
            seen.add(filename.casefold())
            size=0
            with target.open('xb') as out:
                while chunk:=await f.read(1024*1024):
                    size+=len(chunk);total+=len(chunk)
                    if size>50*1024*1024 or total>500*1024*1024: raise ValueError('Maximum 50 MB/file and 500 MB total')
                    if target.suffix.lower()=='.txt' and size>12000: raise ValueError('Caption exceeds 12 KB')
                    out.write(chunk)
        # Keep each upload together under Raw Images; existing batches never collide.
        commit_project(p,d)
        raw=TOOLKIT/'raw_images'
        if raw.is_symlink() or (raw.exists() and not raw.is_dir()):raise ValueError('Raw Images must be a normal directory')
        raw.mkdir(exist_ok=True)
        batch=raw/d['id'];pending=raw/('.upload-'+d['id'])
        try:
            shutil.copytree(p/'source',pending)
            pending.rename(batch)
        finally:
            if pending.exists():shutil.rmtree(pending)
        d['raw_batch']=str(batch);atomic_json(p/'project.json',d)
        return d
    except Exception: shutil.rmtree(p);raise
EXTS_AND_TXT={'.jpg','.jpeg','.png','.webp','.txt'}

@app.get('/api/projects/{pid}')
def get_project(pid:str,prepared:bool=False):
    p=project_path(pid);d=read_json(p/'project.json')
    folder=p/'prepared'/d['prepared'] if prepared and d.get('prepared') else p/'source'
    return dict(project=d,removed_images=[dict(id=x.parent.name,name=read_json(x)['name']) for x in sorted((p/'removed_images').glob('*/image.json'))],audit=audit(folder,d['trigger']),view='prepared' if folder.parent.name=='prepared' else 'source')

@app.get('/api/projects/{pid}/images/{filename}')
def get_image(pid:str,filename:str,prepared:bool=False):
    p=project_path(pid);d=read_json(p/'project.json')
    folder=p/'prepared'/d['prepared'] if prepared and d.get('prepared') else p/'source'
    f=safe_child(folder,filename)
    if not f.is_file() or f.suffix.lower() not in EXTS_AND_TXT-{'.txt'}: raise HTTPException(404)
    # Send small re-encoded previews, never an arbitrary path or raw metadata.
    from PIL import Image,ImageOps
    import io
    with Image.open(f) as im:
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((600,600));buf=io.BytesIO();im.save(buf,format='JPEG',quality=85)
    return Response(buf.getvalue(),media_type='image/jpeg')

@app.put('/api/projects/{pid}/captions/{filename}')
def save_caption(pid:str,filename:str,body:Caption):
    with LOCK:
        p=project_path(pid);im=safe_child(p/'source',filename)
        if im.suffix.lower() not in EXTS_AND_TXT-{'.txt'} or not im.is_file(): raise HTTPException(404)
        cap=im.with_suffix('.txt')
        if cap.exists(): shutil.copy2(cap,p/'caption_backups'/(uuid.uuid4().hex+'_'+cap.name))
        cap.write_text(body.text,encoding='utf-8')
        d=read_json(p/'project.json');d['prepared']=None;atomic_json(p/'project.json',d)
        return {'saved':True,'note':'Prepare a fresh revision before creating a new job. Existing jobs keep their snapshot.'}


class ImageRemoval(BaseModel):
    prepared: bool = False

def image_edit_guard(pid):
    if any(r['project']==pid and r['status'] in {'queued','running','needs_attention'} for r in caption_runs()):
        raise ValueError('Finish or resolve captioning before changing dataset images')

def invalidate_images(p):
    d=read_json(p/'project.json')
    d['prepared']=None
    d['image_count']=len(image_files(p/'source'))
    atomic_json(p/'project.json',d)

@app.post('/api/projects/{pid}/images/{filename}/remove')
def remove_image(pid:str,filename:str,body:ImageRemoval):
    with LOCK:
        p=project_path(pid);image_edit_guard(pid)
        safe_child(p/'source',filename)
        files=image_files(p/'source')
        matches=[f for f in files if (f.stem+'.png'==filename if body.prepared else f.name==filename)]
        if len(matches)!=1: raise ValueError('Image no longer exists or its name is ambiguous; refresh the project')
        im=matches[0];cap=im.with_suffix('.txt')
        if cap.is_symlink(): raise ValueError('Caption symlinks are not supported')
        if sum(f.stem==im.stem for f in files)>1: raise ValueError('Rename duplicate image stems before removing this photo')
        box=p/'removed_images'/uuid.uuid4().hex
        box.mkdir(parents=True)
        atomic_json(box/'image.json',dict(name=im.name,removed=now()))
        moved=[]
        try:
            for f in [im,cap]:
                if f.exists(): f.rename(box/f.name);moved.append(f)
            invalidate_images(p)
        except Exception:
            for f in reversed(moved): (box/f.name).rename(f)
            shutil.rmtree(box)
            raise
        return {'removed':True}

@app.post('/api/projects/{pid}/removed-images/{rid}/restore')
def restore_image(pid:str,rid:str):
    with LOCK:
        p=project_path(pid);image_edit_guard(pid)
        if not re.fullmatch(r'[a-f0-9]{32}',rid): raise HTTPException(404)
        box=p/'removed_images'/rid
        if not (box/'image.json').is_file(): raise HTTPException(404)
        name=read_json(box/'image.json')['name']
        im=safe_child(box,name);target=safe_child(p/'source',name)
        files=[f for f in [im,im.with_suffix('.txt')] if f.exists()]
        if any((p/'source'/f.name).exists() for f in files): raise ValueError('A file with this name already exists; nothing was overwritten')
        moved=[]
        try:
            for f in files: f.rename(p/'source'/f.name);moved.append(f)
            invalidate_images(p)
        except Exception:
            for f in reversed(moved): (p/'source'/f.name).rename(f)
            raise
        shutil.rmtree(box)
        return {'restored':True}

@app.post('/api/projects/{pid}/prepare')
def prepare_project(pid:str,body:Preparation):
    with LOCK:
        p=project_path(pid);d=read_json(p/'project.json');revision=uuid.uuid4().hex[:12]
        # Outputs are a sibling of source, never modifications of originals.
        report=prepare(p/'source',p/'prepared'/revision,d['trigger'],body.mode,body.max_size,body.clean)
        d['prepared']=revision;d['mode']=body.mode;d['max_size']=body.max_size;atomic_json(p/'project.json',d)
        return dict(project=d,audit=report,view='prepared')

@app.post('/api/jobs')
def create_job(body:JobInput):
    with LOCK:
        p=project_path(body.project);project=read_json(p/'project.json')
        if not project.get('prepared'): raise ValueError('Prepare a dataset revision first')
        dataset=p/'prepared'/project['prepared'];report=audit(dataset,project['trigger'])
        blocking=[r['name'] for r in report['images'] if any('Missing or empty' in w or 'Trigger phrase missing' in w or 'Unreadable' in w or 'Duplicate filename' in w for w in r['warnings'])]
        if blocking: raise ValueError('Fix missing captions, trigger phrases or invalid images before training: '+', '.join(blocking[:8]))
        selected_profile=profile(body.profile_id)
        base,adapter=resolve_profile(body.profile_id,TOOLKIT,settings)
        jid=uuid.uuid4().hex[:12]
        label=re.sub(r'[^a-z0-9_-]+','_',body.label.lower()).strip('_-') or 'character'
        name=('krea2_' if selected_profile['family']=='krea2' else '')+label+'_'+jid
        output=TOOLKIT/'output'/'lora_studio'
        # Validate before creating files; Dev caches must not reuse Schnell embeddings.
        config=profile_config(body.profile_id,name,dataset,output,base,adapter,body.steps)
        path=JOBS/jid;path.mkdir()
        if body.profile_id!='flux1-schnell':
            isolated=path/'dataset';isolated.mkdir()
            try:
                for image in image_files(dataset):
                    shutil.copy2(image,isolated/image.name)
                    shutil.copy2(image.with_suffix('.txt'),isolated/image.with_suffix('.txt').name)
                dataset=isolated
                config=profile_config(body.profile_id,name,dataset,output,base,adapter,body.steps)
            except Exception:
                shutil.rmtree(path);raise
        (path/'config.yaml').write_text(yaml.safe_dump(config,sort_keys=False))
        d=dict(id=jid,name=name,project=body.project,project_name=project['name'],trigger=project['trigger'],
               revision=project['prepared'],steps=body.steps,status='ready',created=now(),toolkit=str(TOOLKIT),
               output=str(output),dataset=str(dataset),profile_id=body.profile_id,
               profile_label=selected_profile['label'],family=selected_profile['family'],
               model_path=base,model_revision=next((x for x in Path(base).parts if re.fullmatch(r'[a-f0-9]{40}',x)),None),inference=selected_profile['inference'])
        atomic_json(path/'job.json',d)
        return job_record(path)

@app.get('/api/jobs/{jid}/config')
def config_file(jid:str): return FileResponse(job_path(jid)/'config.yaml',media_type='text/plain',filename='config.yaml')

@app.post('/api/jobs/{jid}/start')
def start_job(jid:str):
    with LOCK:
        path=job_path(jid);d=read_json(path/'job.json')
        if d['status']!='ready': raise ValueError('Only a ready job can start. Create a new job for another run.')
        if any(r['status'] in {'queued','running','needs_attention'} for r in caption_runs()): raise ValueError('Finish or resolve the captioning job first')
        if any(j['status'] in ACTIVE for j in jobs_list()): raise ValueError('Another Studio job is active')
        # Detect external ai-toolkit jobs without terminating them.
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                parts=(proc/'cmdline').read_bytes().split(b'\0')
                if any(x==b'run.py' or x.endswith(b'/ai-toolkit/run.py') for x in parts):
                    raise ValueError('An ai-toolkit process is already running outside this job')
            except (OSError,PermissionError): pass
        gpu=gpu_status()
        if gpu['used'] is None: raise ValueError('NVIDIA GPU is unavailable')
        requirements=profile(d.get('profile_id','flux1-schnell'))['requirements']
        if gpu['total']<requirements['min_vram_mib']: raise ValueError('This preset requires approximately 16 GB VRAM')
        if gpu['used']>requirements['max_idle_vram_mib']: raise ValueError('Free GPU memory first: unload ComfyUI/Ollama models. Studio will not stop other applications.')
        if shutil.disk_usage(TOOLKIT).free<requirements['min_free_disk_bytes']: raise ValueError('Free at least 8 GB disk space before training')
        d.update(status='queued',queued=now());atomic_json(path/'job.json',d)
        try:
            with (path/'runner.log').open('ab') as log:
                child=subprocess.Popen([sys.executable,str(HERE/'runner.py'),str(path)],cwd=HERE,
                            stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        except Exception:
            d.update(status='ready');atomic_json(path/'job.json',d);raise
        return {'started':True,'id':jid}

@app.post('/api/jobs/{jid}/stop')
def stop_job(jid:str):
    with LOCK:
        path=job_path(jid);d=job_record(path)
        if d['status'] not in ACTIVE: raise ValueError('This job is not running')
        (path/'stop.request').touch(exist_ok=True)
        return {'requested':True,'note':'SIGINT requested. Wait for stopped status; unsaved steps may be lost.'}

@app.get('/api/jobs/{jid}/files/{filename}')
def checkpoint(jid:str,filename:str):
    d=read_json(job_path(jid)/'job.json');root=Path(d['output'])/d['name'];f=safe_child(root,filename)
    if f.suffix!='.safetensors' or not f.is_file() or f.is_symlink(): raise HTTPException(404)
    return FileResponse(f,filename=f.name)

@app.get('/api/existing/{filename}')
def existing_file(filename:str):
    for folder in settings.get('existing_outputs',[]):
        f=safe_child(folder,filename)
        if f.is_file() and f.suffix=='.safetensors' and not f.is_symlink(): return FileResponse(f,filename=f.name)
    raise HTTPException(404)


from captioning import preflight, digest, apply_draft, call as comfy_call
CAPTIONS=DATA/'caption_jobs'
CAPTIONS.mkdir(exist_ok=True)
def caption_runs():
    runs=[]
    for f in sorted(CAPTIONS.glob('*/run.json'),key=lambda x:x.stat().st_mtime,reverse=True):
        d=read_json(f)
        if d['status']=='running' and process_identity(d.get('pid',0))!=d.get('identity'):
            d.update(status='needs_attention',error='Caption worker exited. Check ComfyUI before resolving.')
        if d['status']=='queued' and (datetime.now(timezone.utc)-datetime.fromisoformat(d['created'])).total_seconds()>60:
            d.update(status='needs_attention',error='Caption worker did not initialize.')
        runs.append(d)
    return runs
class CaptionRunInput(BaseModel):
    mode:str='missing'
    filename:str=''
class ApplyDraftInput(BaseModel):
    filename:str
    text:str=Field(min_length=1,max_length=12000)
def caption_path(rid):
    if not re.fullmatch(r'[a-f0-9]{12}',rid) or not (CAPTIONS/rid/'run.json').exists():raise HTTPException(404)
    return CAPTIONS/rid
@app.get('/api/captioning')
def caption_status():
    return {'runs':[{k:v for k,v in r.items() if k not in {'source','comfy_root','items'}} for r in caption_runs()]}
@app.post('/api/projects/{pid}/captioning')
def start_captioning(pid:str,body:CaptionRunInput):
    with LOCK:
        p=project_path(pid)
        if any(j['status'] in ACTIVE for j in jobs_list()):raise ValueError('Wait for training to finish')
        if any(r['status'] in {'queued','running','needs_attention'} for r in caption_runs()):raise ValueError('A caption job is active or needs attention')
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                parts=(proc/'cmdline').read_bytes().split(b'\0')
                if any(x==b'run.py' or x.endswith(b'/ai-toolkit/run.py') for x in parts):raise ValueError('Wait for the active training process to finish')
            except OSError:pass
        root=Path(settings.get('comfy_root',TOOLKIT.parent/'ComfyUI')).resolve()
        try:preflight(root)
        except (OSError,TimeoutError) as e:raise ValueError('Cannot reach local ComfyUI: '+str(e))
        if body.mode not in {'missing','all','one'}:raise ValueError('Choose missing, all, or one image')
        files=image_files(p/'source')
        if body.mode=='one':files=[f for f in files if f.name==body.filename]
        if body.mode=='missing':files=[f for f in files if not f.with_suffix('.txt').exists() or not f.with_suffix('.txt').read_text().strip()]
        if not files:raise ValueError('No matching images. Choose all images to replace existing captions with reviewable drafts.')
        rid=uuid.uuid4().hex[:12];path=CAPTIONS/rid;path.mkdir()
        d=dict(id=rid,project=pid,created=now(),status='queued',source=str(p/'source'),comfy_root=str(root),
               items=[dict(name=f.name,original_hash=digest(f.with_suffix('.txt'))) for f in files],results=[],total=len(files))
        atomic_json(path/'run.json',d)
        try:
            with (path/'runner.log').open('ab') as log:
                subprocess.Popen([sys.executable,str(HERE/'caption_runner.py'),str(path)],cwd=HERE,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        except Exception:
            d['status']='failed';atomic_json(path/'run.json',d);raise
        return {'id':rid}
@app.post('/api/captioning/{rid}/stop')
def stop_captioning(rid:str):
    (caption_path(rid)/'stop.request').touch();return {'requested':True}
@app.post('/api/captioning/{rid}/resolve')
def resolve_captioning(rid:str):
    with LOCK:
        path=caption_path(rid);d=next(r for r in caption_runs() if r['id']==rid)
        if d['status']!='needs_attention':raise ValueError('Only a job needing attention can be resolved')
        q=comfy_call('/queue')
        if q['queue_running'] or q['queue_pending']:raise ValueError('Wait until the ComfyUI queue is empty')
        d.update(status='failed',error='Resolved after checking that ComfyUI is idle. Generate new drafts to retry.');atomic_json(path/'run.json',d)
        return {'resolved':True}
@app.post('/api/captioning/{rid}/apply')
def apply_caption(rid:str,body:ApplyDraftInput):
    with LOCK:
        path=caption_path(rid);d=read_json(path/'run.json')
        if d['status'] in {'queued','running','needs_attention'}:raise ValueError('Wait until this caption job finishes')
        apply_draft(project_path(d['project']),d,body.filename,body.text);atomic_json(path/'run.json',d)
        return {'saved':True}


class HistoryChange(BaseModel):
    removed:bool=True
@app.post('/api/projects/{pid}/history')
def project_history(pid:str,body:HistoryChange):
    with LOCK:
        p=project_path(pid)
        if body.removed:
            if any(j['project']==pid and j['status'] in ACTIVE for j in jobs_list()):raise ValueError('Wait for this project’s training to finish')
            if any(r['project']==pid and r['status'] in {'queued','running','needs_attention'} for r in caption_runs()):raise ValueError('Finish or resolve this project’s captioning first')
        d=read_json(p/'project.json');d['removed']=body.removed;atomic_json(p/'project.json',d)
        return {'saved':True}
@app.post('/api/jobs/{jid}/history')
def job_history(jid:str,body:HistoryChange):
    with LOCK:
        p=job_path(jid);d=job_record(p)
        if d['status'] in ACTIVE:raise ValueError('Active training jobs cannot be removed')
        original=read_json(p/'job.json');original['removed']=body.removed;atomic_json(p/'job.json',original)
        return {'saved':True}
@app.post('/api/projects/{pid}/publish')
def publish_dataset(pid:str):
    with LOCK:
        p=project_path(pid);d=read_json(p/'project.json')
        if not d.get('prepared'):raise ValueError('Prepare and review a revision first')
        if any(j['status'] in ACTIVE for j in jobs_list()):raise ValueError('Wait until training finishes before publishing')
        if any(r['status'] in {'queued','running','needs_attention'} for r in caption_runs()):raise ValueError('Finish or resolve captioning before publishing')
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                parts=(proc/'cmdline').read_bytes().split(b'\0')
                if any(x==b'run.py' or x.endswith(b'/ai-toolkit/run.py') for x in parts):raise ValueError('Wait for the active training process before replacing My Dataset')
            except OSError:pass
        source=p/'prepared'/d['prepared'];report=audit(source,d['trigger'])
        if not report['count'] or any(any('Missing or empty' in w or 'Trigger phrase missing' in w or 'Unreadable' in w or 'Duplicate filename' in w for w in r['warnings']) for r in report['images']):raise ValueError('Fix missing captions, triggers or invalid images and prepare again')
        target=TOOLKIT/'my_dataset'
        if target.is_symlink() or (target.exists() and not target.is_dir()):raise ValueError('My Dataset must be a normal directory')
        token=uuid.uuid4().hex;staging=TOOLKIT/('.studio-publish-'+token)
        backup=TOOLKIT/'dataset_backups'/('my_dataset_'+token)
        try:
            staging.mkdir()
            for image in image_files(source):
                shutil.copy2(image,staging/image.name);shutil.copy2(image.with_suffix('.txt'),staging/image.with_suffix('.txt').name)
            if target.exists():backup.parent.mkdir(exist_ok=True);target.rename(backup)
            try:staging.rename(target)
            except Exception:
                if backup.exists():backup.rename(target)
                raise
        finally:
            if staging.exists():shutil.rmtree(staging)
        d['published_revision']=d['prepared'];d['published_at']=now();atomic_json(p/'project.json',d)
        return {'published':True,'images':report['count'],'backup':str(backup) if backup.exists() else None}


@app.get('/api/comfyui')
def comfy_status():
    try:
        r=subprocess.run(['/usr/bin/systemctl','is-active','comfyui.service'],capture_output=True,text=True,timeout=3)
        status=r.stdout.strip() or 'unavailable'
    except (OSError,subprocess.TimeoutExpired):status='unavailable'
    return {'status':status,'managed':bool(settings.get('manage_comfyui',False))}
@app.post('/api/comfyui/{action}')
def comfy_control(action:str):
    if action not in {'start','stop'}:raise HTTPException(404)
    if not settings.get('manage_comfyui',False):raise ValueError('ComfyUI service controls are not configured on this server. See the guide.')
    with LOCK:
        if any(r['status'] in {'queued','running','needs_attention'} for r in caption_runs()):raise ValueError('Finish or resolve the caption job before changing ComfyUI')
        if action=='start':
            if any(j['status'] in ACTIVE for j in jobs_list()):raise ValueError('Wait for training to finish before starting ComfyUI')
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    parts=(proc/'cmdline').read_bytes().split(b'\0')
                    if any(x==b'run.py' or x.endswith(b'/ai-toolkit/run.py') for x in parts):raise ValueError('Wait for the active training process before starting ComfyUI')
                except OSError:pass
        elif comfy_status()['status'] not in {'inactive','failed'}:
            try:q=comfy_call('/queue')
            except Exception:raise ValueError('Cannot verify ComfyUI is idle yet. Wait for it to finish starting, then try again.')
            if q.get('queue_running') or q.get('queue_pending'):raise ValueError('ComfyUI has running or queued work. Wait for it to finish before stopping.')
        try:r=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/systemctl',action,'comfyui.service'],capture_output=True,text=True,timeout=45)
        except subprocess.TimeoutExpired:raise ValueError('ComfyUI service change is still taking time. Check the status before trying again.')
        except OSError:raise ValueError('Service control is unavailable on this server')
        if r.returncode:raise ValueError('The server could not change ComfyUI. Check the narrowly scoped service-control permissions in the guide.')
        return {'requested':action,'note':'Starting can take a moment before captioning is ready.'}

@app.post('/api/captioning/{rid}/apply-all')
def apply_all_captions(rid:str):
    with LOCK:
        path=caption_path(rid);d=read_json(path/'run.json')
        if d['status']!='completed':raise ValueError('Wait until all caption drafts finish')
        p=project_path(d['project']);pending=[r for r in d['results'] if not r.get('applied')]
        # Validate the entire batch before modifying any caption.
        for row in pending:
            cap=safe_child(p/'source',row['name']).with_suffix('.txt')
            if digest(cap)!=row['original_hash']:raise ValueError('A source caption changed after generation. Automatic filling paused to protect your edits: '+row['name'])
            if not row['text'].strip() or len(row['text'])>12000:raise ValueError('A generated caption is empty or too long: '+row['name'])
        for row in pending:
            apply_draft(p,d,row['name'],row['text'])
            atomic_json(path/'run.json',d)
        return {'saved':len(pending)}

class AdapterHistoryChange(BaseModel):
    url:str=Field(max_length=500)
    removed:bool=True
@app.post('/api/library/history')
def adapter_history(body:AdapterHistoryChange):
    from urllib.parse import quote
    with LOCK:
        valid={c['url'] for j in jobs_list() for c in j['checkpoints']}
        for folder in settings.get('existing_outputs',[]):
            valid.update('/api/existing/'+quote(p.name,safe='') for p in Path(folder).glob('*.safetensors') if p.is_file() and not p.is_symlink())
        if body.url not in valid:raise ValueError('Adapter not found in the library')
        path=DATA/'removed_adapters.json';removed=set(read_json(path) if path.exists() else [])
        if body.removed:removed.add(body.url)
        else:removed.discard(body.url)
        atomic_json(path,sorted(removed));return {'saved':True}

@app.get('/guide')
def guide(): return FileResponse(HERE/'GUIDE.html')
@app.get('/')
def index(): return FileResponse(HERE/'static/index.html')
app.mount('/static',StaticFiles(directory=HERE/'static'),name='static')


class CopyAdapter(BaseModel):
    url: str = Field(max_length=500)

@app.post('/api/library/copy-to-comfyui')
def copy_adapter_to_comfyui(body:CopyAdapter):
    import hashlib, tempfile
    from urllib.parse import quote
    from safetensors import safe_open
    def sha(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()
    with LOCK:
        available={}
        for j in jobs_list():
            if j['status'] in ACTIVE: continue
            for c in j['checkpoints']:
                available[c['url']]=Path(j['output'])/j['name']/c['name']
        for folder in settings.get('existing_outputs',[]):
            for f in Path(folder).glob('*.safetensors'):
                if f.is_file() and not f.is_symlink():available.setdefault('/api/existing/'+quote(f.name,safe=''),f)
        source=available.get(body.url)
        if source is None or not source.is_file() or source.is_symlink():raise ValueError('Choose a saved adapter from an inactive training job')
        root=Path(settings.get('comfy_root',TOOLKIT.parent/'ComfyUI')).resolve()
        destination=Path(settings.get('lora_destination',root/'models'/'loras'))
        if not destination.is_dir():raise ValueError('ComfyUI LoRA folder is not configured or does not exist')
        target=destination/source.name
        if target.is_symlink():raise ValueError('Destination is a symlink; nothing was overwritten')
        before=source.stat()
        fd,tmp=tempfile.mkstemp(prefix='.studio-copy-',suffix='.tmp',dir=destination);os.close(fd);tmp=Path(tmp)
        try:
            shutil.copyfile(source,tmp)
            after=source.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Checkpoint changed during copying; try after training finishes')
            with safe_open(tmp,framework='pt',device='cpu') as model:
                if not model.keys():raise ValueError('Checkpoint contains no tensors')
            checksum=sha(tmp)
            if checksum!=sha(source):raise ValueError('Copy verification failed; please retry')
            if target.exists():
                if target.is_file() and sha(target)==checksum:return {'status':'already_present','name':source.name}
                raise ValueError('A different file with this name already exists in ComfyUI; nothing was overwritten')
            # Publish the completed copy atomically, without replacing any existing file.
            try:os.link(tmp,target)
            except FileExistsError:raise ValueError('Destination appeared during copying; nothing was overwritten')
            return {'status':'copied','name':source.name,'bytes':target.stat().st_size}
        finally:tmp.unlink(missing_ok=True)


class DestinationSettings(BaseModel):
    lora_destination: str = Field(min_length=1,max_length=4096)

def default_lora_destination():
    return str(Path(settings.get('comfy_root',TOOLKIT.parent/'ComfyUI')).resolve()/'models'/'loras')

@app.get('/api/settings/destinations')
def get_destinations():
    return {'lora_destination':settings.get('lora_destination',default_lora_destination()),'default_lora_destination':default_lora_destination()}

@app.put('/api/settings/destinations')
def save_destinations(body:DestinationSettings):
    import tempfile
    with LOCK:
        folder=Path(body.lora_destination.strip()).expanduser()
        if not folder.is_absolute():raise ValueError('Enter an absolute folder path on this server')
        folder=folder.resolve()
        if not folder.is_dir():raise ValueError('That folder does not exist on the server. Create it first, then save again.')
        try:
            with tempfile.TemporaryFile(dir=folder) as probe:probe.write(b'LoRA Studio destination check');probe.flush()
        except OSError:raise ValueError('LoRA Studio cannot write to that folder. Check its permissions.')
        # Preserve unrelated settings and persist before changing the live copy destination.
        updated=read_json(SETTINGS);updated['lora_destination']=str(folder)
        atomic_json(SETTINGS,updated);settings['lora_destination']=str(folder)
        return get_destinations()
