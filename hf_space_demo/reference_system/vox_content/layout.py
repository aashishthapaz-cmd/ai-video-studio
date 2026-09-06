from __future__ import annotations


def frame_size(video_format: str) -> tuple[int, int]:
    if (video_format or "").lower() == "landscape":
        return (1920, 1080)
    return (1080, 1920)


def frame_center(video_format: str) -> tuple[int, int]:
    width, height = frame_size(video_format)
    return (width // 2, height // 2)

