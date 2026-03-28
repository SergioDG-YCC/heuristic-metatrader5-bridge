from __future__ import annotations

from heuristic_mt5_bridge.fast_desk.runtime import FastDeskConfig
from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig


def test_fast_runtime_prefers_fast_trader_env_over_legacy_alias(monkeypatch) -> None:
    monkeypatch.setenv("FAST_TRADER_SCAN_INTERVAL", "7")
    monkeypatch.setenv("FAST_DESK_SCAN_INTERVAL", "3")
    monkeypatch.setenv("FAST_TRADER_SIGNAL_COOLDOWN", "61")
    monkeypatch.setenv("FAST_DESK_SIGNAL_COOLDOWN", "33")
    monkeypatch.setenv("FAST_TRADER_RISK_PERCENT", "1.5")
    monkeypatch.setenv("FAST_DESK_RISK_PERCENT", "0.7")

    cfg = FastDeskConfig.from_env()

    assert cfg.scan_interval == 7.0
    assert cfg.signal_cooldown == 61.0
    assert cfg.risk_per_trade_percent == 1.5


def test_fast_runtime_uses_legacy_alias_when_primary_missing(monkeypatch) -> None:
    monkeypatch.delenv("FAST_TRADER_SCAN_INTERVAL", raising=False)
    monkeypatch.setenv("FAST_DESK_SCAN_INTERVAL", "4")
    monkeypatch.delenv("FAST_TRADER_SIGNAL_COOLDOWN", raising=False)
    monkeypatch.setenv("FAST_DESK_SIGNAL_COOLDOWN", "44")
    monkeypatch.delenv("FAST_TRADER_RISK_PERCENT", raising=False)
    monkeypatch.setenv("FAST_DESK_RISK_PERCENT", "0.9")

    cfg = FastDeskConfig.from_env()

    assert cfg.scan_interval == 4.0
    assert cfg.signal_cooldown == 44.0
    assert cfg.risk_per_trade_percent == 0.9


def test_fast_runtime_rr_defaults_and_aliases(monkeypatch) -> None:
    monkeypatch.delenv("FAST_TRADER_RR_RATIO", raising=False)
    monkeypatch.delenv("FAST_DESK_RR_RATIO", raising=False)
    assert FastDeskConfig.from_env().rr_ratio == 3.0

    monkeypatch.setenv("FAST_DESK_RR_RATIO", "3.4")
    assert FastDeskConfig.from_env().rr_ratio == 3.4

    monkeypatch.setenv("FAST_TRADER_RR_RATIO", "3.8")
    assert FastDeskConfig.from_env().rr_ratio == 3.8


def test_fast_setup_config_uses_single_rr_value() -> None:
    cfg = FastSetupConfig(rr_ratio=3.7, min_rr=2.0)
    assert cfg.rr_ratio == 3.7
    assert cfg.min_rr == 2.0


def test_fast_setup_config_caps_internal_floor_to_rr_ratio() -> None:
    cfg = FastSetupConfig(rr_ratio=1.8)
    assert cfg.rr_ratio == 1.8
    assert cfg.min_rr == 1.8
