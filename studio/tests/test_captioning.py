import unittest,tempfile
from pathlib import Path
from captioning import graph,apply_draft,digest
from core import atomic_json,read_json
class CaptionTests(unittest.TestCase):
 def test_graph_matches_uploaded_workflow(self):
  g=graph('lora-studio/example.png',42)
  self.assertEqual(g['4']['inputs']['anything'],['2',2])
  self.assertEqual(g['2']['inputs']['task'],'more_detailed_caption')
  self.assertFalse(g['2']['inputs']['keep_model_loaded'])
  self.assertFalse(g['3']['inputs']['convert_to_safetensors'])
 def test_apply_backup_and_conflict(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'source').mkdir();cap=p/'source/photo.txt';cap.write_text('original')
   atomic_json(p/'project.json',{'prepared':'revision'})
   run={'results':[{'name':'photo.png','original_hash':digest(cap),'text':'draft'}]}
   cap.write_text('edited')
   with self.assertRaises(ValueError):apply_draft(p,run,'photo.png','new')
   self.assertEqual(cap.read_text(),'edited')
   cap.write_text('original');apply_draft(p,run,'photo.png','new')
   self.assertEqual(cap.read_text(),'new\n')
   self.assertEqual(next((p/'caption_backups').iterdir()).read_text(),'original')
   self.assertIsNone(read_json(p/'project.json')['prepared'])
   with self.assertRaises(ValueError):apply_draft(p,run,'photo.png','again')
if __name__=='__main__':unittest.main()

class WorkerTests(unittest.TestCase):
 def run_worker(self,uncertain=False,stop=False):
  from unittest.mock import patch
  from PIL import Image
  import caption_runner
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);path=root/'caption_jobs/123456789abc';path.mkdir(parents=True);(root/'jobs').mkdir();source=root/'source';source.mkdir()
   Image.new('RGB',(16,16),'red').save(source/'test.png')
   atomic_json(path/'run.json',dict(id=path.name,status='queued',source=str(source),comfy_root=str(root/'comfy'),items=[dict(name='test.png',original_hash=None)],results=[]))
   if stop:(path/'stop.request').touch()
   calls=[]
   def fake(route,data=None):
    calls.append(route)
    if route=='/queue':return {'queue_running':[],'queue_pending':[]}
    if route=='/prompt':
     if uncertain:raise TimeoutError('unknown')
     return {'prompt_id':data['prompt_id']}
    if route.startswith('/history/'):return {route.split('/')[-1]:{'outputs':{'4':{'text':['A red square.']}},'status':{'status_str':'success'}}}
    raise AssertionError(route)
   with patch.object(caption_runner,'preflight'),patch.object(caption_runner,'call',side_effect=fake):caption_runner.main(path)
   return read_json(path/'run.json'),calls
 def test_success_extracts_draft_without_writing_source(self):
  d,calls=self.run_worker();self.assertEqual(d['status'],'completed');self.assertEqual(d['results'][0]['text'],'A red square.');self.assertNotIn('/interrupt',calls)
 def test_uncertain_submission_is_not_retried(self):
  d,calls=self.run_worker(uncertain=True);self.assertEqual(d['status'],'needs_attention');self.assertEqual(calls.count('/prompt'),1)
 def test_stop_before_image_does_not_submit(self):
  d,calls=self.run_worker(stop=True);self.assertEqual(d['status'],'stopped');self.assertNotIn('/prompt',calls)
