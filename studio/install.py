#!/usr/bin/env python3
"""Configure a private single-user Linux deployment using the existing ai-toolkit venv."""
import argparse,json,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolkit',required=True);p.add_argument('--bind',default='127.0.0.1');p.add_argument('--port',type=int,default=8765)
p.add_argument('--template');p.add_argument('--service',action='store_true');a=p.parse_args()
import ipaddress
address=ipaddress.ip_address(a.bind)
if not (address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')):
 p.error('Use loopback or a Tailscale IPv4 address. Public or LAN binding is not supported.')
if not 1024<=a.port<=65535: p.error('Invalid port')
root=Path(a.toolkit).resolve();here=Path(__file__).resolve().parent
for path in (root,here):
 if any(ch in str(path) for ch in ['\n','\r','"','%']): p.error('Unsupported character in installation path')
python=root/'venv/bin/python'
if not python.exists() or not (root/'run.py').exists(): p.error('Existing ai-toolkit installation required')
r=subprocess.run([str(python),'-c','import fastapi,uvicorn,multipart,PIL,yaml'],capture_output=True,text=True)
if r.returncode: sys.exit('Missing UI dependencies. With your toolkit Python, install requirements-ui.txt; do not reinstall torch or the training environment.')
settings=here/'settings.json'
if settings.exists(): sys.exit('settings.json already exists. Edit it deliberately instead of overwriting an installation.')
template=Path(a.template).resolve() if a.template else None
sources={name:name for name in ('my_dataset','raw_images') if (root/name).is_dir()}
config=dict(toolkit=str(root),data=str(here/'data'),hosts=[f'{a.bind}:{a.port}',f'localhost:{a.port}',f'127.0.0.1:{a.port}'],
            sources=sources,existing_outputs=[str(root/'output/flux_character_lora_full')] if (root/'output/flux_character_lora_full').exists() else [])
if template: config['template']=str(template)
settings.write_text(json.dumps(config,indent=2));settings.chmod(0o600)
print('Settings written. Private address:',f'http://{a.bind}:{a.port}')
if a.service:
 service=Path.home()/'.config/systemd/user/lora-studio.service'
 if service.exists(): sys.exit('Service already exists; settings written but service not replaced.')
 service.parent.mkdir(parents=True,exist_ok=True)
 service.write_text(f'''[Unit]
Description=LoRA Studio private training dashboard
After=network-online.target

[Service]
Type=simple
WorkingDirectory={here}
ExecStart="{python}" -m uvicorn app:app --host {a.bind} --port {a.port} --workers 1 --no-access-log
Restart=on-failure
RestartSec=5
UMask=0077
KillMode=process
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
''')
 subprocess.run(['systemctl','--user','daemon-reload'],check=True)
 subprocess.run(['systemctl','--user','enable','--now','lora-studio.service'],check=True)
 print('User service enabled. Check: systemctl --user status lora-studio')
else:
 print('Run in this directory:',python,'-m uvicorn app:app --host',a.bind,'--port',a.port,'--workers 1')
