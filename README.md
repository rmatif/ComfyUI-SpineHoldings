# ComfyUI-SpineHoldings

Read-only model and resource-file diagnostics for Civitai's ComfyUI containers.

## Installation

Clone this repository into ComfyUI's `custom_nodes` directory and restart ComfyUI.
No additional dependencies are required. Container builds should pin a commit.

```bash
git clone https://github.com/rmatif/ComfyUI-SpineHoldings.git custom_nodes/ComfyUI-SpineHoldings
```

## Endpoint

`GET /spine/holdings` (also available at `/api/spine/holdings`) reports:

- Comfy-managed model identities, known source paths and devices.
- Reported VRAM, RAM and pinned weight bytes, plus prompt-use state where available.
- Files mapped or open under `/mnt/resources/`, including inode, mapping size, open descriptors and deleted-file status.
- Process identity, observation time, queue counts and file-scan completeness.

Unknown measurements are `null`. Model bytes use Comfy's weight accounting, not
total process or GPU memory. Mapped bytes are address ranges, not resident RAM.
Source paths come from known core loaders and do not include a complete history
of applied LoRAs. Models managed privately by custom nodes are not covered by the
model list, though their mapped or open resource files can appear in the file list.

This is a best-effort snapshot, not an eviction lock. The endpoint neither loads
nor unloads models. Keep it on the worker's internal network. It relies on the
Civitai ComfyUI fork's model-management internals and Linux procfs.
