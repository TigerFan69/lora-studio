"""Explicit training profiles; add a family handler before registering another architecture."""
import json
from pathlib import Path
from core import resolve_models, build_config

PROFILES = {
    'flux1-schnell': dict(id='flux1-schnell', family='flux1', family_label='FLUX.1', label='FLUX.1 Schnell', repo='black-forest-labs/FLUX.1-schnell', revision='741f7c3ce8b383c54771c7003378a50191e9efe9', license_url='https://huggingface.co/black-forest-labs/FLUX.1-schnell/blob/main/LICENSE.md', validation='Existing RTX 4080 baseline verified', inference='Schnell base · 4 steps · guidance 1'),
    'flux1-dev': dict(id='flux1-dev', family='flux1', family_label='FLUX.1', label='FLUX.1 Dev', repo='black-forest-labs/FLUX.1-dev', revision='3de623fc3c33e44ffbe2bad470d0f45bccf2eb21', license_url='https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md', validation='20-step Dev GPU smoke test completed on this RTX 4080; full-run quality not verified', inference='Dev base · start with 20–28 steps · guidance 3.5'),
}

from krea_profile import PROFILE as KREA_PROFILE, resolve_krea, config_krea
PROFILES['krea2-raw']=KREA_PROFILE
for _p in PROFILES.values():
    _p.setdefault('preset',{'Resolution':'512 px','Batch':'1','Rank / alpha':'16 / 16','Learning rate':'0.0001','Quantization':'8-bit','Training previews':'Off'})
    _p.setdefault('requirements',{'min_vram_mib':15500,'max_idle_vram_mib':1400,'min_free_disk_bytes':8*1024**3})

def profile(pid):
    if pid not in PROFILES: raise ValueError('Unknown training profile: '+str(pid))
    return PROFILES[pid]

def resolve_flux(p, toolkit, settings):
    if p['id']=='flux1-schnell': return resolve_models(toolkit, settings.get('template'))
    configured=settings.get('model_paths',{}).get(p['id'])
    if configured: base=Path(configured).expanduser().resolve()
    else:
        from huggingface_hub import hf_hub_download
        try: base=Path(hf_hub_download(p['repo'],'transformer/config.json',revision=p['revision'],local_files_only=True)).parent.parent
        except Exception: raise ValueError('Dev is not installed locally. Accept its license on Hugging Face and install the complete pinned Diffusers model; no download was attempted.') from None
    for part in ('transformer','vae','text_encoder','text_encoder_2','tokenizer','tokenizer_2','scheduler'):
        folder=base/part
        if not folder.is_dir(): raise ValueError('Dev installation is incomplete: missing '+part+'. Install the complete Diffusers model; transformer-only/ComfyUI checkpoints cannot train here.')
        if part in ('transformer','vae','text_encoder','text_encoder_2'):
            if not (folder/'config.json').is_file(): raise ValueError('Missing Dev config: '+part)
            indexes=list(folder.glob('*.safetensors.index.json'))
            if indexes:
                for index in indexes:
                    weights=json.loads(index.read_text()).get('weight_map',{})
                    if not weights: raise ValueError('Empty weight index: '+part)
                    for name in set(weights.values()):
                        f=(folder/name).resolve()
                        if not f.is_file(): raise ValueError('Missing Dev weight: '+part+'/'+name)
            elif not any(f.is_file() for f in folder.glob('*.safetensors')): raise ValueError('Missing Dev weights: '+part)
        elif part=='scheduler':
            if not (folder/'scheduler_config.json').is_file(): raise ValueError('Missing Dev scheduler config')
        elif not (folder/'tokenizer_config.json').is_file(): raise ValueError('Missing Dev tokenizer config: '+part)
    cfg=json.loads((base/'transformer/config.json').read_text())
    if cfg.get('guidance_embeds') is not True: raise ValueError('Selected model is not a guidance-enabled FLUX.1 Dev transformer')
    return str(base), None

def config_flux(p, name, dataset, output, base, adapter, steps):
    result=build_config(name,dataset,output,base,adapter,steps)
    if p['id']=='flux1-dev':
        proc=result['config']['process'][0]
        proc['model'].pop('assistant_lora_path')
        proc['sample'].update(guidance_scale=3.5,sample_steps=20)
    return result

FAMILIES={'flux1': (resolve_flux, config_flux),'krea2': (resolve_krea, config_krea)}
def resolve_profile(pid,toolkit,settings):
    p=profile(pid)
    if p['family'] not in FAMILIES: raise ValueError('Unsupported model family')
    return FAMILIES[p['family']][0](p,toolkit,settings)
def profile_config(pid, *args):
    p=profile(pid)
    if p['family'] not in FAMILIES: raise ValueError('Unsupported model family')
    return FAMILIES[p['family']][1](p,*args)
def catalog(toolkit,settings):
    result=[]
    for pid,p in PROFILES.items():
        row=dict(p)
        try: resolve_profile(pid,toolkit,settings); row.update(ready=True,requirement='Local model files available')
        except (ValueError,OSError,KeyError) as exc: row.update(ready=False,requirement=str(exc))
        result.append(row)
    return result
