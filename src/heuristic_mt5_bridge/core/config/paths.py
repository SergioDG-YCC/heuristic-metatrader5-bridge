from __future__ import annotations

from pathlib import Path

from .env import getenv, load_env_file


def resolve_storage_root(repo_root: Path) -> Path:
    env_values = load_env_file(repo_root / ".env")
    configured = Path(getenv("STORAGE_ROOT", env_values, str(repo_root / "storage")))
    return configured if configured.is_absolute() else repo_root / configured


def resolve_runtime_db_path(storage_root: Path, configured_path: str | None = None) -> Path:
    if configured_path:
        candidate = Path(configured_path)
        return candidate if candidate.is_absolute() else storage_root.parent / candidate
    return storage_root / "runtime.db"

