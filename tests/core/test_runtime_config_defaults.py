from __future__ import annotations

from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeConfig


def test_runtime_config_defaults_include_m1_watch_timeframe(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MT5_WATCH_TIMEFRAMES", raising=False)
    config = CoreRuntimeConfig.load(tmp_path)
    assert config.watch_timeframes == ["M1", "M5", "H1"]
