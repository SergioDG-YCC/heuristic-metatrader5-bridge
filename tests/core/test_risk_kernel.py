from __future__ import annotations

from pathlib import Path

from heuristic_mt5_bridge.core.risk import RiskKernel
from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db


def _mk_kernel(db_path: Path) -> RiskKernel:
    ensure_runtime_db(db_path)
    return RiskKernel.from_env(
        db_path=db_path,
        broker_server="Broker-1",
        account_login=123456,
    )


def test_profile_resolution_and_env_overrides(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RISK_PROFILE_GLOBAL", "1")
    monkeypatch.setenv("RISK_PROFILE_FAST", "3")
    monkeypatch.setenv("RISK_PROFILE_SMC", "4")
    monkeypatch.setenv("RISK_MAX_DRAWDOWN_PCT", "4.25")
    monkeypatch.setenv("RISK_MAX_POSITIONS_TOTAL", "7")

    kernel = _mk_kernel(tmp_path / "runtime.db")

    profile = kernel.profile_state()
    assert profile["global"] == 1
    assert profile["fast"] == 3
    assert profile["smc"] == 4

    limits = kernel.effective_limits()["global"]
    assert float(limits["max_drawdown_pct"]) == 4.25
    assert float(limits["max_positions_total"]) == 7.0


def test_allocator_reduces_other_desk_when_fast_profile_increases(tmp_path: Path) -> None:
    kernel = _mk_kernel(tmp_path / "runtime.db")
    baseline = kernel.allocator_state()

    kernel.set_profiles(profile_fast=4, reason="unit_test")
    updated = kernel.allocator_state()

    assert float(updated["share_fast"]) > float(baseline["share_fast"])
    assert float(updated["share_smc"]) < float(baseline["share_smc"])


def test_kill_switch_blocks_entries_but_allows_defensive_actions(tmp_path: Path) -> None:
    kernel = _mk_kernel(tmp_path / "runtime.db")
    kernel.update_usage(
        account_payload={
            "account_state": {
                "drawdown_percent": 0.0,
                "open_position_count": 0,
                "pending_order_count": 0,
            },
            "exposure_state": {"gross_exposure": 0.0},
            "positions": [],
            "orders": [],
        },
        ownership_open=[],
    )
    kernel.trip_kill_switch(reason="manual emergency", manual_override=False)

    entry = kernel.evaluate_entry(desk="fast", symbol="EURUSD")
    assert entry["allowed"] is False
    assert "kill_switch_tripped" in entry["reasons"]

    assert kernel.evaluate_action(action_type="close_position")["allowed"] is True
    assert kernel.evaluate_action(action_type="remove_order")["allowed"] is True
    assert kernel.evaluate_action(action_type="open_position")["allowed"] is False

    reset = kernel.reset_kill_switch(reason="manual clear", manual_override=True)
    assert reset["state"] == "armed"
    assert reset["manual_override"] is True


def test_global_and_desk_limits_are_both_enforced(tmp_path: Path) -> None:
    kernel = _mk_kernel(tmp_path / "runtime.db")
    kernel.set_profiles(profile_global=3, profile_fast=1, profile_smc=4, reason="desk_budget_test")

    kernel.update_usage(
        account_payload={
            "account_state": {
                "drawdown_percent": 0.0,
                "open_position_count": 3,
                "pending_order_count": 0,
            },
            "exposure_state": {"gross_exposure": 1.2},
            "positions": [
                {"symbol": "EURUSD", "volume": 0.2},
                {"symbol": "GBPUSD", "volume": 0.2},
                {"symbol": "USDJPY", "volume": 0.2},
            ],
            "orders": [],
        },
        ownership_open=[
            {"desk_owner": "fast", "operation_type": "position"},
            {"desk_owner": "fast", "operation_type": "position"},
            {"desk_owner": "fast", "operation_type": "position"},
        ],
    )

    fast_entry = kernel.evaluate_entry(desk="fast", symbol="AUDUSD")
    assert fast_entry["allowed"] is False
    assert "fast_positions_budget_limit" in fast_entry["reasons"]

    kernel.set_profiles(overrides={"max_positions_total": 1}, reason="force_global_limit")
    kernel.update_usage(
        account_payload={
            "account_state": {
                "drawdown_percent": 0.0,
                "open_position_count": 1,
                "pending_order_count": 0,
            },
            "exposure_state": {"gross_exposure": 0.1},
            "positions": [{"symbol": "EURUSD", "volume": 0.1}],
            "orders": [],
        },
        ownership_open=[{"desk_owner": "fast", "operation_type": "position"}],
    )
    global_limited = kernel.evaluate_entry(desk="smc", symbol="GBPUSD")
    assert global_limited["allowed"] is False
    assert "global_positions_limit" in global_limited["reasons"]


def test_to_dict_returns_complete_structure(tmp_path: Path) -> None:
    kernel = _mk_kernel(tmp_path / "runtime.db")
    d = kernel.to_dict()

    assert "profile_global" in d
    assert "profile_fast" in d
    assert "profile_smc" in d
    assert "fast_budget_weight" in d
    assert "smc_budget_weight" in d
    assert "kill_switch_enabled" in d
    assert "overrides" in d
    assert "effective_limits" in d
    assert "allocator" in d

    # effective_limits has global + desks
    assert "global" in d["effective_limits"]
    assert "fast" in d["effective_limits"]["desks"]
    assert "smc" in d["effective_limits"]["desks"]

    # allocator has shares
    assert "share_fast" in d["allocator"]
    assert "share_smc" in d["allocator"]


def test_to_dict_reflects_profile_changes(tmp_path: Path) -> None:
    kernel = _mk_kernel(tmp_path / "runtime.db")
    kernel.set_profiles(profile_fast=4, reason="test")
    d = kernel.to_dict()
    assert d["profile_fast"] == 4
    assert float(d["allocator"]["share_fast"]) > 0.5
