import unittest,tempfile
from pathlib import Path
from krea_profile import PROFILE,config_krea,validate_assets
from training_profiles import profile_config,profile
from core import build_config
class KreaTests(unittest.TestCase):
 def config(self):return config_krea(PROFILE,'krea2_test','/tmp/data','/tmp/out','/models/raw.safetensors',{'text_encoder':'/models/te','vae':'/models/vae'},20)['config']['process'][0]
 def test_architecture_is_not_flux(self):
  p=self.config();self.assertEqual(p['model']['arch'],'krea2');self.assertNotIn('is_flux',p['model']);self.assertNotIn('assistant_lora_path',p['model'])
 def test_memory_policy_and_frozen_base(self):
  p=self.config();self.assertEqual(p['device'],'cuda:0');self.assertEqual(p['model']['qtype'],'uint4');self.assertTrue(p['train']['gradient_checkpointing']);self.assertTrue(p['train']['cache_text_embeddings']);self.assertFalse(p['train']['train_text_encoder']);self.assertEqual(p['datasets'][0]['resolution'],[512]);self.assertTrue(p['train']['disable_sampling'])
 def test_invalid_steps_rejected(self):
  with self.assertRaises(ValueError):config_krea(PROFILE,'test','/tmp/data','/tmp/out','raw',{},-5)
 def test_missing_raw_blocks(self):
  with self.assertRaises(ValueError):validate_assets({'raw':'/not-present/raw.safetensors'})
 def test_existing_schnell_unchanged(self):
  args=('test','/tmp/data','/tmp/out','/base','/adapter',20)
  self.assertEqual(profile_config('flux1-schnell',*args),build_config(*args))
 def test_profile_registered(self):self.assertEqual(profile('krea2-raw')['family'],'krea2')
 def test_installed_config_classes(self):
  from toolkit.config_modules import ModelConfig,TrainConfig,DatasetConfig,NetworkConfig
  p=self.config();m=ModelConfig(**p['model']);t=TrainConfig(**p['train']);d=DatasetConfig(**p['datasets'][0]);n=NetworkConfig(**p['network'])
  self.assertEqual(m.arch,'krea2');self.assertEqual(m.qtype,'uint4');self.assertEqual(t.steps,20)
