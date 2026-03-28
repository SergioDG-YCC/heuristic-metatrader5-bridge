"""
SMC Heuristic Scanner — pure Python runtime (no LLM).

Reads market_state candles for D1/H4 timeframes, detects SMC zones using
detection modules, persists results in smc_zones (SQLite, broker-partitioned),
and emits events to registered callbacks.

Events emitted:
    zone_approaching    — price is within SMC_ZONE_APPROACH_PCT of a zone
    sweep_detected      — a sweep was detected at a known liquidity zone
    zone_invalidated    — a zone was mitigated (price closed through it)
    new_zone_detected   — a new high-quality zone was found

Configuration (env vars):
    SMC_SCANNER_ENABLED=true
    SMC_SCANNER_POLL_SECONDS=300
    SMC_SCANNER_SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF
    SMC_ZONE_APPROACH_PCT=1.5
    SMC_MIN_IMPULSE_CANDLES=3
    SMC_MAX_ACTIVE_ZONES_PER_SYMBOL=10
    SMC_SCANNER_D1_BARS=100
    SMC_SCANNER_H4_BARS=200
    SMC_MIN_QUALITY_SCORE=0.2
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.infra.storage.runtime_db import (
    ensure_runtime_db,
    load_active_smc_zones,
    log_smc_event,
    upsert_smc_zone,
)
from heuristic_mt5_bridge.shared.symbols.universe import is_operable_symbol, normalize_symbol
from heuristic_mt5_bridge.smc_desk.detection import (
    calculate_extensions,
    calculate_retracements,
    count_waves,
    detect_fair_value_gaps,
    detect_liquidity_pools,
    detect_market_structure,
    detect_order_blocks,
    detect_sweeps,
    evaluate_confluences,
)
from heuristic_mt5_bridge.smc_desk.detection.fibonacci import fibo_levels_for_structure


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class SmcScannerConfig:
    enabled: bool = True
    poll_seconds: float = 300.0
    symbols: list[str] = field(default_factory=list)
    approach_pct: float = 1.5
    min_impulse_candles: int = 3
    max_active_zones_per_symbol: int = 10
    d1_bars: int = 100
    h4_bars: int = 200
    min_quality_score: float = 0.2

    @classmethod
    def from_env(cls) -> "SmcScannerConfig":
        def _env(key: str, default: str) -> str:
            return os.getenv(key, default)

        symbols_raw = _env("SMC_SCANNER_SYMBOLS", _env("MT5_WATCH_SYMBOLS", "EURUSD,GBPUSD,USDJPY,USDCHF"))
        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

        return cls(
            enabled=_env("SMC_SCANNER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
            poll_seconds=float(_env("SMC_SCANNER_POLL_SECONDS", "300")),
            symbols=symbols,
            approach_pct=float(_env("SMC_ZONE_APPROACH_PCT", "1.5")),
            min_impulse_candles=int(_env("SMC_MIN_IMPULSE_CANDLES", "3")),
            max_active_zones_per_symbol=int(_env("SMC_MAX_ACTIVE_ZONES_PER_SYMBOL", "10")),
            d1_bars=int(_env("SMC_SCANNER_D1_BARS", "100")),
            h4_bars=int(_env("SMC_SCANNER_H4_BARS", "200")),
            min_quality_score=float(_env("SMC_MIN_QUALITY_SCORE", "0.2")),
        )


# ---------------------------------------------------------------------------
# Event callbacks
# ---------------------------------------------------------------------------

_EVENT_CALLBACKS: list[Callable[[str, str, dict[str, Any]], None]] = []


def register_smc_event_callback(fn: Callable[[str, str, dict[str, Any]], None]) -> None:
    """Register a callback invoked as fn(event_type, symbol, payload)."""
    _EVENT_CALLBACKS.append(fn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zone_id(symbol: str, timeframe: str, zone_type: str, origin_time: str) -> str:
    slug = f"{symbol}::{timeframe}::{zone_type}::{origin_time}"
    return "zone_" + hashlib.sha1(slug.encode()).hexdigest()[:16]


def _current_price(service: MarketStateService, symbol: str) -> float | None:
    for tf in ("H1", "M15", "H4", "D1"):
        candles = service.get_candles(symbol, tf, bars=1)
        if candles:
            c = candles[-1]
            p = c.get("close")
            if isinstance(p, (int, float)) and p > 0:
                return float(p)
    return None


def _is_invalidated(zone: dict[str, Any], current_price: float) -> bool:
    z_type = str(zone.get("zone_type", ""))
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)

    is_bullish = z_type in {"ob_bullish", "fvg_bullish", "liquidity_ssl", "equal_lows"}
    is_bearish = z_type in {"ob_bearish", "fvg_bearish", "liquidity_bsl", "equal_highs"}

    if is_bullish and current_price < z_low:
        return True
    if is_bearish and current_price > z_high:
        return True
    return False


def _is_mitigated(zone: dict[str, Any], current_price: float) -> bool:
    """A zone is mitigated when price is currently inside the zone body.

    OBs and FVGs are single-use: once price revisits and reacts, they are
    consumed.  We detect this when price enters the zone — the scanner marks
    it as ``mitigated`` so it won't be used for new setups.
    """
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)
    z_type = str(zone.get("zone_type", ""))
    if z_type not in {"ob_bullish", "ob_bearish", "fvg_bullish", "fvg_bearish"}:
        return False
    return z_low <= current_price <= z_high


def _distance_pct(zone: dict[str, Any], current_price: float) -> float:
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)
    if current_price >= z_low and current_price <= z_high:
        return 0.0
    nearest = z_high if abs(current_price - z_high) < abs(current_price - z_low) else z_low
    if nearest <= 0:
        return 999.0
    return round(abs(current_price - nearest) / nearest * 100, 4)


# ---------------------------------------------------------------------------
# Core scan for a single symbol
# ---------------------------------------------------------------------------

def scan_symbol(
    service: MarketStateService,
    symbol: str,
    *,
    config: SmcScannerConfig,
    db_path: Path,
    broker_server: str,
    account_login: int,
) -> dict[str, Any]:
    """Run a full SMC scan for one symbol. Returns a summary dict."""
    d1_candles = service.get_candles(symbol, "D1", bars=config.d1_bars)
    h4_candles = service.get_candles(symbol, "H4", bars=config.h4_bars)

    if len(d1_candles) < 10 or len(h4_candles) < 10:
        return {
            "symbol": symbol,
            "skipped": True,
            "reason": f"insufficient_candles (D1={len(d1_candles)} H4={len(h4_candles)})",
        }

    current_price = _current_price(service, symbol)

    # Event emitter with broker identity
    def _emit(event_type: str, payload: dict[str, Any]) -> None:
        try:
            log_smc_event(
                db_path,
                broker_server=broker_server,
                account_login=account_login,
                symbol=symbol,
                event_type=event_type,
                payload=payload,
            )
        except Exception as exc:
            print(f"[smc-scanner] log_smc_event error ({event_type} {symbol}): {exc}")
        for fn in _EVENT_CALLBACKS:
            try:
                fn(event_type, symbol, payload)
            except Exception as exc:
                print(f"[smc-scanner] callback error ({event_type} {symbol}): {exc}")

    # 1. Detect structure
    structure_d1 = detect_market_structure(d1_candles, window=3)
    structure_h4 = detect_market_structure(h4_candles, window=3)

    # 2. Fibonacci from D1
    fibo = fibo_levels_for_structure(structure_d1)

    # 3. Elliott wave count (D1)
    elliott = count_waves(structure_d1)

    # 4. Detect zones on H4
    obs = detect_order_blocks(
        h4_candles,
        structure_h4,
        min_impulse_candles=config.min_impulse_candles,
        max_zones=config.max_active_zones_per_symbol,
    )
    fvgs = detect_fair_value_gaps(h4_candles, max_zones=config.max_active_zones_per_symbol)
    liquidity = detect_liquidity_pools(
        d1_candles,
        h4_candles,
        structure=structure_d1,
        max_zones=config.max_active_zones_per_symbol,
    )

    # 5. Load existing zones and detect sweeps
    existing_zones = load_active_smc_zones(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
    )
    all_raw_zones: list[dict[str, Any]] = obs + fvgs + liquidity
    sweeps = detect_sweeps(h4_candles, existing_zones + liquidity)

    # 6. Build candidate list with confluences (skip already-mitigated zones)
    candidates: list[dict[str, Any]] = []
    for raw in all_raw_zones:
        if raw.get("mitigated"):
            continue
        origin_time = str(raw.get("origin_candle_time", ""))
        zone_id = _make_zone_id(symbol, "H4", raw["zone_type"], origin_time)
        all_context = all_raw_zones + [s for s in sweeps]
        confluences, quality_score = evaluate_confluences(raw, structure_d1, fibo, all_context)
        if quality_score < config.min_quality_score:
            continue
        dist = _distance_pct(raw, current_price) if current_price else None
        candidates.append({
            "zone_id": zone_id,
            "symbol": symbol,
            "timeframe": "H4",
            "zone_type": raw["zone_type"],
            "price_high": raw["price_high"],
            "price_low": raw["price_low"],
            "origin_candle_time": origin_time,
            "status": "active",
            "quality_score": quality_score,
            "confluences": confluences,
            "detected_at": _utc_now_iso(),
            "invalidated_at": None,
            "distance_pct": dist,
        })

    # Deduplicate against existing zones
    existing_ids = {z["zone_id"] for z in existing_zones}
    new_zones = [z for z in candidates if z["zone_id"] not in existing_ids]

    # Cap at remaining capacity
    max_zones = config.max_active_zones_per_symbol
    new_zones.sort(key=lambda z: z["quality_score"], reverse=True)
    new_zones = new_zones[:max(0, max_zones - len(existing_ids))]

    # 7. Persist new zones
    for zone in new_zones:
        upsert_smc_zone(db_path, broker_server=broker_server, account_login=account_login, zone=zone)
        _emit(
            "new_zone_detected",
            {"zone_id": zone["zone_id"], "zone_type": zone["zone_type"], "quality_score": zone["quality_score"]},
        )

    # 8. Update existing zones: mitigation → invalidation → approach
    approaching_count = 0
    invalidated_count = 0
    mitigated_count = 0
    all_active = existing_zones + new_zones
    for zone in all_active:
        cur_status = str(zone.get("status", ""))
        if cur_status in {"invalidated", "mitigated"}:
            continue
        if current_price is None:
            continue
        # Mitigation check first (OB/FVG only) — price inside the zone
        if _is_mitigated(zone, current_price):
            zone["status"] = "mitigated"
            zone["invalidated_at"] = _utc_now_iso()
            zone["distance_pct"] = 0.0
            upsert_smc_zone(db_path, broker_server=broker_server, account_login=account_login, zone=zone)
            _emit(
                "zone_mitigated",
                {"zone_id": zone["zone_id"], "zone_type": zone["zone_type"], "price": current_price},
            )
            mitigated_count += 1
        elif _is_invalidated(zone, current_price):
            zone["status"] = "invalidated"
            zone["invalidated_at"] = _utc_now_iso()
            zone["distance_pct"] = 0.0
            upsert_smc_zone(db_path, broker_server=broker_server, account_login=account_login, zone=zone)
            _emit(
                "zone_invalidated",
                {"zone_id": zone["zone_id"], "zone_type": zone["zone_type"], "price": current_price},
            )
            invalidated_count += 1
        else:
            dist = _distance_pct(zone, current_price)
            new_status = "approaching" if dist <= config.approach_pct else "active"
            prev_dist = zone.get("distance_pct")
            if new_status != str(zone.get("status", "active")) or (
                prev_dist is not None and abs(float(prev_dist) - dist) > 0.01
            ):
                zone["status"] = new_status
                zone["distance_pct"] = dist
                upsert_smc_zone(db_path, broker_server=broker_server, account_login=account_login, zone=zone)
                if new_status == "approaching":
                    _emit(
                        "zone_approaching",
                        {
                            "zone_id": zone["zone_id"],
                            "zone_type": zone["zone_type"],
                            "distance_pct": dist,
                            "quality_score": zone.get("quality_score", 0.0),
                        },
                    )
                    approaching_count += 1

    # 9. Log sweep events
    for sweep in sweeps:
        _emit(
            "sweep_detected",
            {
                "zone_type": sweep["zone_type"],
                "swept_level": sweep.get("swept_level"),
                "sweep_candle_time": sweep.get("sweep_candle_time"),
                "origin_zone_type": sweep.get("origin_zone_type"),
            },
        )

    return {
        "symbol": symbol,
        "skipped": False,
        "new_zones": len(new_zones),
        "approaching": approaching_count,
        "invalidated": invalidated_count,
        "mitigated": mitigated_count,
        "sweeps": len(sweeps),
        "structure_d1_trend": structure_d1.get("trend"),
        "elliott_pattern": elliott.get("pattern_type"),
        "scanned_at": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Scanner service class
# ---------------------------------------------------------------------------

class SmcScannerService:
    """Asyncio-compatible SMC scanner service.

    Used by SmcDeskService inside CoreRuntimeService.run_forever().
    All CPU-bound work is offloaded via asyncio.to_thread.
    """

    def __init__(self, config: SmcScannerConfig, db_path: Path) -> None:
        self._config = config
        self._db_path = db_path

    def _ensure_db(self) -> None:
        ensure_runtime_db(self._db_path)

    def _resolve_symbols(
        self,
        symbols_ref: Callable[[], list[str]] | None = None,
    ) -> list[str]:
        def _normalize(symbols: list[str]) -> list[str]:
            ordered: list[str] = []
            seen: set[str] = set()
            for raw in symbols:
                symbol = normalize_symbol(raw)
                if not symbol or symbol in seen or not is_operable_symbol(symbol):
                    continue
                ordered.append(symbol)
                seen.add(symbol)
            return ordered

        if symbols_ref is not None:
            try:
                return _normalize(symbols_ref())
            except Exception as exc:
                print(f"[smc-scanner] dynamic symbols_ref error: {exc}")
        return _normalize(self._config.symbols)

    def _scan_all_sync(
        self,
        service: MarketStateService,
        broker_server: str,
        account_login: int,
        symbols: list[str],
    ) -> list[dict[str, Any]]:
        """Synchronous scan of all configured symbols. Run in thread."""
        results = []
        for symbol in symbols:
            try:
                result = scan_symbol(
                    service,
                    symbol,
                    config=self._config,
                    db_path=self._db_path,
                    broker_server=broker_server,
                    account_login=account_login,
                )
                results.append(result)
                if result.get("skipped"):
                    print(f"[smc-scanner] {symbol}: skipped ({result.get('reason', '')})")
                else:
                    print(
                        f"[smc-scanner] {symbol}: "
                        f"new={result.get('new_zones', 0)} "
                        f"approaching={result.get('approaching', 0)} "
                        f"invalidated={result.get('invalidated', 0)} "
                        f"sweeps={result.get('sweeps', 0)}"
                    )
            except Exception as exc:
                print(f"[smc-scanner] {symbol} error: {exc}")
        return results

    async def run_once(
        self,
        service: MarketStateService,
        broker_server: str,
        account_login: int,
        symbols_ref: Callable[[], list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run one scan cycle (async, offloaded to thread)."""
        import asyncio

        self._ensure_db()
        symbols = self._resolve_symbols(symbols_ref)
        return await asyncio.to_thread(
            self._scan_all_sync, service, broker_server, account_login, symbols
        )

    async def run_forever(
        self,
        service: MarketStateService,
        broker_server: str,
        account_login: int,
        symbols_ref: Callable[[], list[str]] | None = None,
    ) -> None:
        """Periodic scanner loop. Runs until cancelled."""
        import asyncio

        if not self._config.enabled:
            print("[smc-scanner] disabled (SMC_SCANNER_ENABLED=false)")
            return

        print(
            f"[smc-scanner] starting — "
            f"fallback_symbols={self._config.symbols} "
            f"poll={self._config.poll_seconds}s"
        )
        while True:
            try:
                await self.run_once(service, broker_server, account_login, symbols_ref=symbols_ref)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[smc-scanner] cycle error: {exc}")
            await asyncio.sleep(self._config.poll_seconds)
