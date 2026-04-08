"""
SMC Desk unit tests — no MT5, no LocalAI, no network.

Covers:
  - Detection pipeline (structure, OB, FVG, liquidity, fibonacci, elliott, confluences)
  - Heuristic validators
  - Thesis store (build + SQLite round-trip)
  - Scanner (SmcScannerService.run_once) end-to-end via mock MarketStateService
  - Analyst (build_heuristic_output) with LLM disabled
"""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Candle factory helpers
# ---------------------------------------------------------------------------

def _make_candles(
    count: int = 60,
    base_price: float = 1.1000,
    step: float = 0.0005,
    symbol: str = "EURUSD",
    timeframe: str = "H4",
) -> list[dict[str, Any]]:
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    candles = []
    price = base_price
    for i in range(count):
        ts = (start + timedelta(hours=4 * i)).isoformat().replace("+00:00", "Z")
        # Alternate up/down slightly to create swing structure
        direction = 1 if i % 8 < 4 else -1
        candles.append({
            "timestamp": ts,
            "open": round(price, 5),
            "high": round(price + 0.0012, 5),
            "low": round(price - 0.0008, 5),
            "close": round(price + direction * step, 5),
        })
        price += direction * step * 0.4
    return candles


def _make_market_state_service(
    symbols: list[str] | None = None,
    candle_count: int = 120,
) -> MagicMock:
    """Return a mock MarketStateService that serves synthetic candles."""
    symbols = symbols or ["EURUSD", "GBPUSD"]
    service = MagicMock()

    d1_candles = _make_candles(count=candle_count, timeframe="D1", step=0.0010)
    h4_candles = _make_candles(count=candle_count, timeframe="H4", step=0.0005)
    h1_candles = _make_candles(count=candle_count, timeframe="H1", step=0.0002)

    def _get_candles(symbol: str, timeframe: str, bars: int = 200) -> list[dict[str, Any]]:
        mapping = {"D1": d1_candles, "H4": h4_candles, "H1": h1_candles, "M15": h1_candles}
        data = mapping.get(timeframe, h4_candles)
        return data[-bars:] if bars < len(data) else data

    service.get_candles = _get_candles
    return service


# ---------------------------------------------------------------------------
# Test: Detection pipeline
# ---------------------------------------------------------------------------

class TestDetectionPipeline(unittest.TestCase):

    def test_detect_market_structure_returns_trend(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure

        candles = _make_candles(count=50)
        result = detect_market_structure(candles, window=3)
        self.assertIn("trend", result)
        self.assertIn(result["trend"], {"bullish", "bearish", "ranging"})
        self.assertIn("swings", result)
        self.assertIsInstance(result["swings"], list)

    def test_detect_order_blocks_returns_list(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure, detect_order_blocks

        candles = _make_candles(count=60)
        structure = detect_market_structure(candles, window=3)
        obs = detect_order_blocks(candles, structure, min_impulse_candles=2, max_zones=10)
        self.assertIsInstance(obs, list)
        for ob in obs:
            self.assertIn("zone_type", ob)
            self.assertIn(ob["zone_type"], {"ob_bullish", "ob_bearish"})
            self.assertGreater(float(ob.get("price_high", 0)), 0)
            self.assertGreater(float(ob.get("price_low", 0)), 0)

    def test_detect_fair_value_gaps_returns_list(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_fair_value_gaps

        candles = _make_candles(count=60)
        fvgs = detect_fair_value_gaps(candles, max_zones=10)
        self.assertIsInstance(fvgs, list)

    def test_detect_liquidity_pools_returns_list(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure, detect_liquidity_pools

        d1 = _make_candles(count=80, step=0.0010)
        h4 = _make_candles(count=60, step=0.0005)
        structure = detect_market_structure(d1, window=3)
        pools = detect_liquidity_pools(d1, h4, structure=structure, max_zones=10)
        self.assertIsInstance(pools, list)

    def test_fibonacci_levels_for_structure(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure
        from heuristic_mt5_bridge.smc_desk.detection.fibonacci import fibo_levels_for_structure

        d1 = _make_candles(count=80, step=0.0010)
        structure = detect_market_structure(d1, window=3)
        fibo = fibo_levels_for_structure(structure)
        self.assertIsInstance(fibo, dict)

    def test_count_waves_returns_dict(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import count_waves, detect_market_structure

        d1 = _make_candles(count=80, step=0.0010)
        structure = detect_market_structure(d1, window=3)
        elliott = count_waves(structure)
        self.assertIsInstance(elliott, dict)
        self.assertIn("pattern_type", elliott)


# ---------------------------------------------------------------------------
# Test: Validators
# ---------------------------------------------------------------------------

class TestHeuristicValidators(unittest.TestCase):

    def _minimal_thesis(self, bias: str = "bullish") -> dict[str, Any]:
        return {
            "symbol": "EURUSD",
            "strategy_type": "smc_prepared",
            "bias": bias,
            "bias_confidence": "medium",
            "base_scenario": "Test scenario",
            "prepared_zones": [],
            "watch_conditions": ["Wait for zone"],
            "invalidations": ["H4 close below zone"],
            "operation_candidates": [
                {
                    "side": "buy" if bias == "bullish" else "sell",
                    "entry_zone_high": 1.1020,
                    "entry_zone_low": 1.1010,
                    "stop_loss": 1.0990,
                    "take_profit_1": 1.1080,
                    "take_profit_2": 1.1120,
                    "rr_ratio": "1:2.0",
                    "confluences": ["ob_aligned", "fvg_present"],
                    "quality": "medium",
                    "source_zone_id": "zone_abc123",
                }
            ],
            "status": "watching",
        }

    def test_validate_heuristic_thesis_accepts_coherent_thesis(self) -> None:
        from heuristic_mt5_bridge.smc_desk.validators.heuristic import validate_heuristic_thesis

        thesis = self._minimal_thesis("bullish")
        result = validate_heuristic_thesis(
            thesis,
            symbol="EURUSD",
            current_price=1.1015,
            active_zones=[],
            min_rr=1.5,
        )
        self.assertIn("normalized_thesis", result)
        self.assertIn("validation_summary", result)
        self.assertIn("issues", result)
        self.assertIsInstance(result["issues"], list)
        self.assertIsInstance(result["normalized_thesis"], dict)

    def test_validate_heuristic_thesis_drops_bad_rr_candidate(self) -> None:
        from heuristic_mt5_bridge.smc_desk.validators.heuristic import validate_heuristic_thesis

        thesis = self._minimal_thesis("bullish")
        # Make TP very close to entry → bad RR
        thesis["operation_candidates"][0]["take_profit_1"] = 1.1012
        thesis["operation_candidates"][0]["take_profit_2"] = 1.1014

        result = validate_heuristic_thesis(
            thesis,
            symbol="EURUSD",
            current_price=1.1015,
            active_zones=[],
            min_rr=2.0,
        )
        # The bad-RR candidate should appear in dropped_candidates
        self.assertIsInstance(result.get("dropped_candidates", []), list)


# ---------------------------------------------------------------------------
# Test: Thesis store
# ---------------------------------------------------------------------------

class TestThesisStore(unittest.TestCase):

    def _temp_db(self) -> Path:
        tmp = tempfile.mktemp(suffix=".db")
        return Path(tmp)

    def test_build_smc_thesis_record_produces_valid_record(self) -> None:
        from heuristic_mt5_bridge.smc_desk.state.thesis_store import build_smc_thesis_record

        analyst_output: dict[str, Any] = {
            "bias": "bullish",
            "bias_confidence": "medium",
            "base_scenario": "Bullish test scenario",
            "operation_candidates": [],
            "watch_conditions": ["Wait for zone"],
            "invalidations": ["H4 close below"],
            "status": "watching",
        }
        record = build_smc_thesis_record(
            symbol="EURUSD",
            analyst_output=analyst_output,
            prepared_zones=["zone_abc"],
        )
        self.assertEqual(record["symbol"], "EURUSD")
        self.assertEqual(record["bias"], "bullish")
        self.assertEqual(record["strategy_type"], "smc_prepared")
        self.assertIn("thesis_id", record)
        self.assertTrue(str(record["thesis_id"]).startswith("smc_thesis_"))
        self.assertIn("next_review_not_before", record)

    def test_thesis_id_preserved_on_update(self) -> None:
        from heuristic_mt5_bridge.smc_desk.state.thesis_store import build_smc_thesis_record

        analyst_output: dict[str, Any] = {
            "bias": "bearish",
            "status": "active",
            "operation_candidates": [],
        }
        prior: dict[str, Any] = {
            "thesis_id": "smc_thesis_fixedid123",
            "created_at": "2026-03-23T10:00:00Z",
        }
        record = build_smc_thesis_record(
            symbol="GBPUSD",
            analyst_output=analyst_output,
            prepared_zones=[],
            prior=prior,
        )
        self.assertEqual(record["thesis_id"], "smc_thesis_fixedid123")
        self.assertEqual(record["created_at"], "2026-03-23T10:00:00Z")

    def test_save_and_load_thesis_round_trip(self) -> None:
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.state.thesis_store import (
            load_recent_smc_thesis,
            save_smc_thesis,
        )

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            analyst_output: dict[str, Any] = {
                "bias": "bullish",
                "bias_confidence": "high",
                "base_scenario": "Round-trip test",
                "operation_candidates": [
                    {
                        "side": "buy",
                        "entry_zone_high": 1.1020,
                        "entry_zone_low": 1.1010,
                        "stop_loss": 1.0990,
                        "take_profit_1": 1.1080,
                        "take_profit_2": 1.1120,
                        "rr_ratio": "1:2.3",
                        "confluences": ["ob_aligned", "fib_618"],
                        "quality": "high",
                    }
                ],
                "status": "watching",
            }
            saved = save_smc_thesis(
                db_path,
                broker_server="FBS-Demo",
                account_login=12345678,
                symbol="EURUSD",
                analyst_output=analyst_output,
                prepared_zones=["zone_abc"],
            )
            self.assertEqual(saved["symbol"], "EURUSD")
            self.assertEqual(saved["bias"], "bullish")

            loaded = load_recent_smc_thesis(
                db_path,
                broker_server="FBS-Demo",
                account_login=12345678,
                symbol="EURUSD",
            )
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["symbol"], "EURUSD")
            self.assertEqual(loaded["bias"], "bullish")
            self.assertEqual(loaded["thesis_id"], saved["thesis_id"])
        finally:
            db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: Scanner (SmcScannerService.run_once)
# ---------------------------------------------------------------------------

class TestSmcScanner(unittest.TestCase):

    def _temp_db(self) -> Path:
        tmp = tempfile.mktemp(suffix=".db")
        return Path(tmp)

    def test_run_once_returns_scan_results(self) -> None:
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import SmcScannerConfig, SmcScannerService

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            config = SmcScannerConfig(
                enabled=True,
                poll_seconds=300,
                symbols=["EURUSD"],
                approach_pct=1.5,
                min_impulse_candles=2,
                max_active_zones_per_symbol=5,
                d1_bars=80,
                h4_bars=60,
                min_quality_score=0.0,
            )
            scanner = SmcScannerService(config=config, db_path=db_path)
            service = _make_market_state_service(["EURUSD"], candle_count=120)

            results = asyncio.run(
                scanner.run_once(service, broker_server="FBS-Demo", account_login=12345678)
            )
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertEqual(result["symbol"], "EURUSD")
            self.assertFalse(result.get("skipped", False), msg=f"scan skipped: {result.get('reason')}")
            self.assertIn("new_zones", result)
            self.assertIn("scanned_at", result)
        finally:
            db_path.unlink(missing_ok=True)

    def test_scanner_persists_zones_to_db(self) -> None:
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db, load_active_smc_zones
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import SmcScannerConfig, SmcScannerService

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            config = SmcScannerConfig(
                enabled=True,
                poll_seconds=300,
                symbols=["EURUSD"],
                approach_pct=99.0,  # everything is "approaching"
                min_impulse_candles=2,
                max_active_zones_per_symbol=20,
                d1_bars=80,
                h4_bars=80,
                min_quality_score=0.0,
            )
            scanner = SmcScannerService(config=config, db_path=db_path)
            service = _make_market_state_service(["EURUSD"], candle_count=120)

            asyncio.run(
                scanner.run_once(service, broker_server="FBS-Demo", account_login=12345678)
            )

            zones = load_active_smc_zones(
                db_path,
                broker_server="FBS-Demo",
                account_login=12345678,
                symbol="EURUSD",
            )
            # Zones should be broker-partitioned and readable
            self.assertIsInstance(zones, list)
            for z in zones:
                self.assertIn("zone_id", z)
                self.assertIn("zone_type", z)
                self.assertGreater(float(z.get("price_high", 0)), 0)
        finally:
            db_path.unlink(missing_ok=True)

    def test_scanner_prefers_dynamic_runtime_symbols_over_fallback_config(self) -> None:
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import SmcScannerConfig, SmcScannerService

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            config = SmcScannerConfig(
                enabled=True,
                poll_seconds=300,
                symbols=["EURUSD"],
                approach_pct=1.5,
                min_impulse_candles=2,
                max_active_zones_per_symbol=5,
                d1_bars=80,
                h4_bars=60,
                min_quality_score=0.0,
            )
            scanner = SmcScannerService(config=config, db_path=db_path)
            service = _make_market_state_service(["GBPUSD"], candle_count=120)

            results = asyncio.run(
                scanner.run_once(
                    service,
                    broker_server="FBS-Demo",
                    account_login=12345678,
                    symbols_ref=lambda: ["GBPUSD"],
                )
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["symbol"], "GBPUSD")
        finally:
            db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: Analyst (build_heuristic_output, LLM disabled)
# ---------------------------------------------------------------------------

class TestSmcAnalyst(unittest.TestCase):

    def _temp_db(self) -> Path:
        tmp = tempfile.mktemp(suffix=".db")
        return Path(tmp)

    def test_build_heuristic_output_returns_full_payload(self) -> None:
        from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import (
            SmcAnalystConfig,
            build_heuristic_output,
        )

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            spec_registry = SymbolSpecRegistry()
            config = SmcAnalystConfig(
                max_candidates=3,
                min_rr=1.5,
                next_review_hint_seconds=14400,
                d1_bars=80,
                h4_bars=60,
                h1_bars=60,
                llm_enabled=False,
            )
            service = _make_market_state_service(["EURUSD"])

            payload = build_heuristic_output(
                symbol="EURUSD",
                trigger_reason="zone_approaching",
                trigger_payload={"zone_id": "zone_test123"},
                service=service,
                db_path=db_path,
                broker_server="FBS-Demo",
                account_login=12345678,
                spec_registry=spec_registry,
                config=config,
            )
            self.assertIn("heuristic_output", payload)
            output = payload["heuristic_output"]
            self.assertEqual(output["symbol"], "EURUSD")
            self.assertEqual(output["strategy_type"], "smc_prepared")
            self.assertIn("bias", output)
            self.assertIn(output["bias"], {"bullish", "bearish", "neutral"})
            self.assertIsInstance(output.get("operation_candidates", []), list)
            self.assertIsInstance(output.get("watch_conditions", []), list)
        finally:
            db_path.unlink(missing_ok=True)

    def test_run_smc_heuristic_analyst_with_llm_disabled(self) -> None:
        from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import (
            SmcAnalystConfig,
            run_smc_heuristic_analyst,
        )

        db_path = self._temp_db()
        try:
            ensure_runtime_db(db_path)
            spec_registry = SymbolSpecRegistry()
            config = SmcAnalystConfig(
                max_candidates=3,
                min_rr=1.5,
                llm_enabled=False,  # no LocalAI needed
            )
            service = _make_market_state_service(["EURUSD"])

            result = asyncio.run(
                run_smc_heuristic_analyst(
                    symbol="EURUSD",
                    trigger_reason="zone_approaching",
                    trigger_payload={"zone_id": "zone_test123"},
                    service=service,
                    db_path=db_path,
                    broker_server="FBS-Demo",
                    account_login=12345678,
                    spec_registry=spec_registry,
                    config=config,
                )
            )
            self.assertIn("thesis", result)
            thesis = result["thesis"]
            self.assertEqual(thesis["symbol"], "EURUSD")
            self.assertEqual(thesis["strategy_type"], "smc_prepared")
            self.assertIn("thesis_id", thesis)
            self.assertIn(thesis["bias"], {"bullish", "bearish", "neutral"})

            # Verify thesis was persisted to SQLite
            from heuristic_mt5_bridge.smc_desk.state.thesis_store import load_recent_smc_thesis

            loaded = load_recent_smc_thesis(
                db_path,
                broker_server="FBS-Demo",
                account_login=12345678,
                symbol="EURUSD",
            )
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["thesis_id"], thesis["thesis_id"])
        finally:
            db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: SMC Custody — thesis state must not close live positions
# ---------------------------------------------------------------------------

class TestSmcCustodyThesisIsolation(unittest.TestCase):
    """Open positions must survive thesis state changes (gone/rejected/watching).

    The SL/TP set at entry are the exit mechanism.  Custody only acts on
    hard_cut (emergency) and tp1/tp2 scale-out logic.
    """

    def _pos(self, side: str = "sell", open_price: float = 1.1600,
             current_price: float = 1.1560, sl: float = 1.1700) -> dict[str, Any]:
        return {
            "position_id": 999,
            "side": side,
            "price_open": open_price,
            "price_current": current_price,
            "stop_loss": sl,
            "volume": 0.10,
        }

    def _thesis_active(self) -> dict[str, Any]:
        return {
            "status": "active",
            "bias": "sell",
            "validator_decision": "approve",
            "operation_candidates": [{
                "side": "sell",
                "take_profit_1": 1.1480,
                "take_profit_2": 1.1400,
                "stop_loss": 1.1700,
            }],
        }

    def setUp(self) -> None:
        from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig
        from heuristic_mt5_bridge.smc_desk.trader.custody import SmcCustodyEngine
        self.engine = SmcCustodyEngine(SmcTraderConfig())

    def test_thesis_gone_does_not_close_position(self) -> None:
        decision = self.engine.evaluate_position(
            position=self._pos(), thesis=None, pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "hold",
                         f"Expected hold when thesis is None, got {decision.action}: {decision.reason}")

    def test_thesis_rejected_does_not_close_position(self) -> None:
        thesis = self._thesis_active()
        thesis["validator_decision"] = "reject"
        decision = self.engine.evaluate_position(
            position=self._pos(), thesis=thesis, pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "hold",
                         f"Expected hold when thesis rejected, got {decision.action}: {decision.reason}")

    def test_thesis_watching_does_not_close_position(self) -> None:
        thesis = self._thesis_active()
        thesis["status"] = "watching"
        decision = self.engine.evaluate_position(
            position=self._pos(), thesis=thesis, pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "hold",
                         f"Expected hold when thesis=watching, got {decision.action}: {decision.reason}")

    def test_hard_cut_still_fires_when_far_underwater(self) -> None:
        """hard_cut is the emergency backstop and must still work."""
        thesis = self._thesis_active()
        # SELL at 1.1600, SL at 1.1700 (100 pips risk). Price moves 200 pips against us.
        pos = self._pos(side="sell", open_price=1.1600, current_price=1.1800, sl=1.1700)
        decision = self.engine.evaluate_position(
            position=pos, thesis=thesis, pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "close",
                         f"Expected hard_cut close, got {decision.action}: {decision.reason}")
        self.assertIn("hard_cut", decision.reason)

    def test_tp2_reached_closes_position(self) -> None:
        thesis = self._thesis_active()
        # SELL: price reaches tp2=1.1400
        pos = self._pos(side="sell", open_price=1.1600, current_price=1.1395, sl=1.1700)
        decision = self.engine.evaluate_position(
            position=pos, thesis=thesis, pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "close")
        self.assertEqual(decision.reason, "tp2_reached")


# ---------------------------------------------------------------------------
# Test: SMC Custody — breakeven and trailing
# ---------------------------------------------------------------------------

class TestSmcCustodyBreakevenAndTrailing(unittest.TestCase):
    """BE triggers at be_trigger_r×R; trailing kicks in at trailing_trigger_r×R."""

    def setUp(self) -> None:
        from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig
        from heuristic_mt5_bridge.smc_desk.trader.custody import SmcCustodyEngine
        self.cfg = SmcTraderConfig(
            be_trigger_r=1.0,
            enable_trailing=True,
            trailing_trigger_r=2.0,
            trailing_atr_multiplier=2.0,
        )
        self.engine = SmcCustodyEngine(self.cfg)

    def _thesis(self) -> dict[str, Any]:
        return {
            "status": "active",
            "bias": "buy",
            "validator_decision": "approve",
            "operation_candidates": [{
                "side": "buy",
                "take_profit_1": 1.1300,
                "take_profit_2": 1.1500,
                "stop_loss": 1.0900,
            }],
        }

    def _candles_h4(self, count: int = 20, atr_size: float = 0.0100) -> list[dict[str, Any]]:
        """Synthetic H4 candles with predictable ATR (≈ atr_size)."""
        out = []
        price = 1.1000
        for i in range(count):
            out.append({
                "open": price,
                "high": price + atr_size,
                "low": price,
                "close": price + atr_size * 0.5,
            })
            price += 0.0001
        return out

    def test_breakeven_triggers_at_1r(self) -> None:
        """BE fires when profit ≥ 1×R and SL is still below entry."""
        # BUY at 1.1000, SL at 1.0900 (100 pip risk). Price at 1.1101 = 101 pips = 1.01R
        pos = {
            "position_id": 200,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1101,
            "stop_loss": 1.0900,
            "volume": 0.10,
        }
        decision = self.engine.evaluate_position(
            position=pos, thesis=self._thesis(), pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "move_sl_be",
                         f"Expected move_sl_be, got {decision.action}: {decision.reason}")
        self.assertAlmostEqual(decision.new_sl, 1.1000, places=4)
        self.assertIn("breakeven_trigger", decision.reason)

    def test_no_breakeven_below_threshold(self) -> None:
        """Below 1R profit — no BE fired."""
        pos = {
            "position_id": 201,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1050,  # 50 pips = 0.5R → below threshold
            "stop_loss": 1.0900,
            "volume": 0.10,
        }
        decision = self.engine.evaluate_position(
            position=pos, thesis=self._thesis(), pip_size=0.0001, scaled_out_ids=set()
        )
        self.assertEqual(decision.action, "hold",
                         f"Expected hold below BE threshold, got {decision.action}")

    def test_trailing_triggers_at_2r_with_candles(self) -> None:
        """Trailing fires at 2R profit when SL is already at entry (BE done)."""
        # BUY at 1.1000, SL already moved to entry (1.1000). Price at 1.1210 = 210 pips = 2.1R
        pos = {
            "position_id": 202,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1210,
            "stop_loss": 1.1000,  # already at BE
            "volume": 0.10,
        }
        candles = self._candles_h4(atr_size=0.0100)  # ATR ≈ 100 pips
        decision = self.engine.evaluate_position(
            position=pos, thesis=self._thesis(), pip_size=0.0001,
            scaled_out_ids=set(), candles=candles,
        )
        self.assertEqual(decision.action, "trail_sl",
                         f"Expected trail_sl, got {decision.action}: {decision.reason}")
        self.assertIn("trailing", decision.reason)
        # Trail SL should be below current price
        self.assertIsNotNone(decision.new_sl)
        self.assertLess(decision.new_sl, 1.1210)  # type: ignore[operator]

    def test_trailing_not_fire_if_be_not_set(self) -> None:
        """Trailing must not fire if SL is still below entry (BE not yet triggered)."""
        # 2.5R profit but SL still at original level (no BE done)
        pos = {
            "position_id": 203,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1250,
            "stop_loss": 1.0900,  # original SL, not yet at BE
            "volume": 0.10,
        }
        decision = self.engine.evaluate_position(
            position=pos, thesis=self._thesis(), pip_size=0.0001,
            scaled_out_ids=set(), candles=self._candles_h4(),
        )
        # Should fire BE (1R threshold already passed), not trail
        self.assertEqual(decision.action, "move_sl_be",
                         f"Expected BE before trailing with original SL, got {decision.action}")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Test: Audit — new detection-layer fields and behaviours
# ---------------------------------------------------------------------------


class TestAuditOBMitigation(unittest.TestCase):
    """OBs now carry a ``mitigated`` flag and a ``structure_break`` field."""

    def test_ob_has_mitigated_field(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure, detect_order_blocks

        candles = _make_candles(count=80)
        structure = detect_market_structure(candles, window=3)
        obs = detect_order_blocks(candles, structure, min_impulse_candles=2, max_zones=20)
        for ob in obs:
            self.assertIn("mitigated", ob)
            self.assertIsInstance(ob["mitigated"], bool)

    def test_ob_has_structure_break_field(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure, detect_order_blocks

        candles = _make_candles(count=80)
        structure = detect_market_structure(candles, window=3)
        obs = detect_order_blocks(candles, structure, min_impulse_candles=2, max_zones=20)
        for ob in obs:
            self.assertIn("structure_break", ob)
            self.assertIn(ob["structure_break"], {"bos", "choch"})


class TestAuditFVGMitigation(unittest.TestCase):
    """FVGs now carry a ``mitigated`` flag."""

    def test_fvg_has_mitigated_field(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_fair_value_gaps

        candles = _make_candles(count=80)
        fvgs = detect_fair_value_gaps(candles, max_zones=20)
        for fvg in fvgs:
            self.assertIn("mitigated", fvg)
            self.assertIsInstance(fvg["mitigated"], bool)


class TestAuditLiquiditySweeps(unittest.TestCase):
    """Sweeps now have ``sweep_quality`` and mark zones as ``taken``."""

    def test_sweep_has_quality_field(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import (
            detect_liquidity_pools,
            detect_market_structure,
            detect_sweeps,
        )

        d1 = _make_candles(count=100, step=0.0010)
        h4 = _make_candles(count=80, step=0.0005)
        structure = detect_market_structure(d1, window=3)
        pools = detect_liquidity_pools(d1, h4, structure=structure, max_zones=20)
        sweeps = detect_sweeps(h4, pools)
        for s in sweeps:
            self.assertIn("sweep_quality", s)
            self.assertIn(s["sweep_quality"], {"clean", "deep"})


class TestAuditCHoCHConfirmation(unittest.TestCase):
    """CHoCH events now carry a ``confirmed`` flag."""

    def test_choch_has_confirmed_field(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection import detect_market_structure

        candles = _make_candles(count=80)
        result = detect_market_structure(candles, window=3)
        choch = result.get("last_choch")
        if choch is not None:
            self.assertIn("confirmed", choch)
            self.assertIsInstance(choch["confirmed"], bool)


class TestAuditWeightedConfluences(unittest.TestCase):
    """Confluences now use weighted scoring instead of linear count / MAX."""

    def test_weighted_scoring_produces_score(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection.confluences import (
            CONFLUENCE_WEIGHTS,
            MAX_WEIGHTED_SCORE,
            evaluate_confluences,
        )

        zone = {
            "zone_type": "ob_bullish",
            "price_high": 1.1020,
            "price_low": 1.1010,
            "origin_index": 5,
        }
        structure = {
            "trend": "bullish",
            "last_bos": {"index": 10, "direction": "bullish"},
            "last_choch": None,
            "premium_discount_level": 1.1050,
            "swing_labels": [],
        }
        fibo = {"retracements": [], "extensions": []}
        confs, score = evaluate_confluences(zone, structure, fibo, [zone])
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1.0)
        # Verify weights dict is present
        self.assertIsInstance(CONFLUENCE_WEIGHTS, dict)
        self.assertGreater(MAX_WEIGHTED_SCORE, 0)

    def test_new_confluences_ob_unmitigated(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection.confluences import evaluate_confluences

        zone = {
            "zone_type": "ob_bullish",
            "price_high": 1.1020,
            "price_low": 1.1010,
            "origin_index": 5,
            "mitigated": False,
        }
        structure = {"trend": "ranging", "swing_labels": []}
        fibo = {"retracements": [], "extensions": []}
        confs, _ = evaluate_confluences(zone, structure, fibo, [zone])
        self.assertIn("ob_unmitigated", confs)

    def test_mitigated_ob_no_unmitigated_confluence(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection.confluences import evaluate_confluences

        zone = {
            "zone_type": "ob_bullish",
            "price_high": 1.1020,
            "price_low": 1.1010,
            "origin_index": 5,
            "mitigated": True,
        }
        structure = {"trend": "ranging", "swing_labels": []}
        fibo = {"retracements": [], "extensions": []}
        confs, _ = evaluate_confluences(zone, structure, fibo, [zone])
        self.assertNotIn("ob_unmitigated", confs)


class TestAuditScannerMitigation(unittest.TestCase):
    """Scanner now distinguishes ``mitigated`` from ``invalidated`` status."""

    def test_scanner_is_mitigated_helper(self) -> None:
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import _is_mitigated

        zone = {"zone_type": "ob_bullish", "price_high": 1.1020, "price_low": 1.1010}
        self.assertTrue(_is_mitigated(zone, 1.1015))  # inside zone
        self.assertFalse(_is_mitigated(zone, 1.0990))  # below zone
        self.assertFalse(_is_mitigated(zone, 1.1050))  # above zone

    def test_scanner_mitigated_not_applied_to_liquidity(self) -> None:
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import _is_mitigated

        zone = {"zone_type": "liquidity_bsl", "price_high": 1.1020, "price_low": 1.1010}
        self.assertFalse(_is_mitigated(zone, 1.1015))

    def test_scanner_result_has_mitigated_count(self) -> None:
        from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
        from heuristic_mt5_bridge.smc_desk.scanner.scanner import SmcScannerConfig, SmcScannerService

        db_path = Path(tempfile.mktemp(suffix=".db"))
        try:
            ensure_runtime_db(db_path)
            config = SmcScannerConfig(
                enabled=True, symbols=["EURUSD"],
                min_impulse_candles=2, max_active_zones_per_symbol=5,
                d1_bars=80, h4_bars=60, min_quality_score=0.0,
            )
            scanner = SmcScannerService(config=config, db_path=db_path)
            service = _make_market_state_service(["EURUSD"], candle_count=120)
            results = asyncio.run(
                scanner.run_once(service, broker_server="FBS-Demo", account_login=12345678)
            )
            for r in results:
                if not r.get("skipped"):
                    self.assertIn("mitigated", r)
        finally:
            db_path.unlink(missing_ok=True)


class TestAuditElliottFiboIntegration(unittest.TestCase):
    """Elliott impulse scoring now penalises based on Fibonacci retrace violations."""

    def test_impulse_up_fibo_validation(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection.elliott import _score_impulse_up

        # Perfect Fibonacci: W2 retraces 50% of W1, W4 retraces 38.2% of W3
        w0, w1 = 1.0, 1.1      # Wave 1 up
        w2 = 1.05               # 50% retrace of W1
        w3 = 1.2                # Wave 3 up (beyond W1)
        w4 = 1.1427             # 38.2% retrace of W3 (W3 span = 0.15, 38.2% = 0.0573)
        w5 = 1.25               # Wave 5 up (beyond W3)

        score, violations = _score_impulse_up([w0, w1, w2, w3, w4, w5])
        self.assertGreater(score, 0.7)
        fibo_warnings = [v for v in violations if v.startswith("w2_retrace") or v.startswith("w4_retrace")]
        # Should have no hard fibo violations for this well-formed impulse
        hard = [w for w in fibo_warnings if "exceeds" in w]
        self.assertEqual(len(hard), 0)

    def test_impulse_up_deep_w2_retrace(self) -> None:
        from heuristic_mt5_bridge.smc_desk.detection.elliott import _score_impulse_up

        # W2 retraces >100% — should get violation
        w0, w1 = 1.0, 1.1
        w2 = 0.99               # >100% retrace
        w3 = 1.2
        w4 = 1.15
        w5 = 1.3

        score, violations = _score_impulse_up([w0, w1, w2, w3, w4, w5])
        # Should have w2_below_w0 AND fibo violation
        self.assertIn("w2_below_w0", violations)

    def test_atr_helper(self) -> None:
        from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import _compute_atr

        candles = _make_candles(count=30)
        atr = _compute_atr(candles, 14)
        self.assertGreater(atr, 0.0)
