"""Standalone entry: boots CoreRuntimeService + FastDeskService."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from heuristic_mt5_bridge.core.config.env import load_env_file, repo_root_from
from heuristic_mt5_bridge.core.runtime.service import build_runtime_service


async def _run() -> None:
    repo_root = Path(repo_root_from(__file__))
    os.environ.setdefault("FAST_DESK_ENABLED", "true")
    service = await build_runtime_service(repo_root)
    await service.bootstrap()
    await service.run_forever()


def main() -> int:
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

