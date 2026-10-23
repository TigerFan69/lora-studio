# Validation and limits

The development session recorded successful operation on an RTX 4080 (16 GB), Linux, about 32 GB system RAM and substantial swap. This is evidence for that configured machine, not a clean-install certification of this release folder.

Krea 2 RAW: 20 training steps completed; approximately 113 seconds including startup/save, observed GPU peak 12,610 MiB. The saved adapter's tensors were finite and a 512px Turbo inference test with the adapter completed. Sampling GPU memory is not an exact allocator peak. A short functional test does not prove identity quality, 2,000-step stability, 1024px fit, or support on smaller GPUs.

Settings: 512px, batch 1, rank/alpha 16, base uint4, text encoder qfloat8, cached latents/text embeddings, gradient checkpointing, training previews off, learning rate 0.0001. See `krea_profile.py` for the complete profile. Historical Schnell and Dev short tests also completed on the development machine.

The previously recorded runtime used Python 3.12.14, Torch 2.14.1+cu130, Transformers 5.5.3, Diffusers 0.39.0.dev0, bitsandbytes 0.50.2 and optimum-quanto 0.2.4. These observations are not installation instructions or a complete dependency lock. The ai-toolkit runtime had local memory changes. Rebuilding that full runtime on a clean host remains unverified for this Studio release.

The accompanying software tests exercise dataset/configuration and UI behavior; they do not train a model. Run with the compatible toolkit environment, adding its root to PYTHONPATH:

```sh
PYTHONPATH=/path/to/ai-toolkit:. /path/to/ai-toolkit/venv/bin/python -m unittest discover -s tests -v
```

Do not run tests concurrently with real training. Report hardware, selected profile, settings, failure stage and redacted logs. Never attach tokens or private datasets to a public issue.

## Release-folder check (2026-10-22)

All 36 software tests passed in an isolated temporary copy using the existing Linux training environment, with no active training. This replaces the earlier run in which three tests were blocked by the external-training safety guard. These tests do not perform GPU training or establish fresh-machine compatibility. Python and browser JavaScript syntax checks passed in the earlier packaging check; application code has not changed since that check.
