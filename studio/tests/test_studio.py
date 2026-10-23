import os, sys, tempfile, unittest, shutil, json, subprocess, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from core import clean_caption,prepare,audit,safe_child,build_config,atomic_json,process_identity

class DatasetTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
  Image.new('RGB',(800,400),'red').save(self.source/'image.png')
  (self.source/'image.txt').write_text('A woman with short hair.\n')
 def tearDown(self): self.temp.cleanup()
 def test_clean_is_idempotent_and_preserves_details(self):
  text='A woman wearing a teal t-shirt.'
  clean=clean_caption(text,'ohwx woman')
  self.assertEqual(clean_caption(clean,'ohwx woman'),clean)
  self.assertIn('teal t-shirt',clean);self.assertEqual(clean_caption('','ohwx woman'),'')
 def test_preserve_and_square_are_non_destructive(self):
  before=(self.source/'image.png').read_bytes()
  r=prepare(self.source,self.root/'prepared','ohwx woman','preserve',512)
  self.assertEqual((r['images'][0]['width'],r['images'][0]['height']),(512,256))
  r=prepare(self.source,self.root/'square','ohwx woman','square',512)
  self.assertEqual((r['images'][0]['width'],r['images'][0]['height']),(400,400))
  self.assertEqual((self.source/'image.png').read_bytes(),before)
  with self.assertRaises(ValueError): prepare(self.source,self.root/'prepared','ohwx woman')
 def test_hidden_and_collision(self):
  (self.source/'._image.png').write_bytes(b'junk');self.assertEqual(audit(self.source,'ohwx')['count'],1)
  Image.new('RGB',(500,500)).save(self.source/'image.jpg')
  with self.assertRaises(ValueError): prepare(self.source,self.root/'out','ohwx')
 def test_path_bounds(self):
  for n in ['../secret','/etc/passwd','.env','a/b','a\\b']:
   with self.assertRaises(ValueError): safe_child(self.source,n)
 def test_config(self):
  c=build_config('test_job',self.source,self.root/'output','/models/base','/models/adapter',20)
  s=c['config']['process'][0]
  self.assertEqual(s['train']['batch_size'],1);self.assertTrue(s['train']['cache_text_embeddings'])
  self.assertTrue(s['train']['disable_sampling']);self.assertFalse(s['save']['push_to_hub'])
  with self.assertRaises(ValueError): build_config('test',self.source,self.root,'x','y',-1)

class HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);toolkit=cls.root/'toolkit';toolkit.mkdir();(toolkit/'my_dataset').mkdir()
  Image.new('RGB',(512,512),'green').save(toolkit/'my_dataset/a.png');(toolkit/'my_dataset/a.txt').write_text('ohwx woman, short hair')
  model=cls.root/'base'
  for part in ['transformer','vae','text_encoder','text_encoder_2','tokenizer','tokenizer_2','scheduler']:(model/part).mkdir(parents=True)
  for part in ['transformer','vae','text_encoder','text_encoder_2']:
   (model/part/'config.json').write_text('{}');(model/part/'model.safetensors').write_bytes(b'fixture')
  adapter=cls.root/'adapter.safetensors';adapter.write_bytes(b'test')
  import yaml
  template=cls.root/'template.yaml';template.write_text(yaml.safe_dump({'config':{'process':[{'model':{'name_or_path':str(model),'assistant_lora_path':str(adapter)}}]}}))
  setting=cls.root/'settings.json';atomic_json(setting,dict(toolkit=str(toolkit),data=str(cls.root/'data'),hosts=['testserver'],template=str(template)))
  os.environ['LORA_STUDIO_SETTINGS']=str(setting)
  import app
  cls.app=app
  from fastapi.testclient import TestClient
  cls.client=TestClient(app.app);cls.headers={'X-Studio-Request':'1'}
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def make_project(self):
  r=self.client.post('/api/projects',headers=self.headers,json=dict(name='Test',trigger='ohwx woman',source='my_dataset'));self.assertEqual(r.status_code,200,r.text);return r.json()['id']
 def test_history_removal_and_restore(self):
  pid=self.make_project();self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  job=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20}).json()
  for kind,key in [('projects',pid),('jobs',job['id'])]:
   self.assertEqual(self.client.post(f'/api/{kind}/{key}/history',headers=self.headers,json={'removed':True}).status_code,200)
   row=next(x for x in self.client.get('/api/state').json()[kind] if x['id']==key);self.assertTrue(row['removed'])
   self.assertEqual(self.client.post(f'/api/{kind}/{key}/history',headers=self.headers,json={'removed':False}).status_code,200)
  self.assertTrue(Path(job['dataset']).is_dir())
  with patch.object(self.app,'job_record',return_value={**job,'status':'running'}):
   self.assertEqual(self.client.post(f'/api/jobs/{job['id']}/history',headers=self.headers,json={'removed':True}).status_code,400)
 def test_publish_replaces_cleanly_and_backs_up(self):
  pid=self.make_project()
  self.assertEqual(self.client.post(f'/api/projects/{pid}/publish',headers=self.headers,json={}).status_code,400)
  self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  old=self.app.TOOLKIT/'my_dataset/old.txt';old.write_text('preserve this')
  r=self.client.post(f'/api/projects/{pid}/publish',headers=self.headers,json={});self.assertEqual(r.status_code,200,r.text)
  self.assertFalse(old.exists());self.assertEqual((Path(r.json()['backup'])/'old.txt').read_text(),'preserve this')
  self.assertEqual(sorted(x.name for x in (self.app.TOOLKIT/'my_dataset').iterdir()),['a.png','a.txt'])
  self.assertTrue((self.app.PROJECTS/pid/'source/a.png').exists())
 def test_upload_keeps_raw_batches_separate(self):
  import io
  buf=io.BytesIO();Image.new('RGB',(512,512),'blue').save(buf,format='PNG')
  batches=[]
  for caption in [b'first caption',b'second caption']:
   r=self.client.post('/api/upload',headers=self.headers,data={'name':'Upload test','trigger':'test'},files=[('files',('same.png',buf.getvalue(),'image/png')),('files',('same.txt',caption,'text/plain'))])
   self.assertEqual(r.status_code,200,r.text);d=r.json();batch=Path(d['raw_batch']);batches.append(batch)
   self.assertEqual(batch.parent,self.app.TOOLKIT/'raw_images');self.assertEqual((batch/'same.txt').read_bytes(),caption)
   self.assertTrue((self.app.PROJECTS/d['id']/'source/same.png').exists())
  self.assertNotEqual(batches[0],batches[1]);self.assertEqual((batches[0]/'same.txt').read_bytes(),b'first caption')
 def test_comfy_service_controls(self):
  from types import SimpleNamespace
  with patch.dict(self.app.settings,{'manage_comfyui':True}),patch.object(self.app,'caption_runs',return_value=[]),patch.object(self.app,'jobs_list',return_value=[]),patch.object(self.app,'comfy_status',return_value={'status':'active'}),patch.object(self.app.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
   with patch.object(self.app,'comfy_call',return_value={'queue_running':[['work']], 'queue_pending':[]}):
    self.assertEqual(self.client.post('/api/comfyui/stop',headers=self.headers,json={}).status_code,400);run.assert_not_called()
   with patch.object(self.app,'comfy_call',return_value={'queue_running':[], 'queue_pending':[]}):
    self.assertEqual(self.client.post('/api/comfyui/stop',headers=self.headers,json={}).status_code,200)
    self.assertEqual(run.call_args.args[0],['/usr/bin/sudo','-n','/usr/bin/systemctl','stop','comfyui.service'])
   with patch.object(self.app,'jobs_list',return_value=[{'status':'running'}]):
    self.assertEqual(self.client.post('/api/comfyui/start',headers=self.headers,json={}).status_code,400)
 def test_dev_job_isolates_cache_and_records_profile(self):
  pid=self.make_project()
  r=self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={});self.assertEqual(r.status_code,200,r.text)
  original=self.app.PROJECTS/pid/'prepared'/r.json()['project']['prepared']
  (original/'stale-cache.bin').write_bytes(b'old embeddings')
  with patch.object(self.app,'resolve_profile',return_value=('/dev-model',None)):
   r=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20,'profile_id':'flux1-dev'})
  self.assertEqual(r.status_code,200,r.text);job=r.json()
  self.assertEqual(job['profile_id'],'flux1-dev');self.assertEqual(job['family'],'flux1')
  dataset=Path(job['dataset']);self.assertNotEqual(dataset,original)
  self.assertTrue((dataset/'a.png').is_file());self.assertTrue((dataset/'a.txt').is_file())
  self.assertFalse((dataset/'stale-cache.bin').exists());self.assertTrue((original/'stale-cache.bin').exists())
  import yaml
  config=yaml.safe_load((self.app.JOBS/job['id']/'config.yaml').read_text())
  self.assertNotIn('assistant_lora_path',config['config']['process'][0]['model'])

 def test_bulk_caption_apply_is_idempotent(self):
  from captioning import digest
  pid=self.make_project();root=self.app.PROJECTS/pid;rid='abcdef123456';folder=self.app.CAPTIONS/rid;folder.mkdir(exist_ok=True)
  atomic_json(folder/'run.json',{'id':rid,'project':pid,'status':'completed','results':[{'name':'a.png','original_hash':digest(root/'source/a.txt'),'text':'ohwx woman, new caption','applied':False}]})
  r=self.client.post(f'/api/captioning/{rid}/apply-all',headers=self.headers,json={});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['saved'],1)
  self.assertEqual(self.client.post(f'/api/captioning/{rid}/apply-all',headers=self.headers,json={}).json()['saved'],0)
  self.assertEqual((root/'source/a.txt').read_text(),'ohwx woman, new caption\n')
 def test_adapter_history_preserves_files(self):
  pid=self.make_project();self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  job=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20}).json()
  folder=Path(job['output'])/job['name'];folder.mkdir(parents=True,exist_ok=True);f=folder/'test.safetensors';f.write_bytes(b'fixture')
  state=self.client.get('/api/state').json();entry=next(j for j in state['jobs'] if j['id']==job['id'])['checkpoints'][0];self.assertGreater(entry['modified'],0)
  for removed in [True,False]:
   r=self.client.post('/api/library/history',headers=self.headers,json={'url':entry['url'],'removed':removed});self.assertEqual(r.status_code,200,r.text)
   self.assertEqual(entry['url'] in self.client.get('/api/state').json()['removed_adapters'],removed);self.assertEqual(f.read_bytes(),b'fixture')
  self.assertEqual(self.client.post('/api/library/history',headers=self.headers,json={'url':'/etc/passwd'}).status_code,400)
 def test_cross_origin_rejected(self):
  self.assertEqual(self.client.post('/api/projects',json={}).status_code,403)
  self.assertEqual(self.client.post('/api/projects',headers={**self.headers,'Origin':'http://evil.test'},json={}).status_code,403)
  self.assertEqual(self.client.get('/api/state',headers={'Host':'evil.test'}).status_code,403)
 def test_edit_prepare_job_snapshot(self):
  pid=self.make_project()
  r=self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={});self.assertEqual(r.status_code,200,r.text)
  r=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20});self.assertEqual(r.status_code,200,r.text);job=r.json()
  snapshot=Path(job['dataset'])/'a.txt';before=snapshot.read_text()
  r=self.client.put(f'/api/projects/{pid}/captions/a.png',headers=self.headers,json={'text':'ohwx woman, blue coat'});self.assertEqual(r.status_code,200)
  self.assertEqual(snapshot.read_text(),before)
  self.assertIsNone(self.client.get(f'/api/projects/{pid}').json()['project']['prepared'])
  self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'project':pid}).status_code,400)
  self.assertEqual(self.client.get(f'/api/jobs/{job["id"]}/config').status_code,200)
  self.assertEqual(self.client.get(f'/api/projects/{pid}/images/a.png').status_code,200)
 def test_upload_traversal_and_empty_captions(self):
  r=self.client.post('/api/upload',headers=self.headers,data={'name':'bad','trigger':'abc'},files=[('files',('../escape.txt',b'test','text/plain'))]);self.assertEqual(r.status_code,400)
  pid=self.make_project();self.client.put(f'/api/projects/{pid}/captions/a.png',headers=self.headers,json={'text':''})
  self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'project':pid}).status_code,400)
 def test_start_checks_without_launch(self):
  pid=self.make_project();self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  job=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20}).json()
  with patch.object(self.app,'gpu_status',return_value={'used':3000,'total':16376,'name':'test','utilization':0}):
   r=self.client.post(f'/api/jobs/{job["id"]}/start',headers=self.headers,json={})
   self.assertEqual(r.status_code,400);self.assertIn('Free GPU',r.text)
 def test_start_dispatch_and_single_job_guard(self):
  pid=self.make_project();self.client.post(f'/api/projects/{pid}/prepare',headers=self.headers,json={})
  job=self.client.post('/api/jobs',headers=self.headers,json={'project':pid,'steps':20}).json()
  with patch.object(self.app,'gpu_status',return_value={'used':300,'total':16376,'name':'test','utilization':0}), patch.object(self.app.subprocess,'Popen') as spawn:
   r=self.client.post(f'/api/jobs/{job["id"]}/start',headers=self.headers,json={})
   self.assertEqual(r.status_code,200,r.text)
   args=spawn.call_args.args[0]
   self.assertTrue(args[1].endswith('runner.py'));self.assertTrue(spawn.call_args.kwargs['start_new_session'])
   self.assertEqual(self.client.post(f'/api/jobs/{job["id"]}/start',headers=self.headers,json={}).status_code,400)
   stop=self.client.post(f'/api/jobs/{job["id"]}/stop',headers=self.headers,json={})
   self.assertEqual(stop.status_code,200)
  path=self.app.JOBS/job['id']/'job.json';d=json.loads(path.read_text());d['status']='stopped';atomic_json(path,d)
 def test_redaction(self):
  from core import redact
  self.assertNotIn('hf_fake123',redact('token hf_fake123'))

class RunnerTests(unittest.TestCase):
 def test_runner_completion_requires_artifact(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);tk=root/'toolkit';(tk/'venv/bin').mkdir(parents=True)
   (tk/'venv/bin/python').symlink_to(sys.executable)
   final=root/'output/fake/fake.safetensors'
   (tk/'run.py').write_text('from pathlib import Path\np=Path('+repr(str(final))+')\np.parent.mkdir(parents=True)\np.write_bytes(b"fake-test-artifact")\n')
   job=root/'jobs/test';job.mkdir(parents=True)
   atomic_json(job/'job.json',dict(id='test',toolkit=str(tk),output=str(root/'output'),name='fake',status='queued'))
   runner=Path(__file__).resolve().parents[1]/'runner.py'
   subprocess.run([sys.executable,str(runner),str(job)],check=True,timeout=10)
   self.assertEqual(json.loads((job/'job.json').read_text())['status'],'completed')
 def test_runner_stop_is_persisted_without_real_training(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);tk=root/'toolkit';(tk/'venv/bin').mkdir(parents=True)
   (tk/'venv/bin/python').symlink_to(sys.executable)
   (tk/'run.py').write_text('import time\ntry:\n time.sleep(60)\nexcept KeyboardInterrupt:\n print("Job stopped")\n')
   job=root/'jobs/test';job.mkdir(parents=True)
   atomic_json(job/'job.json',dict(id='test',toolkit=str(tk),output=str(root/'output'),name='fake',status='queued'))
   runner=Path(__file__).resolve().parents[1]/'runner.py'
   child=subprocess.Popen([sys.executable,str(runner),str(job)])
   try:
    for _ in range(100):
     d=json.loads((job/'job.json').read_text())
     if d.get('child_pid'):break
     time.sleep(.05)
    (job/'stop.request').touch()
    child.wait(timeout=10)
    d=json.loads((job/'job.json').read_text());self.assertEqual(d['status'],'stopped')
   finally:
    if child.poll() is None:child.terminate();child.wait()

if __name__=='__main__':unittest.main()
