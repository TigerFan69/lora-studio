"""Detached caption worker; shares the training lock and stops between images."""
import fcntl, sys, time, uuid
from pathlib import Path
from PIL import Image, ImageOps
from core import atomic_json, read_json, process_identity
from captioning import call, graph, preflight

def main(path):
    d=read_json(path/'run.json');lock=(path.parent.parent/'jobs/training.lock').open('a')
    def save():atomic_json(path/'run.json',d)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        d.update(status='running',pid=__import__('os').getpid(),identity=process_identity(__import__('os').getpid()));save()
        root=Path(d['comfy_root']);preflight(root)
        inputs=root/'input/lora-studio'/d['id'];inputs.mkdir(parents=True,exist_ok=True)
        for item in d['items']:
            if (path/'stop.request').exists():break
            q=call('/queue')
            if q['queue_running'] or q['queue_pending']:raise ValueError('ComfyUI is busy. Completed drafts are kept; try remaining images later.')
            filename=uuid.uuid4().hex+'.png'
            with Image.open(Path(d['source'])/item['name']) as im:
                im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((2048,2048));im.save(inputs/filename)
            prompt_id=str(uuid.uuid4());seed=uuid.uuid4().int%(2**63-1)+1
            d.update(prompt_id=prompt_id,current=item['name']);save()
            # A caller-selected ID lets an uncertain submission remain identifiable.
            try:response=call('/prompt',{'prompt':graph('lora-studio/'+d['id']+'/'+filename,seed),'prompt_id':prompt_id,'client_id':'lora-studio-'+d['id']})
            except Exception:
                d.update(status='needs_attention',error='Submission outcome uncertain. Check ComfyUI before retrying. Prompt ID: '+prompt_id);save();return
            if response.get('prompt_id')!=prompt_id:raise ValueError('ComfyUI did not preserve the requested prompt ID')
            failures=0
            while True:
                try:h=call('/history/'+prompt_id).get(prompt_id);failures=0
                except Exception:
                    failures+=1
                    if failures>=10:
                        d.update(status='needs_attention',error='Lost ComfyUI connection. Check its queue before retrying.');save();return
                    time.sleep(3);continue
                if h:
                    if h.get('status',{}).get('status_str')=='error':raise ValueError('ComfyUI failed to caption this image. Check its log and installed model.')
                    texts=h.get('outputs',{}).get('4',{}).get('text',[])
                    text='\n'.join(str(t) for t in texts).strip()
                    if not text:raise ValueError('ComfyUI returned no caption')
                    d['results'].append(dict(item,text=text,seed=seed,applied=False));d['prompt_id']=None;save();break
                q=call('/queue')
                if not any(x[1]==prompt_id for x in q['queue_running']+q['queue_pending']):raise ValueError('Caption prompt disappeared from ComfyUI; drafts already completed are preserved')
                time.sleep(2)
            (inputs/filename).unlink(missing_ok=True)
        d['status']='stopped' if (path/'stop.request').exists() else 'completed';save()
    except Exception as e:
        d.update(status='needs_attention' if d.get('prompt_id') else 'failed',error=str(e));save()
    finally:lock.close()
if __name__=='__main__':main(Path(sys.argv[1]))
