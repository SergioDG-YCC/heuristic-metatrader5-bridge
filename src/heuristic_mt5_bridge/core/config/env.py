from __future__ import annotations

import os
from pathlib import Path


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def getenv(key: str, env_values: dict[str, str], default: str) -> str:
    return os.getenv(key, env_values.get(key, default))


def repo_root_from(current_file: str | Path) -> Path:
    path = Path(current_file).resolve()
    for candidate in [path.parent, *path.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return path.parent

