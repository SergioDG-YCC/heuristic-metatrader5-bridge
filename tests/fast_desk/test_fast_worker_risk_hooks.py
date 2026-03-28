from __future__ import annotations

import asyncio
from pathlib import Path

from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.state.desk_state import SymbolDeskState
from heuristic_mt5_bridge.fast_desk.workers.symbol_worker import FastSymbolWorker, FastWorkerConfig
from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db


class _StubMarketState:
    pass


class _StubSpecRegistry:
    pass


def test_fast_worker_scan_delegates_risk_gate_and_ownership_hooks(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    ensure_runtime_db(db_path)

    worker = FastSymbolWorker()

    captured: dict = {}

    class _StubTrader:
        def scan_and_execute(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True}

    worker._trader = _StubTrader()  # type: ignore[assignment]

    risk_gate_calls: list[str] = []

    def _risk_gate(symbol: str) -> dict:
        risk_gate_calls.append(symbol)
        return {"allowed": True}

    ownership_calls: list[tuple] = []

    def _ownership_register(result: dict, symbol: str, side: str, signal_id: str | None) -> list[dict]:
        ownership_calls.append((result, symbol, side, signal_id))
        return []

    asyncio.run(
        worker._run_scan(
            symbol="EURUSD",
            market_state=_StubMarketState(),
            account_payload_ref=lambda: {},
            connector=object(),
            spec_registry=_StubSpecRegistry(),
            db_path=db_path,
            broker_server="Broker-1",
            account_login=123456,
            config=FastWorkerConfig(scan_interval=0.01, custody_interval=0.01, signal_cooldown=0.0),
            risk_config=FastRiskConfig(),
            state=SymbolDeskState(),
            risk_gate_ref=_risk_gate,
            ownership_register_ref=_ownership_register,
        )
    )

    assert captured["symbol"] == "EURUSD"
    assert callable(captured["risk_gate_ref"])
    assert callable(captured["ownership_register_ref"])
    assert captured["risk_gate_ref"]("EURUSD")["allowed"] is True
    assert risk_gate_calls == ["EURUSD"]


def test_fast_worker_custody_delegates_risk_action_and_ownership_open(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    ensure_runtime_db(db_path)

    worker = FastSymbolWorker()
    captured: dict = {}

    class _StubTrader:
        def run_custody(self, **kwargs):
            captured.update(kwargs)
            return {"positions": 0, "orders": 0}

    worker._trader = _StubTrader()  # type: ignore[assignment]

    def _risk_action(action_type: str) -> dict:
        return {"allowed": True, "action": action_type}

    def _ownership_open() -> list[dict]:
        return []

    asyncio.run(
        worker._run_custody(
            symbol="EURUSD",
            market_state=_StubMarketState(),
            account_payload_ref=lambda: {},
            connector=object(),
            spec_registry=_StubSpecRegistry(),
            db_path=db_path,
            broker_server="Broker-1",
            account_login=123456,
            state=SymbolDeskState(),
            risk_action_ref=_risk_action,
            ownership_open_ref=_ownership_open,
        )
    )

    assert captured["symbol"] == "EURUSD"
    assert callable(captured["risk_action_ref"])
    assert callable(captured["ownership_open_ref"])
    assert captured["risk_action_ref"]("close")["allowed"] is True
    assert captured["ownership_open_ref"]() == []
