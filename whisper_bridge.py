from __future__ import annotations

import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    audio = Path(sys.argv[1])
    output = Path(sys.argv[2])
    model_name = sys.argv[3] if len(sys.argv) > 3 else "small"
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    segments, _ = model.transcribe(str(audio), word_timestamps=True, vad_filter=False, beam_size=3)
    rows = []
    for seg in segments:
        rows.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
                "words": [
                    {"start": w.start, "end": w.end, "word": w.word}
                    for w in (seg.words or [])
                    if str(w.word).strip()
                ],
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "segments": len(rows), "words": sum(len(x["words"]) for x in rows)}))


if __name__ == "__main__":
    main()
