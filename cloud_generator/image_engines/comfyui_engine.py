"""Local ComfyUI image engine used by the desktop queue renderer."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from ..config import PROJECT_ROOT
except ImportError:
    from config import PROJECT_ROOT


def _request_json(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 15) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _replace_workflow(value, prompt: str, seed: int, width: int, height: int):
    if isinstance(value, dict):
        output = {key: _replace_workflow(item, prompt, seed, width, height) for key, item in value.items()}
        if value.get("class_type") in {"EmptyLatentImage", "EmptySD3LatentImage"}:
            inputs = output.get("inputs", {})
            inputs["width"] = width
            inputs["height"] = height
        return output
    if isinstance(value, list):
        return [_replace_workflow(item, prompt, seed, width, height) for item in value]
    if isinstance(value, str):
        if value == "__SEED__":
            return int(seed)
        return value.replace("__PROMPT__", prompt).replace("__SEED__", str(seed))
    return value


def _start_comfyui(cfg: dict) -> bool:
    launch_path = Path(str(cfg.get("comfyui_launch_path") or "").strip())
    if not launch_path.is_file():
        return False
    working_dir = str(cfg.get("comfyui_workdir") or launch_path.parent)
    if launch_path.suffix.lower() == ".bat":
        command = ["cmd", "/c", str(launch_path)]
    else:
        command = [str(launch_path)]
    launch_args = str(cfg.get("comfyui_launch_args") or "").strip()
    if launch_args:
        command.extend(launch_args.split())
    subprocess.Popen(
        command,
        cwd=working_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True


def ensure_comfyui_ready(cfg: dict, wait_seconds: int = 180) -> str:
    base_url = str(cfg.get("comfyui_url") or "http://127.0.0.1:8188").rstrip("/")
    try:
        _request_json(f"{base_url}/system_stats", timeout=3)
        return base_url
    except Exception:
        print(f"[ComfyUI] ComfyUI not detected at {base_url}. Attempting to launch...", flush=True)
        if not _start_comfyui(cfg):
            raise RuntimeError("ComfyUI is offline and no valid local launcher is configured.")
        print(f"[ComfyUI] Launched ComfyUI background process. Waiting for {base_url} to be ready...", flush=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            _request_json(f"{base_url}/system_stats", timeout=3)
            print(f"[ComfyUI] Connected successfully to {base_url}!", flush=True)
            return base_url
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"ComfyUI did not become ready at {base_url}.")


def generate_comfyui_image(prompt: str, output_path: Path, width: int, height: int, seed: int, cfg: dict) -> str:
    """Queue an API-format ComfyUI workflow and save its first output image."""
    base_url = ensure_comfyui_ready(cfg)
    workflow_setting = str(cfg.get("comfyui_workflow") or "workflows/txt2img_api.json")
    workflow_path = Path(workflow_setting)
    if not workflow_path.is_absolute():
        workflow_path = PROJECT_ROOT / workflow_path
    if not workflow_path.is_file():
        raise FileNotFoundError(f"ComfyUI workflow not found: {workflow_path}")

    workflow = json.loads(workflow_path.read_text(encoding="utf-8-sig"))
    # For FLUX on local 8GB desktop GPU, generating latents at 720x1280 (9:16) runs ~3x faster
    # with zero VRAM offload, and is cleanly upscaled to 1080x1920 in video compilation
    latent_w = 720 if width >= 1080 else (width or 720)
    latent_h = 1280 if height >= 1920 else (height or 1280)
    payload = _replace_workflow(workflow, prompt, seed, latent_w, latent_h)
    queued = _request_json(
        f"{base_url}/prompt",
        method="POST",
        payload={"prompt": payload, "client_id": f"local-queue-{uuid.uuid4().hex}"},
        timeout=30,
    )
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt ID: {queued}")

    deadline = time.monotonic() + int(cfg.get("comfyui_timeout_seconds", 420))
    while time.monotonic() < deadline:
        time.sleep(1)
        history = _request_json(f"{base_url}/history/{prompt_id}", timeout=15)
        item = history.get(prompt_id)
        if not item:
            continue
        for node in item.get("outputs", {}).values():
            for image in node.get("images", []):
                query = urlencode({
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                })
                with urlopen(f"{base_url}/view?{query}", timeout=60) as response:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.read())
                if output_path.stat().st_size < 1_000:
                    raise RuntimeError("ComfyUI returned an empty image.")
                return str(output_path)
        status = item.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI workflow failed: {status.get('messages', [])}")
    raise TimeoutError("ComfyUI image generation timed out.")
