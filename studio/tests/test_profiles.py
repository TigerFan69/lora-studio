import unittest,tempfile,json
from pathlib import Path
from training_profiles import profile_config,resolve_profile,profile
from core import build_config
class ProfileTests(unittest.TestCase):
 def test_schnell_unchanged(self):
  args=('test','/tmp/data','/tmp/out','/base','/adapter',20)
  self.assertEqual(profile_config('flux1-schnell',*args),build_config(*args))
 def test_dev_model_and_memory_settings(self):
  c=profile_config('flux1-dev','test','/tmp/data','/tmp/out','/base',None,20)['config']['process'][0]
  self.assertNotIn('assistant_lora_path',c['model'])
  self.assertTrue(c['model']['is_flux']);self.assertTrue(c['model']['low_vram'])
  self.assertTrue(c['train']['cache_text_embeddings']);self.assertEqual(c['datasets'][0]['resolution'],[512])
  self.assertEqual(c['sample']['guidance_scale'],3.5)
 def test_unknown_rejected(self):
  with self.assertRaises(ValueError):profile('made-up-family')
 def test_transformer_only_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'transformer';p.mkdir();(p/'config.json').write_text('{"guidance_embeds":true}');(p/'model.safetensors').touch()
   with self.assertRaisesRegex(ValueError,'missing vae'):
    resolve_profile('flux1-dev','/tmp',{'model_paths':{'flux1-dev':d}})
