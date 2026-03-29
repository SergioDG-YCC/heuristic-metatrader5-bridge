from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.fast_desk.context import FastContext, FastContextConfig
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyDecision, FastCustodyPolicyConfig
from heuristic_mt5_bridge.fast_desk.execution.bridge import FastExecutionBridge
from heuristic_mt5_bridge.fast_desk.pending import FastPendingPolicyConfig
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.setup import FastSetup, FastSetupConfig
from heuristic_mt5_bridge.fast_desk.state.desk_state import SymbolDeskState
from heuristic_mt5_bridge.fast_desk.trader import FastTraderConfig, FastTraderService
from heuristic_mt5_bridge.fast_desk.trigger import FastTriggerConfig, FastTriggerDecision


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candles(count: int, *, minutes: int, start: float = 1.1000) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rows: list[dict[str, Any]] = []
    price = start
    for idx in range(count):
        ts = now - timedelta(minutes=(count - idx) * minutes)
        rows.append(
            {
                "timestamp": _iso(ts),
                "open": price,
                "high": price + 0.0006,
                "low": price - 0.0004,
                "close": price + 0.0002,
            }
        )
        price += 0.00005
    return rows


def _context() -> FastContext:
    return FastContext(
        symbol="EURUSD",
        session_name="london",
        h1_bias="buy",
        volatility_regime="normal",
        spread_pips=0.6,
        expected_slippage_points=2.0,
        stale_feed=False,
        no_trade_regime=False,
        allowed=True,
        reasons=[],
        details={},
    )


class _MarketState:
    def __init__(self) -> None:
        self._m1 = _candles(260, minutes=1)
        self._m5 = _candles(260, minutes=5)
        self._m30 = _candles(260, minutes=30)

    def get_candles(self, symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
        _ = symbol
        _ = bars
        tf = str(timeframe).upper()
        if tf == "M1":
            return list(self._m1)
        if tf == "M5":
            return list(self._m5)
        return list(self._m30)


class _SpecRegistry:
    def pip_size(self, symbol: str) -> float:
        _ = symbol
        return 0.0001

    def get(self, symbol: str) -> dict[str, Any]:
        _ = symbol
        return {"point": 0.0001, "tick_value": 10.0}


class _Connector:
    def __init__(self) -> None:
        self.instructions: list[dict[str, Any]] = []

    def symbol_tick(self, symbol: str) -> dict[str, float]:
        _ = symbol
        return {"bid": 1.1000, "ask": 1.1001}

    def send_execution_instruction(self, instruction: dict[str, Any]) -> dict[str, Any]:
        self.instructions.append(dict(instruction))
        entry_type = str(instruction.get("entry_type", "")).lower()
        if entry_type == "market":
            return {"ok": True, "position": 1001}
        return {"ok": True, "order": 2001}


class _CustodyConnector:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def modify_position_levels(
        self,
        *,
        symbol: str,
        position_id: int,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "position_id": position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
        self.calls.append(payload)
        return {"ok": True, "request": payload}


def _service() -> FastTraderService:
    return FastTraderService(
        trader_config=FastTraderConfig(
            signal_cooldown=0.0,
            enable_pending_orders=True,
            require_h1_alignment=False,
        ),
        context_config=FastContextConfig(),
        setup_config=FastSetupConfig(min_confidence=0.5),
        trigger_config=FastTriggerConfig(),
        pending_config=FastPendingPolicyConfig(),
        custody_config=FastCustodyPolicyConfig(),
    )


def _setup(*, setup_type: str, requires_pending: bool, pending_entry_type: str) -> FastSetup:
    return FastSetup(
        setup_id=f"EURUSD_{setup_type}",
        setup_type=setup_type,
        symbol="EURUSD",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1020,
        risk_pips=10.0,
        confidence=0.86,
        requires_pending=requires_pending,
        pending_entry_type=pending_entry_type,
        retest_level=1.1000,
        metadata={},
    )


def test_scan_blocks_entry_when_no_m1_trigger(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    connector = _Connector()

    monkeypatch.setattr(service.context_service, "build_context", lambda **kwargs: _context())
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="breakout_retest", requires_pending=True, pending_entry_type="limit")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(False, "none", 0.0, "m1_trigger_missing"),
    )
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    result = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=connector,
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_config=FastRiskConfig(),
    )

    assert result is None
    assert connector.instructions == []


def test_scan_selects_pending_entry_for_retest_setup(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    connector = _Connector()

    monkeypatch.setattr(service.context_service, "build_context", lambda **kwargs: _context())
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="order_block_retest", requires_pending=True, pending_entry_type="limit")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(True, "reclaim", 0.8, "ok"),
    )
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    out = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=connector,
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_config=FastRiskConfig(),
    )

    assert out is not None
    assert out["entry_type"] == "limit"
    assert connector.instructions
    assert connector.instructions[0]["entry_type"] == "limit"
    assert connector.instructions[0]["entry_price"] == 1.1000


def test_scan_selects_market_entry_for_reclaim_setup(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    connector = _Connector()

    monkeypatch.setattr(service.context_service, "build_context", lambda **kwargs: _context())
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="liquidity_sweep_reclaim", requires_pending=False, pending_entry_type="market")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(True, "displacement", 0.9, "ok"),
    )
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    out = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=connector,
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_config=FastRiskConfig(),
    )

    assert out is not None
    assert out["entry_type"] == "market"
    assert connector.instructions
    assert connector.instructions[0]["entry_type"] == "market"
    assert "entry_price" not in connector.instructions[0]


def test_custody_ignores_non_fast_positions(monkeypatch, tmp_path: Path) -> None:
    service = _service()

    managed_ids: list[int] = []

    def _eval_position(**kwargs: Any) -> FastCustodyDecision:
        pos_id = int(kwargs["position"]["position_id"])
        managed_ids.append(pos_id)
        return FastCustodyDecision(action="close", position_id=pos_id, reason="test_close")

    monkeypatch.setattr(service.context_service, "build_context", lambda **kwargs: _context())
    monkeypatch.setattr(service.custody_engine, "evaluate_position", _eval_position)
    monkeypatch.setattr(service.execution, "apply_professional_custody", lambda *a, **k: {"ok": True})
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    positions = [
        {"position_id": 11, "symbol": "EURUSD", "side": "buy", "price_open": 1.1000, "price_current": 1.1010, "stop_loss": 1.0990, "volume": 0.10},
        {"position_id": 12, "symbol": "EURUSD", "side": "buy", "price_open": 1.1000, "price_current": 1.1010, "stop_loss": 1.0990, "volume": 0.10},
        {"position_id": 22, "symbol": "EURUSD", "side": "buy", "price_open": 1.1000, "price_current": 1.1010, "stop_loss": 1.0990, "volume": 0.10},
    ]
    ownership_rows = [
        {"desk_owner": "fast", "ownership_status": "fast_owned", "position_id": 11},
        {"desk_owner": "smc", "ownership_status": "inherited_fast", "position_id": 12},
        {"desk_owner": "smc", "ownership_status": "smc_owned", "position_id": 22},
    ]

    result = service.run_custody(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"positions": positions, "orders": []},
        connector=_Connector(),
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_action_ref=lambda action_type: {"allowed": True, "action_type": action_type},
        ownership_open_ref=lambda: ownership_rows,
    )

    assert sorted(managed_ids) == [11, 12]
    assert result["positions"] == 2


def test_rejected_entry_does_not_consume_cooldown_or_open_counter(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    state = SymbolDeskState()

    monkeypatch.setattr(service.context_service, "build_context", lambda **kwargs: _context())
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="liquidity_sweep_reclaim", requires_pending=False, pending_entry_type="market")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(True, "displacement", 0.9, "ok"),
    )
    monkeypatch.setattr(service.execution, "send_entry", lambda *a, **k: {"ok": False, "error": "broker_reject"})
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    out = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=_Connector(),
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=state,
        risk_config=FastRiskConfig(),
    )

    assert out is not None
    assert out["result"]["ok"] is False
    assert state.last_signal_at == 0.0
    assert state.positions_opened_today == 0


def test_ranging_context_filters_breakout_setup_even_with_trigger(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    connector = _Connector()

    monkeypatch.setattr(
        service.context_service,
        "build_context",
        lambda **kwargs: FastContext(
            symbol="EURUSD",
            session_name="london",
            h1_bias="sell",
            volatility_regime="high",
            spread_pips=0.6,
            expected_slippage_points=2.0,
            stale_feed=False,
            no_trade_regime=False,
            allowed=True,
            market_phase="ranging",
            exhaustion_risk="low",
            reasons=[],
            warnings=["m5_ranging"],
            details={},
        ),
    )
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="breakout_retest", requires_pending=True, pending_entry_type="stop")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(True, "micro_bos", 0.95, "ok"),
    )
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    out = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=connector,
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_config=FastRiskConfig(),
    )

    assert out is None
    assert connector.instructions == []


def test_pullback_context_allows_strong_reclaim_setup(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    connector = _Connector()

    monkeypatch.setattr(
        service.context_service,
        "build_context",
        lambda **kwargs: FastContext(
            symbol="EURUSD",
            session_name="london",
            h1_bias="sell",
            volatility_regime="high",
            spread_pips=0.6,
            expected_slippage_points=2.0,
            stale_feed=False,
            no_trade_regime=False,
            allowed=True,
            market_phase="pullback_bear",
            exhaustion_risk="low",
            reasons=[],
            warnings=["pullback_bear"],
            details={},
        ),
    )
    monkeypatch.setattr(
        service.setup_engine,
        "detect_setups",
        lambda **kwargs: [_setup(setup_type="order_block_retest", requires_pending=True, pending_entry_type="limit")],
    )
    monkeypatch.setattr(
        service.trigger_engine,
        "confirm",
        lambda **kwargs: FastTriggerDecision(True, "reclaim", 0.80, "ok"),
    )
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.upsert_fast_signal", lambda *a, **k: None)
    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.trader.service.runtime_db.append_fast_trade_log", lambda *a, **k: None)

    out = service.scan_and_execute(
        symbol="EURUSD",
        market_state=_MarketState(),
        spec_registry=_SpecRegistry(),
        account_payload_ref=lambda: {"account_state": {"balance": 10000.0, "equity": 10000.0}, "positions": []},
        connector=connector,
        db_path=tmp_path / "runtime.db",
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        risk_config=FastRiskConfig(),
    )

    assert out is not None
    assert out["entry_type"] == "limit"


def test_professional_custody_preserves_existing_tp_when_moving_sl() -> None:
    bridge = FastExecutionBridge()
    connector = _CustodyConnector()

    result = bridge.apply_professional_custody(
        connector,
        decision=FastCustodyDecision(
            action="move_to_be",
            position_id=101,
            reason="breakeven_trigger",
            new_sl=1.1001,
            new_tp=None,
        ),
        position={
            "symbol": "EURUSD",
            "position_id": 101,
            "side": "buy",
            "volume": 0.10,
            "take_profit": 1.1045,
        },
    )

    assert result["ok"] is True
    assert connector.calls
    assert connector.calls[0]["stop_loss"] == 1.1001
    assert connector.calls[0]["take_profit"] == 1.1045
