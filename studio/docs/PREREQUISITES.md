# Before installing: prerequisite checklist

## Required for Studio and training

- [ ] Linux host; the browser can run on another computer. Windows/macOS training is not validated by this preview.
- [ ] NVIDIA GPU and a working NVIDIA driver, confirmed with `nvidia-smi`. Tested baseline: RTX 4080 with 16 GB VRAM. Close other GPU workloads before training.
- [ ] Adequate system RAM, swap, and disk space. The development machine had about 32 GB RAM and substantial swap. Reserve space for complete model downloads, caches, dataset copies, and checkpoints; a 26.3 GB RAW file is only one part of the installation. A minimum RAM/disk specification has not been established.
- [ ] [ai-toolkit](https://github.com/ostris/ai-toolkit) already installed and able to train using the intended profile, with `run.py` and `venv/bin/python`. Krea 2 requires the Krea 2 trainer extension. The tested runtime includes local memory-management changes; unmodified upstream installation parity is unverified.
- [ ] Python and all ai-toolkit dependencies in that environment, including a CUDA-enabled PyTorch build compatible with the NVIDIA driver, Transformers, Diffusers, bitsandbytes, optimum-quanto, Hugging Face Hub, and safetensors. Follow the trainer's requirements; do not replace a working Torch/CUDA stack merely to install the UI. A separately installed CUDA toolkit is needed only if a dependency requires compilation, not simply because Studio uses a GPU.
- [ ] Studio UI packages: FastAPI, Uvicorn, python-multipart, Pillow, and PyYAML (see `requirements-ui.txt`). The supplied ranges are not a fully locked environment.
- [ ] The complete locally downloaded assets for the selected training profile, with access/license requirements handled by the user. Model weights are not bundled. ComfyUI-only quantized checkpoints generally cannot replace the training assets.
- [ ] A modern browser, write permission to Studio's data directory, and permission to read model/dataset paths.

## Required for ComfyUI copy and generation

- [ ] [ComfyUI](https://github.com/Comfy-Org/ComfyUI) installed on the same server, with its own working dependencies and the intended inference model, text encoder, and VAE.
- [ ] A writable LoRA destination (normally `ComfyUI/models/loras`). Configure custom destinations in **04 Settings**. Copying a file does not establish compatibility with every model family.
- [ ] Refresh ComfyUI's model list after copying. Do not generate while a memory-intensive training job is running on the same GPU.

## Additional requirements for automatic caption drafts

- [ ] ComfyUI running at `http://127.0.0.1:8188` on the Studio server; this preview's caption endpoint is fixed to that address.
- [ ] [ComfyUI-Florence2](https://github.com/kijai/ComfyUI-Florence2) custom nodes and their dependencies. **Florence2Run is a node in this project, not a separate application to install.** The workflow also requires `DownloadAndLoadFlorence2Model`.
- [ ] [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use), providing the `easy showAnything` node, and its dependencies.
- [ ] [Florence-2-large-PromptGen-v2.0](https://huggingface.co/MiaoshouAI/Florence-2-large-PromptGen-v2.0) complete model files under `ComfyUI/models/LLM/Florence-2-large-PromptGen-v2.0`, including `model.safetensors`.
- [ ] A working caption workflow with the node interfaces used in `workflows/florence_caption_api.json`. Current clean-install compatibility of all custom-node versions is not certified. Manual caption editing remains available without automatic captioning.

## Optional

- [ ] User systemd for `--service` startup.
- [ ] Tailscale for private remote browser access, or an SSH tunnel to loopback. No public port forwarding is required.
- [ ] Git for obtaining source and reporting changes; not required just to unpack and run this folder.

## Model sources and terms

- Schnell: [model and license](https://huggingface.co/black-forest-labs/FLUX.1-schnell), plus [Schnell training adapter](https://huggingface.co/ostris/FLUX.1-schnell-training-adapter). Obtain the full Diffusers model, not only its transformer.
- Dev: [model, access and license](https://huggingface.co/black-forest-labs/FLUX.1-dev). Obtain the full Diffusers model. Its terms differ from Schnell.
- Krea 2 RAW: [model, access and terms](https://huggingface.co/krea/Krea-2-Raw), [Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct), and the VAE from [Qwen-Image](https://huggingface.co/Qwen/Qwen-Image). Exact asset revisions used by the profile are in `krea_profile.py`.

Download directly from the respective publisher and review each license. No redistribution permission for model weights is conveyed by this package. Gated/restricted weights must not be added to the public release. Model access tokens belong in the user's local credential store, never in GitHub.
