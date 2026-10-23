# LoRA Studio — Community Preview

A local, browser-based character LoRA workflow: review images and captions, prepare dataset revisions, train, and copy saved adapters to ComfyUI.

**Prerequisite: a working, compatible Linux NVIDIA ai-toolkit training installation must already be installed before running this package.** This is an add-on Studio, not a fresh-machine training installer. The complete Studio installation on a clean machine has not been verified. A generic latest ai-toolkit checkout is not automatically equivalent to the tested, locally patched runtime.

Current development focuses on Krea 2 LoRAs for 12 GB VRAM cards, with an eventual goal of 8 GB cards. Neither target is established compatibility for this preview; the recorded development baseline is 16 GB. No paid membership is required.

Start with [the prerequisite checklist](docs/PREREQUISITES.md), then [installation](docs/INSTALL.md). Read [validation limits](docs/VALIDATION.md) before choosing training settings. See [GitHub publishing](docs/PUBLISHING.md) to distribute this preview.

The development baseline is Linux with an NVIDIA RTX 4080 16 GB. This does not establish support for every 16 GB GPU or lower-memory card. Krea 2 RAW completed a short 20-step functional test; longer character-quality runs remain to be evaluated.

Includes dataset review, removal/restoration, caption drafts, immutable prepared revisions, training controls, checkpoint downloads, configurable ComfyUI copy destination, and workflow cues. No model weights, credentials, datasets, or trained personal adapters are included. No training or downloads start simply by unpacking this folder.

Studio source is MIT licensed; upstream software and model terms apply separately. This preview is for a trusted single operator on loopback or a private Tailscale connection, not an unauthenticated public website.
