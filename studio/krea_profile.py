"""Krea 2 RAW training profile. Local pinned assets only; no implicit downloads."""
from pathlib import Path
import json

ASSETS = {
 'raw': ('krea/Krea-2-Raw','6b0ece7fffb640c5e3bcbe0a7f10f66b8e60a603','raw.safetensors'),
 'text_encoder': ('Qwen/Qwen3-VL-4B-Instruct','ebb281ec70b05090aa6165b016eac8ec08e71b17','config.json'),
 'vae': ('Qwen/Qwen-Image','75e0b4be04f60ec59a75f475837eced720f823b6','vae/config.json'),
}
PROFILE=dict(id='krea2-raw',family='krea2',family_label='Krea 2',label='Krea 2 RAW · character training',repo=ASSETS['raw'][0],revision=ASSETS['raw'][1],license_url='https://huggingface.co/krea/Krea-2-Raw',validation='20-step RTX 4080 test passed: 12,610 MiB observed peak. Full-run quality not yet verified',inference='Krea 2 Turbo · 8 steps · CFG disabled (ComfyUI CFG 1); 512px preview with trained adapter tested',preset={'Resolution':'512 px','Batch':'1','Rank / alpha':'16 / 16','Learning rate':'0.0001','Frozen base':'4-bit uint4','Training previews':'Off'},requirements={'min_vram_mib':15500,'max_idle_vram_mib':1400,'min_free_disk_bytes':8*1024**3})

def cached_assets(settings):
 from huggingface_hub import hf_hub_download
 overrides=settings.get('krea2_paths',{})
 result={}
 for kind,(repo,revision,filename) in ASSETS.items():
  if overrides.get(kind):path=Path(overrides[kind]).expanduser().resolve()
  else:
   try: path=Path(hf_hub_download(repo,filename,revision=revision,local_files_only=True))
   except Exception: raise ValueError('Krea 2 setup required: missing '+kind+'. See the model access link and server setup guide; Studio does not download models.') from None
   if kind=='text_encoder':path=path.parent
   if kind=='vae':path=path.parent.parent
  result[kind]=str(path)
 return result

def validate_assets(paths):
 from safetensors import safe_open
 raw=Path(paths['raw'])
 if not raw.is_file():raise ValueError('Krea 2 RAW checkpoint is missing')
 with safe_open(str(raw),framework='pt',device='cpu') as f:
  keys=set(f.keys())
  if not {'first.weight','last.linear.weight'}.issubset(keys):
   raise ValueError('Krea 2 RAW must use the official original checkpoint format, not a Flux or quantized ComfyUI file')
 for kind,sub in [('text_encoder',''),('vae','vae')]:
  root=Path(paths[kind])/sub
  if not (root/'config.json').is_file():raise ValueError('Missing Krea '+kind+' config')
  indices=list(root.glob('*.safetensors.index.json'))
  if indices:
   for index in indices:
    weights=json.loads(index.read_text()).get('weight_map',{})
    if not weights:raise ValueError('Empty '+kind+' weight index')
    for name in set(weights.values()):
     if not (root/name).is_file():raise ValueError('Missing '+kind+' shard: '+name)
  elif not any(p.is_file() for p in root.glob('*.safetensors')):raise ValueError('Missing '+kind+' weights')
 if not (Path(paths['text_encoder'])/'tokenizer_config.json').is_file():raise ValueError('Missing Krea tokenizer')
 return paths

def resolve_krea(p, toolkit, settings):
 if not (Path(toolkit)/'extensions_built_in/diffusion_models/krea2/krea2.py').is_file():raise ValueError('Installed trainer lacks Krea 2 support')
 assets=validate_assets(cached_assets(settings))
 return assets['raw'],assets

def config_krea(p,name,dataset,output,base,assets,steps):
 import re
 if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}',name):raise ValueError('Invalid job name')
 if steps not in (20,500,1000,1500,2000,3000):raise ValueError('Unsupported step count')
 if p.get('max_test_steps') and steps>p['max_test_steps']:raise ValueError('Krea 2 is limited to a 20-step smoke test until hardware validation is complete')
 return dict(job='extension',config=dict(name=name,process=[dict(
  type='sd_trainer',training_folder=str(Path(output).resolve()),device='cuda:0',
  network=dict(type='lora',linear=16,linear_alpha=16),
  save=dict(dtype='float16',save_every=250,max_step_saves_to_keep=4,push_to_hub=False),
  datasets=[dict(folder_path=str(Path(dataset).resolve()),caption_ext='txt',caption_dropout_rate=0.05,shuffle_tokens=False,cache_latents_to_disk=True,resolution=[512])],
  train=dict(batch_size=1,steps=steps,gradient_accumulation_steps=1,train_unet=True,train_text_encoder=False,gradient_checkpointing=True,noise_scheduler='flowmatch',timestep_type='linear',optimizer='adamw8bit',lr=1e-4,ema_config=dict(use_ema=False),dtype='bf16',disable_sampling=True,cache_text_embeddings=True),
  model=dict(arch='krea2',name_or_path=base,quantize=True,qtype='uint4',quantize_te=True,qtype_te='qfloat8',low_vram=True,model_kwargs=dict(text_encoder_path=assets['text_encoder'],vae_path=assets['vae'],max_text_length=256)),
  sample=dict(sampler='flowmatch',sample_every=250,width=512,height=512,prompts=[],neg='',seed=42,walk_seed=False,guidance_scale=3.5,sample_steps=52)
 )]),meta=dict(name='[name]',version='1.0'))
