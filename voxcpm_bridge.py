#!/usr/bin/env python3
"""Local VOXCPM bridge used by Stickman Studio.

The bridge accepts one JSON request path and writes one WAV output. It never
fetches model weights automatically; set VOXCPM_MODEL_PATH to a local model
folder after reinstalling weights.
"""
from __future__ import annotations
import json, os, sys, wave
from pathlib import Path

def fail(message: str, code: int = 2):
    print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
    raise SystemExit(code)

def duration_seconds(path: str) -> float:
    try:
        with wave.open(path, "rb") as f:
            return f.getnframes() / float(f.getframerate() or 1)
    except Exception:
        try:
            import soundfile as sf
            info = sf.info(path)
            return float(info.frames) / float(info.samplerate or 1)
        except Exception:
            return 0.0

def main():
    if len(sys.argv) != 2:
        fail("usage: voxcpm_bridge.py request.json")
    request_path = Path(sys.argv[1])
    if not request_path.exists():
        fail(f"Request file not found: {request_path}")
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    text = str(request.get("text", "")).strip()
    output = Path(str(request.get("output", "output.wav"))).resolve()
    if not text:
        fail("No text supplied")
    reference = str(request.get('reference_audio', '')).strip()
    reference_exists = bool(reference and Path(reference).exists())
    default_paths = [
        Path(r'D:\\VoxCPM Content Factory\\models\\VoxCPM2') if reference_exists else Path(r'D:\\VoxCPM Content Factory\\models\\VoxCPM1.5'),
        Path(__file__).resolve().parent / 'models' / ('VoxCPM2' if reference_exists else 'VoxCPM1.5'),
        Path(__file__).resolve().parent / 'models' / 'VoxCPM1.5',
        Path(r'D:\\VoxCPM Content Factory\\models\\VoxCPM1.5'),
    ]
    model_path = Path(os.environ.get('VOXCPM_MODEL_PATH', '') or next((str(p) for p in default_paths if p.exists()), str(default_paths[0])))
    if not Path(model_path).exists():
        fail("VOXCPM application restored, but model weights are not installed. Set VOXCPM_MODEL_PATH to a local VoxCPM model directory.")
    try:
        from voxcpm import VoxCPM
        import soundfile as sf
    except Exception as exc:
        fail(f"VOXCPM Python package is unavailable: {exc}")
    WHISPER_REFERENCE_TRANSCRIPT = (
        "I don't know what you did to me, but I swear my heart reacts to you like a habit. "
        "Your voice feels like music. Your smile hits me harder than any high. "
        "I don't crave attention. I crave you. The way you talk, the way you look at me, "
        "the way you exist, it's dangerous because now my favorite addiction is simply being yours."
    )
    try:
        model = VoxCPM.from_pretrained(model_path, load_denoiser=False, optimize=False)
        style = str(request.get('style_instruction', '')).strip()
        if reference_exists and 'VoxCPM2' in str(model_path):
            prompt_text = str(request.get('prompt_text', '')).strip()
            if not prompt_text and 'whishper' in reference.lower():
                prompt_text = WHISPER_REFERENCE_TRANSCRIPT
            # In Ultimate Continuation Cloning, do NOT pass reference_wav_path when prompt_text is present
            # (passing both triggers combined mode which doubles VRAM usage and crashes CUDA).
            kwargs = {
                'text': text,
                'cfg_value': float(request.get('cfg_value', 1.9)),
                'inference_timesteps': int(request.get('inference_timesteps', 10)),
                'normalize': True,
                'denoise': False,
                'retry_badcase': False,
            }
            if prompt_text:
                kwargs['prompt_wav_path'] = reference
                kwargs['prompt_text'] = prompt_text
            else:
                kwargs['reference_wav_path'] = reference
        if request.get("batch") and isinstance(request.get("batch"), list):
            batch_results = []
            for item in request["batch"]:
                item_text = str(item.get("text", "")).strip()
                item_output = Path(str(item.get("output", "output.wav"))).resolve()
                if not item_text:
                    continue
                item_kwargs = dict(kwargs)
                item_kwargs['text'] = item_text
                wav = model.generate(**item_kwargs)
                item_output.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(item_output), wav, model.tts_model.sample_rate)
                dur = duration_seconds(str(item_output))
                batch_results.append({"output": str(item_output), "duration": round(dur, 3), "text": item_text})
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            print(json.dumps({"ok": True, "batch": batch_results, "engine": "VOXCPM English"}))
            return

        wav = model.generate(**kwargs)
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), wav, model.tts_model.sample_rate)
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    except Exception as exc:
        fail(f"VOXCPM synthesis failed: {exc}")
    print(json.dumps({"ok": True, "output": str(output), "duration": round(duration_seconds(str(output)), 3), "engine": "VOXCPM English"}))

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
