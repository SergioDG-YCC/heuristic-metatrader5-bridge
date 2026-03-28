from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from heuristic_mt5_bridge.core.config.env import repo_root_from
from heuristic_mt5_bridge.core.runtime.service import build_runtime_service
from heuristic_mt5_bridge.infra.mt5.connector import MT5ConnectorError
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the core runtime bridge process.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument(
        "--dry-run-config",
        action="store_true",
        help="Load config and write runtime info without connecting to MT5.",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    repo_root = Path(repo_root_from(__file__))
    service = await build_runtime_service(repo_root)
    if args.dry_run_config:
        payload = {
            "status": "dry_run",
            "storage_root": str(service.config.storage_root),
            "runtime_db_path": str(service.config.runtime_db_path),
            "bootstrap_symbols": service.config.watch_symbols,
            "watch_timeframes": service.config.watch_timeframes,
            "sessions_enabled": service.config.sessions_enabled,
            "indicator_enabled": service.config.indicator_enabled,
            "market_state_checkpoint_seconds": service.config.market_state_checkpoint_seconds,
            "updated_at": utc_now_iso(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    try:
        if args.once:
            await service.run_once()
            return 0
        await service.run_forever()
        return 0
    except MT5ConnectorError:
        return 1
    finally:
        if args.once:
            await service.shutdown()


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
