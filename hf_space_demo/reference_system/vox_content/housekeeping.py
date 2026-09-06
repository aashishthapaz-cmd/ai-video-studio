from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import shutil

from .config import ASSETS_DIR, LOGS_DIR, OUTPUTS_DIR, PROJECTS_DIR, QUEUE_DIR, ROOT, settings


PROTECTED_DIRS = {
    ".venv",
    "analysis",
    "assets",
    "logs",
    "outputs",
    "projects",
    "queue",
    "scripts",
    "vox_content",
}


@dataclass
class CleanupReport:
    removed_dirs: int = 0
    removed_files: int = 0
    freed_bytes: int = 0

    @property
    def summary(self) -> str:
        size_mb = self.freed_bytes / (1024 * 1024)
        return f"Startup cleanup removed {self.removed_dirs} folders and {self.removed_files} files, freeing {size_mb:.1f} MB."


def ensure_project_layout() -> None:
    folders = [
        ASSETS_DIR / "poems" / "overlays",
        ASSETS_DIR / "poems" / "music",
        ASSETS_DIR / "motivation" / "overlays",
        ASSETS_DIR / "motivation" / "music",
        ASSETS_DIR / "image_drop" / "poems",
        ASSETS_DIR / "image_drop" / "motivation",
        ASSETS_DIR / "reference_voice",
        LOGS_DIR,
        OUTPUTS_DIR / "poems",
        OUTPUTS_DIR / "motivation",
        PROJECTS_DIR,
        QUEUE_DIR,
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def startup_cleanup() -> CleanupReport:
    ensure_project_layout()
    report = CleanupReport()
    if not settings.cleanup_on_startup:
        return report
    _remove_root_temp_dirs(report)
    _remove_stale_project_dirs(report)
    _remove_python_caches(report)
    _remove_old_logs(report)
    return report


def _remove_root_temp_dirs(report: CleanupReport) -> None:
    for path in ROOT.iterdir():
        if path.is_dir() and path.name.startswith("tmp_") and path.name not in PROTECTED_DIRS:
            _remove_dir(path, report)


def _remove_stale_project_dirs(report: CleanupReport) -> None:
    cutoff = datetime.now() - timedelta(hours=max(1, settings.cleanup_project_hours))
    if not PROJECTS_DIR.exists():
        return
    for path in PROJECTS_DIR.iterdir():
        if path.is_dir() and _mtime(path) < cutoff:
            _remove_dir(path, report)


def _remove_python_caches(report: CleanupReport) -> None:
    for path in ROOT.rglob("__pycache__"):
        if path.is_dir():
            _remove_dir(path, report)
    for path in ROOT.rglob("*.pyc"):
        if path.is_file():
            _remove_file(path, report)


def _remove_old_logs(report: CleanupReport) -> None:
    cutoff = datetime.now() - timedelta(days=max(1, settings.cleanup_log_days))
    if not LOGS_DIR.exists():
        return
    for path in LOGS_DIR.glob("*.log"):
        if path.is_file() and _mtime(path) < cutoff:
            _remove_file(path, report)


def _remove_dir(path: Path, report: CleanupReport) -> None:
    if not _is_safe_to_remove(path):
        return
    size = _size(path)
    shutil.rmtree(path, ignore_errors=True)
    if not path.exists():
        report.removed_dirs += 1
        report.freed_bytes += size


def _remove_file(path: Path, report: CleanupReport) -> None:
    if not _is_safe_to_remove(path):
        return
    size = path.stat().st_size if path.exists() else 0
    path.unlink(missing_ok=True)
    if not path.exists():
        report.removed_files += 1
        report.freed_bytes += size


def _is_safe_to_remove(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = ROOT.resolve()
    except OSError:
        return False
    if not resolved.is_relative_to(root):
        return False
    relative = resolved.relative_to(root)
    if not relative.parts:
        return False
    top = relative.parts[0]
    if top in {"assets", "outputs", "queue", "scripts", "vox_content", ".venv"}:
        return top == "vox_content" and path.name == "__pycache__"
    if top == "logs":
        return path.suffix == ".log"
    if top == "projects":
        return len(relative.parts) >= 2
    return top.startswith("tmp_") or path.name == "__pycache__" or path.suffix == ".pyc"


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)
