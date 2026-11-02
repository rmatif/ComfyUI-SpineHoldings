import os
import stat
import time
import uuid

from aiohttp import web

import comfy.model_management as model_management
from server import PromptServer


NODE_CLASS_MAPPINGS = {}
INSTANCE_ID = str(uuid.uuid4())
RESOURCE_ROOT = "/mnt/resources/"
SOURCE_FACTORIES = {
    "load_diffusion_model",
    "load_clip_model_patcher",
    "load_checkpoint_guess_config",
    "load_checkpoint_clip_patcher",
    "load_checkpoint_vae_patcher",
    "load_vae_patcher",
}


def source_paths(patcher):
    factory = getattr(patcher, "cached_patcher_init", None)
    if (factory is None
            or getattr(factory[0], "__module__", None) != "comfy.sd"
            or getattr(factory[0], "__name__", None) not in SOURCE_FACTORIES):
        return []
    paths = factory[1][0]
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    return sorted({os.path.realpath(path) for path in paths})


def loaded_models():
    models = []
    for loaded in tuple(model_management.current_loaded_models):
        patcher = loaded.model
        if patcher is None:
            continue
        device = patcher.load_device
        dynamic = patcher.is_dynamic()
        pin_state = getattr(patcher.model, "dynamic_pins", {}).get(device, {})
        models.append({
            "model_id": str(patcher.clone_base_uuid),
            "patches_id": str(patcher.patches_uuid),
            "model_class": type(patcher.model).__name__,
            "source_paths": source_paths(patcher),
            "device": str(device),
            "in_use_by_prompt": pin_state.get("current_prompt") if dynamic else None,
            "model_bytes": patcher.model_size(),
            "vram_bytes": patcher.loaded_size() if device.type == "cuda" else None,
            "ram_bytes": patcher.loaded_ram_size() if dynamic else None,
            "pinned_bytes": patcher.pinned_memory_size() if dynamic else None,
            "dynamic_offloading": dynamic,
        })
    return models


def held_files():
    files = {}
    errors = []

    def entry(path, device, inode):
        deleted = path.endswith(" (deleted)")
        if deleted:
            path = path[:-10]
        if not path.startswith(RESOURCE_ROOT):
            return None
        key = (path, device, inode, deleted)
        return files.setdefault(key, {
            "path": path,
            "device": device,
            "inode": inode,
            "deleted": deleted,
            "mapped_bytes": 0,
            "open_fds": 0,
        })

    try:
        with open("/proc/self/maps", encoding="utf-8") as maps:
            for line in maps:
                fields = line.rstrip("\n").split(maxsplit=5)
                if len(fields) != 6 or fields[4] == "0":
                    continue
                major, minor = (int(part, 16) for part in fields[3].split(":"))
                file = entry(fields[5].replace("\\012", "\n"), f"{major}:{minor}", int(fields[4]))
                if file is not None:
                    start, end = (int(part, 16) for part in fields[0].split("-"))
                    file["mapped_bytes"] += end - start
    except OSError as error:
        errors.append(f"maps: {error.strerror}")

    try:
        for fd in os.listdir("/proc/self/fd"):
            link = f"/proc/self/fd/{fd}"
            try:
                path = os.readlink(link)
                info = os.stat(link)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                file = entry(path, f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}", info.st_ino)
                if file is not None:
                    file["open_fds"] += 1
    except OSError as error:
        errors.append(f"fds: {error.strerror}")

    return sorted(files.values(), key=lambda file: (file["path"], file["inode"])), errors


@PromptServer.instance.routes.get("/spine/holdings")
async def holdings(request):
    running, pending = PromptServer.instance.prompt_queue.get_current_queue()
    models = loaded_models()
    files, errors = held_files()
    return web.json_response({
        "version": 1,
        "instance_id": INSTANCE_ID,
        "pid": os.getpid(),
        "observed_at": time.time(),
        "running_prompts": len(running),
        "pending_prompts": len(pending),
        "model_coverage": "comfy_model_management",
        "models": models,
        "resource_root": RESOURCE_ROOT,
        "files": files,
        "file_scan_complete": not errors,
        "errors": errors,
    }, headers={"Cache-Control": "no-store"})
