#!/usr/bin/env python3
"""Check known low-VRAM guards; optional narrow patch for compatible legacy Flux loaders."""
import argparse, shutil, sys, uuid
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('toolkit');p.add_argument('--apply',action='store_true');a=p.parse_args()
root=Path(a.toolkit);model=root/'toolkit/stable_diffusion_model.py';trainer=root/'jobs/process/BaseSDTrainProcess.py'
s=model.read_text();t=trainer.read_text();changes=[]
# Do not replace whole files or guess at different toolkit architectures.
start=s.index('            self.print_and_status_update("Loading T5")',s.index('Quantizing transformer'))
end=s.index('        elif self.model_config.is_lumina2:',start);part=s[start:end]
for old,new in [('text_encoder.to(self.device_torch, dtype=dtype)','text_encoder.to("cpu" if self.low_vram else self.device_torch, dtype=dtype)'),('text_encoder[0].to(self.device_torch)','text_encoder[0].to("cpu" if self.low_vram else self.device_torch)'),('text_encoder[1].to(self.device_torch)','text_encoder[1].to("cpu" if self.low_vram else self.device_torch)')]:
 if new in part: continue
 if part.count(old)!=1: sys.exit('Unrecognized loader; review manually. No files changed.')
 part=part.replace(old,new);changes.append(old)
s=s[:start]+part+s[end:]
old='    def prepare_accelerator(self):\n'
if 'if self.is_caching_text_embeddings and self.model_config.low_vram:' not in t:
 if t.count(old)!=1: sys.exit('Unrecognized trainer; review manually. No files changed.')
 t=t.replace(old,old+'        # Cached captions no longer need GPU text encoders when preparing the transformer.\n        if self.is_caching_text_embeddings and self.model_config.low_vram:\n            self.sd.text_encoder_to("cpu")\n            self.sd.vae.to("cpu")\n            flush()\n');changes.append('cached text encoder offload before accelerator')
if 'text_encoder_2.to("cpu", dtype=dtype)' not in s[start:end]:
 sys.exit('CPU T5 loading prerequisite missing. Review your loader before using this helper. No files changed.')
compile(s,str(model),'exec');compile(t,str(trainer),'exec')
if changes and a.apply:
 backup=root/'work'/('lora_studio_loader_backup_'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True)
 shutil.copy2(model,backup/model.name);shutil.copy2(trainer,backup/trainer.name)
 model.write_text(s);trainer.write_text(t);print('Applied; originals at',backup)
elif changes:
 print('Changes needed:',*changes,sep='\n- ');sys.exit(2)
else: print('Known low-VRAM guards are present; no changes made.')
