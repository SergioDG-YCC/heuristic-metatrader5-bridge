"""
SMC Desk standalone runtime.

Starts CoreRuntimeService (market data) + SmcDeskService (scanner + analyst)
and runs them concurrently until interrupted.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from heuristic_mt5_bridge.core.config.env import repo_root_from
from heuristic_mt5_bridge.core.runtime.service import build_runtime_service
from heuristic_mt5_bridge.infra.mt5.connector import MT5ConnectorError
from heuristic_mt5_bridge.smc_desk.runtime import create_smc_desk_service


async def _run() -> int:
    repo_root = Path(repo_root_from(__file__))

    service = await build_runtime_service(repo_root)
    smc_desk = create_smc_desk_service(service.config.runtime_db_path)

    print("[smc-desk-runtime] bootstrapping core runtime...")
    try:
        await service.bootstrap()
    except MT5ConnectorError as exc:
        print(f"[smc-desk-runtime] MT5 connection failed: {exc}")
        return 1

    broker_server = str(service.broker_identity.get("broker_server", ""))
    account_login = int(service.broker_identity.get("account_login", 0) or 0)

    print(
        f"[smc-desk-runtime] connected — "
        f"broker={broker_server} account={account_login}"
    )

    async with asyncio.TaskGroup() as tg:
        tg.create_task(service.run_forever(), name="core_runtime")
        tg.create_task(
            smc_desk.run_forever(
                service.market_state,
                broker_server,
                account_login,
                service.spec_registry,
                symbols_ref=lambda: service.subscribed_symbols_for_desk("smc"),
            ),
            name="smc_desk",
        )

    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        print("[smc-desk-runtime] interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
