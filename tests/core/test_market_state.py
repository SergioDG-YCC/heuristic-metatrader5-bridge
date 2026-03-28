from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService


def build_snapshot(symbol: str, timeframe: str, candle_count: int = 30) -> dict[str, object]:
    start = datetime(2026, 3, 23, 8, 0, tzinfo=timezone.utc)
    candles: list[dict[str, object]] = []
    price = 1.1000
    for index in range(candle_count):
        current = start + timedelta(minutes=5 * index)
        candles.append(
            {
                "timestamp": current.isoformat().replace("+00:00", "Z"),
                "open": round(price, 5),
                "high": round(price + 0.0008, 5),
                "low": round(price - 0.0004, 5),
                "close": round(price + 0.0003, 5),
            }
        )
        price += 0.0002
    return {
        "snapshot_id": "snap_1",
        "symbol": symbol,
        "timeframe": timeframe,
        "created_at": (start + timedelta(minutes=5 * candle_count)).isoformat().replace("+00:00", "Z"),
        "bid": round(price, 5),
        "ask": round(price + 0.0002, 5),
        "ohlc": candles,
        "structure": {
            "market_regime": "trend_up",
            "range_high": round(price + 0.0008, 5),
            "range_low": round(price - 0.005, 5),
            "last_breakout_direction": "up",
            "breakout_strength": 0.4,
            "retest_state": "pending",
            "pattern_hypothesis": "trend_continuation",
        },
    }


class MarketStateServiceTest(unittest.TestCase):
    def test_ingest_snapshot_builds_chart_context_and_summary(self) -> None:
        service = MarketStateService(max_bars=50)
        snapshot = build_snapshot("EURUSD", "M5")
        context = service.ingest_snapshot(snapshot)
        summary = service.query("EURUSD", "M5", "state_summary")

        self.assertEqual(context["symbol"], "EURUSD")
        self.assertEqual(context["timeframe"], "M5")
        self.assertEqual(context["window_bars"], 30)
        self.assertEqual(summary["query_type"], "state_summary")
        self.assertEqual(summary["indicator_enrichment_status"], "missing")
        self.assertEqual(service.bootstrap_status()[0]["ready_for_scheduler"], True)

    def test_indicator_snapshot_updates_state_summary(self) -> None:
        service = MarketStateService(max_bars=50)
        service.ingest_snapshot(build_snapshot("GBPUSD", "H1"))
        summary = service.ingest_indicator_snapshot(
            {
                "symbol": "GBPUSD",
                "timeframe": "H1",
                "request_id": "req_1",
                "computed_at": "2026-03-23T10:35:00Z",
                "source": "indicator_ea",
                "indicator_values": {"ema_20": 1.25, "rsi_14": 55.0},
            }
        )

        self.assertEqual(summary["indicator_enrichment_status"], "ready")
        self.assertEqual(summary["indicator_summary"]["ema_20"], 1.25)
        self.assertEqual(service.get_candles("GBPUSD", "H1", bars=5)[0]["timestamp"], "2026-03-23T10:05:00Z")


if __name__ == "__main__":
    unittest.main()
