"""Dataset preparation and bounded Schnell configuration, shared by CLI and UI."""
from pathlib import Path
import hashlib, json, re, shutil, tempfile, uuid
from datetime import datetime, timezone
from PIL import Image, ImageOps
import yaml

EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
Image.MAX_IMAGE_PIXELS = 40_000_000

def now():
    return datetime.now(timezone.utc).isoformat()

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)

def read_json(path):
    return json.loads(Path(path).read_text())

def safe_child(root, name):
    if not name or name.startswith('.') or '/' in name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid file name')
    p = (Path(root) / name).resolve()
    if p.parent != Path(root).resolve():
        raise ValueError('Path escapes folder')
    return p

def image_files(folder):
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.is_symlink()
                  and not p.name.startswith('.') and p.suffix.lower() in EXTS)

def clean_caption(text, trigger):
    trigger = ' '.join(trigger.split())
    if not trigger or len(trigger) > 100:
        raise ValueError('Use a trigger phrase between 1 and 100 characters')
    text = ' '.join(text.replace('\ufeff', '').replace('\x00', '').split())
    if not text:
        return ''  # Empty captions require a human description, never fabricate one.
    if not re.search(r'(?<!\w)' + re.escape(trigger) + r'(?!\w)', text, re.I):
        text = trigger + '. ' + text
    return text

def audit(folder, trigger):
    rows, stems, hashes = [], set(), {}
    for p in image_files(folder):
        warnings = []
        caption_path = p.with_suffix('.txt')
        caption = caption_path.read_text(encoding='utf-8', errors='replace') if caption_path.exists() else ''
        if p.stem.casefold() in stems:
            warnings.append('Duplicate filename stem: rename one image and its caption')
        stems.add(p.stem.casefold())
        if not caption.strip(): warnings.append('Missing or empty caption')
        if caption.strip() and not re.search(r'(?<!\w)' + re.escape(trigger) + r'(?!\w)', caption, re.I):
            warnings.append('Trigger phrase missing')
        if len(caption.split()) > 200: warnings.append('Long caption: review unnecessary detail (word count is not token count)')
        if re.search(r'appears to be|difficult to determine|as if|likely',caption,re.I): warnings.append('Speculative wording: verify against the image')
        if re.search(r'high ponytail',caption,re.I) and re.search(r'low ponytail',caption,re.I): warnings.append('Both high and low ponytail mentioned: review consistency')
        width = height = 0
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                width, height = im.size
                im.verify() if hasattr(im, 'verify') else None
            if min(width, height) < 256: warnings.append('Small image: short side below 256 pixels')
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            if digest in hashes: warnings.append('Exact duplicate of ' + hashes[digest])
            hashes[digest] = p.name
        except Exception:
            warnings.append('Unreadable or oversized image')
        rows.append(dict(name=p.name, width=width, height=height, caption=caption,
                         words=len(caption.split()), warnings=warnings))
    return {'count': len(rows), 'images': rows, 'warnings': sum(bool(r['warnings']) for r in rows)}

def prepare(source, destination, trigger, mode='preserve', max_size=2048, clean=True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError('Choose a new output folder outside the source dataset')
    if mode not in ('preserve', 'square'): raise ValueError('Unknown crop mode')
    if max_size not in (512, 768, 1024, 2048): raise ValueError('Unsupported maximum image size')
    files = image_files(source)
    if not files: raise ValueError('Dataset contains no images')
    report = audit(source, trigger)
    if any(any('Duplicate filename' in w or 'Unreadable' in w for w in r['warnings']) for r in report['images']):
        raise ValueError('Fix duplicate filename stems or invalid images first')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.prepare-', dir=destination.parent))
    try:
        for p in files:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                if mode == 'square':
                    side = min(im.size)
                    x, y = (im.width-side)//2, (im.height-side)//2
                    im = im.crop((x,y,x+side,y+side))
                im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                # Standardize format and strip metadata without overwriting source images.
                im.save(staging/(p.stem+'.png'))
            cap = p.with_suffix('.txt')
            text = cap.read_text(encoding='utf-8', errors='replace') if cap.exists() else ''
            (staging/(p.stem+'.txt')).write_text(clean_caption(text, trigger) if clean else text)
        atomic_json(staging/'preparation.json', dict(created=now(), mode=mode, max_size=max_size,
                     clean=clean, trigger=trigger, image_count=len(files)))
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging)
        raise
    return audit(destination, trigger)

def resolve_models(toolkit, template=None):
    if template and Path(template).is_file():
        c = yaml.safe_load(Path(template).read_text())
        m = c['config']['process'][0]['model']
        base, adapter = Path(m['name_or_path']), Path(m['assistant_lora_path'])
    else:
        from huggingface_hub import hf_hub_download
        base = Path(hf_hub_download('black-forest-labs/FLUX.1-schnell', 'transformer/config.json', local_files_only=True)).parent.parent
        adapter = Path(hf_hub_download('ostris/FLUX.1-schnell-training-adapter', 'pytorch_lora_weights.safetensors', local_files_only=True))
    if not base.is_dir() or not adapter.is_file():
        raise ValueError('Schnell base or training adapter is not cached locally; no downloads were attempted')
    for part in ('transformer','vae','text_encoder','text_encoder_2','tokenizer','tokenizer_2','scheduler'):
        if not (base/part).is_dir(): raise ValueError('Cached model is missing '+part)
    for part in ('transformer','vae','text_encoder','text_encoder_2'):
        folder=base/part
        if not (folder/'config.json').is_file(): raise ValueError('Missing model config: '+part)
        indices=list(folder.glob('*.safetensors.index.json'))
        if indices:
            for index in indices:
                for filename in set(json.loads(index.read_text()).get('weight_map',{}).values()):
                    if not (folder/filename).is_file(): raise ValueError('Missing cached weight shard: '+part+'/'+filename)
        elif not any(folder.glob('*.safetensors')):
            raise ValueError('Missing cached weights: '+part)
    return str(base.resolve()), str(adapter.resolve())

def build_config(name, dataset, output, base, adapter, steps=2000):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', name): raise ValueError('Invalid job name')
    if steps not in (20, 500, 1000, 1500, 2000, 3000): raise ValueError('Unsupported step count')
    return dict(job='extension', config=dict(name=name, process=[dict(
        type='sd_trainer', training_folder=str(Path(output).resolve()), device='cuda:0',
        network=dict(type='lora',linear=16,linear_alpha=16),
        save=dict(dtype='float16',save_every=250,max_step_saves_to_keep=4,push_to_hub=False),
        datasets=[dict(folder_path=str(Path(dataset).resolve()),caption_ext='txt',caption_dropout_rate=0.05,
                       shuffle_tokens=False,cache_latents_to_disk=True,resolution=[512])],
        train=dict(batch_size=1,steps=steps,gradient_accumulation_steps=1,train_unet=True,train_text_encoder=False,
                   gradient_checkpointing=True,noise_scheduler='flowmatch',optimizer='adamw8bit',lr=1e-4,
                   ema_config=dict(use_ema=False,ema_decay=0.99),dtype='bf16',disable_sampling=True,
                   cache_text_embeddings=True),
        model=dict(name_or_path=base,assistant_lora_path=adapter,is_flux=True,quantize=True,quantize_te=True,
                   low_vram=True,qtype='qfloat8'),
        sample=dict(sampler='flowmatch',sample_every=250,width=512,height=512,prompts=[],neg='',seed=42,
                    walk_seed=False,guidance_scale=1,sample_steps=4)
    )]), meta=dict(name='[name]',version='1.0'))

def redact(text):
    text = re.sub(r'hf_[A-Za-z0-9]+', '[REDACTED]', text)
    return re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)

def gpu_status():
    import subprocess
    try:
        r = subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu',
                            '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
        if r.returncode: raise RuntimeError()
        a = [x.strip() for x in r.stdout.splitlines()[0].split(',')]
        return dict(name=a[0],used=int(a[1]),total=int(a[2]),utilization=int(a[3]))
    except Exception:
        return dict(name='GPU unavailable',used=None,total=None,utilization=None)

def process_identity(pid):
    try: return Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
    except (OSError,IndexError): return None
