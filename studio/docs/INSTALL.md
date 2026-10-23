# Install onto an existing compatible training host

Use Python 3.12 (the tested runtime) or a compatible newer version; older Python is not supported by this preview.

First complete [PREREQUISITES.md](PREREQUISITES.md). This installer configures Studio only. It does not install ai-toolkit, PyTorch, CUDA, ComfyUI, custom nodes, or model weights. A fresh-machine end-to-end installation of this release has not been tested.

1. Place this folder in a new location on the Linux server. Do not overlay an existing Studio installation. Back up any existing Studio settings and data before changing an installation.
2. Activate or identify the existing ai-toolkit virtual environment. If UI packages are missing, install them with that environment's Python after recording/backing up its package state:

```sh
/path/to/ai-toolkit/venv/bin/python -m pip freeze > environment-before-studio.txt
/path/to/ai-toolkit/venv/bin/python -m pip install -r requirements-ui.txt
```

These commands assume the current directory is this release folder. Inspect proposed dependency changes first on a working training host; the UI requirements are version ranges, not a reproducible training environment lock.

3. Configure Studio with one command once prerequisites are present:

```sh
python3 install.py --toolkit /path/to/ai-toolkit
```

The installer prints the startup command. Run it from this folder and open `http://127.0.0.1:8765` on the server. Alternatively add `--service` to create and start a user systemd service. Use `--bind YOUR_TAILSCALE_IP` for private remote access. The installer refuses to overwrite existing settings or an existing service.

For Schnell, `--template /path/to/known-working-training.yaml` explicitly selects your existing base and training-adapter paths. Without it, Studio uses the locally cached default Schnell files; that fallback does not enforce a model revision. Keep the known-working template for reproducibility.

4. With Studio stopped, adjust `settings.json` if necessary: `comfy_root` is the absolute ComfyUI directory (default: a sibling of ai-toolkit). `model_paths` can map `flux1-dev` to the complete local model directory. `krea2_paths` can specify `raw` (checkpoint file), `text_encoder` (complete directory), and `vae` (repository root containing `vae/`). Otherwise Dev/Krea use the pinned local caches referenced in the source. Studio does not download missing training models.
5. Open Studio, create a project, upload images, review captions and remove unwanted images, then prepare a dataset revision. Choose only a locally ready profile. Confirm the selected model family and available GPU memory before starting a short test.
6. Inspect completion, logs, and a saved adapter before trying a longer run. Begin quality evaluation at 500 steps with the tested settings unchanged; 2,000 steps is available but is not a validated quality or long-run stability guarantee.
7. Use **04 Settings** for the destination folder, then **Copy to ComfyUI**, or **Download to computer** for a local browser download.

## Safety, stopping and rollback

This is a trusted single-user application with filesystem access and no login system. Keep it private. Never expose it directly to the internet.

Stop training through Studio and wait for it to finish stopping before stopping the web service. The service intentionally uses KillMode=process: stopping it alone may leave a detached training/caption worker running. Inspect the GPU and running jobs before restarting or switching versions.

For a service installation, `systemctl --user disable --now lora-studio.service` stops/disables the UI. Preserve `settings.json`, `data/`, output adapters and any custom destination files. To roll back, restore the previous application folder and its service configuration, then reload user systemd and start that version. Do not overwrite newer data with an older backup without first preserving it. Manual startup can be stopped with Ctrl-C once jobs are stopped.

The installer never deletes existing data or installs model weights. If service creation fails after settings were written, review those settings before retrying; do not delete an existing installation's configuration blindly.
