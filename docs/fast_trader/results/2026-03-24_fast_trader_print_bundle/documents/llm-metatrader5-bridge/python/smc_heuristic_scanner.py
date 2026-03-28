"""
SMC Heuristic Scanner — pure Python runtime (no LLM).

Runs in its own thread, reads market_state candles for D1/H4 timeframes,
detects SMC zones using smc_zone_detection modules, persists results in
smc_zone_cache (SQLite) + JSON fallback, and emits events to registered
callbacks.

Events emitted:
    zone_approaching    — price is within SMC_ZONE_APPROACH_PCT of a zone
    sweep_detected      — a sweep was detected at a known liquidity zone
    zone_invalidated    — a zone was mitigated (price closed through it)
    new_zone_detected   — a new high-quality zone was found

Configuration via .env:
    SMC_SCANNER_ENABLED=true
    SMC_SCANNER_POLL_SECONDS=300
    SMC_SCANNER_SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF
    SMC_ZONE_APPROACH_PCT=1.5
    SMC_MIN_IMPULSE_CANDLES=3
    SMC_MAX_ACTIVE_ZONES_PER_SYMBOL=10
    SMC_SCANNER_D1_BARS=100
    SMC_SCANNER_H4_BARS=200
    SMC_SCANNER_H1_BARS=300
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from market_state_core import MarketStateService
from runtime_db import (
    ensure_runtime_db,
    load_active_smc_zones,
    log_smc_event,
    runtime_db_path,
    upsert_smc_zone,
)
from smc_zone_detection import (
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
from smc_zone_detection.fibonacci import fibo_levels_for_structure


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def config() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    env_values = load_env_file(repo_root / ".env")

    def _env(key: str, default: str) -> str:
        return os.getenv(key, env_values.get(key, default))

    configured_storage = Path(_env("STORAGE_ROOT", str(repo_root / "python" / "storage")))
    storage_root = configured_storage if configured_storage.is_absolute() else repo_root / configured_storage

    symbols_raw = _env("SMC_SCANNER_SYMBOLS", _env("MT5_WATCH_SYMBOLS", "EURUSD,GBPUSD,USDJPY,USDCHF"))
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

    return {
        "repo_root": repo_root,
        "storage_root": storage_root,
        "runtime_db_path": runtime_db_path(
            storage_root,
            os.getenv("RUNTIME_DB_PATH", env_values.get("RUNTIME_DB_PATH")),
        ),
        "enabled": _env("SMC_SCANNER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        "poll_seconds": float(_env("SMC_SCANNER_POLL_SECONDS", "300")),
        "symbols": symbols,
        "approach_pct": float(_env("SMC_ZONE_APPROACH_PCT", "1.5")),
        "min_impulse_candles": int(_env("SMC_MIN_IMPULSE_CANDLES", "3")),
        "max_active_zones_per_symbol": int(_env("SMC_MAX_ACTIVE_ZONES_PER_SYMBOL", "10")),
        "d1_bars": int(_env("SMC_SCANNER_D1_BARS", "100")),
        "h4_bars": int(_env("SMC_SCANNER_H4_BARS", "200")),
        "h1_bars": int(_env("SMC_SCANNER_H1_BARS", "300")),
        "min_quality_score": float(_env("SMC_MIN_QUALITY_SCORE", "0.2")),
    }


CFG = config()

# ---------------------------------------------------------------------------
# Event callbacks registry
# ---------------------------------------------------------------------------

_EVENT_CALLBACKS: list[Callable[[str, str, dict[str, Any]], None]] = []


def register_smc_event_callback(fn: Callable[[str, str, dict[str, Any]], None]) -> None:
    """Register a callback invoked as fn(event_type, symbol, payload)."""
    _EVENT_CALLBACKS.append(fn)


def _emit(event_type: str, symbol: str, payload: dict[str, Any]) -> None:
    log_smc_event(CFG["runtime_db_path"], symbol=symbol, event_type=event_type, payload=payload)
    for fn in _EVENT_CALLBACKS:
        try:
            fn(event_type, symbol, payload)
        except Exception as exc:
            print(f"[smc-scanner] callback error ({event_type} {symbol}): {exc}")


# ---------------------------------------------------------------------------
# Zone ID generation
# ---------------------------------------------------------------------------

def _make_zone_id(symbol: str, timeframe: str, zone_type: str, origin_time: str) -> str:
    slug = f"{symbol}::{timeframe}::{zone_type}::{origin_time}"
    import hashlib
    return "zone_" + hashlib.sha1(slug.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Current-price extraction from market_state_service
# ---------------------------------------------------------------------------

def _current_price(service: MarketStateService, symbol: str) -> float | None:
    # Use H1 as reference for "current price" when D1/H4 are used for zones
    for tf in ("H1", "M15", "H4", "D1"):
        candles = service.get_candles(symbol, tf, bars=1)
        if candles:
            c = candles[-1]
            p = c.get("close")
            if isinstance(p, (int, float)) and p > 0:
                return float(p)
    return None


# ---------------------------------------------------------------------------
# Invalidation logic
# ---------------------------------------------------------------------------

def _is_invalidated(zone: dict[str, Any], current_price: float) -> bool:
    """A zone is invalidated when price closes through it."""
    z_type = str(zone.get("zone_type", ""))
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)

    is_bullish = z_type in {"ob_bullish", "fvg_bullish", "liquidity_ssl", "equal_lows"}
    is_bearish = z_type in {"ob_bearish", "fvg_bearish", "liquidity_bsl", "equal_highs"}

    # Bullish zone invalidated if price closes below the zone
    if is_bullish and current_price < z_low:
        return True
    # Bearish zone invalidated if price closes above the zone
    if is_bearish and current_price > z_high:
        return True
    return False


def _distance_pct(zone: dict[str, Any], current_price: float) -> float:
    """Distance from current_price to nearest zone edge, in %."""
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)
    if current_price >= z_low and current_price <= z_high:
        return 0.0  # inside zone
    nearest = z_high if abs(current_price - z_high) < abs(current_price - z_low) else z_low
    if nearest <= 0:
        return 999.0
    return round(abs(current_price - nearest) / nearest * 100, 4)


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def _persist_zone_json(zone: dict[str, Any]) -> None:
    target = CFG["storage_root"] / "smc_scanner" / str(zone.get("symbol", "unknown")).upper()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{zone['zone_id']}.json"
    path.write_text(json.dumps(zone, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core scan for a single symbol
# ---------------------------------------------------------------------------

def scan_symbol(
    service: MarketStateService,
    symbol: str,
) -> dict[str, Any]:
    """Run a full SMC scan for one symbol. Returns a summary dict."""
    d1_candles = service.get_candles(symbol, "D1", bars=CFG["d1_bars"])
    h4_candles = service.get_candles(symbol, "H4", bars=CFG["h4_bars"])

    if len(d1_candles) < 10 or len(h4_candles) < 10:
        return {"symbol": symbol, "skipped": True, "reason": f"insufficient_candles (D1={len(d1_candles)} H4={len(h4_candles)})"}

    current_price = _current_price(service, symbol)

    # 1. Detect structure on D1 (higher TF for bias)
    structure_d1 = detect_market_structure(d1_candles, window=3)
    # 2. Detect structure on H4 (execution TF)
    structure_h4 = detect_market_structure(h4_candles, window=3)

    # 3. Fibonacci from D1 structure
    fibo = fibo_levels_for_structure(structure_d1)

    # 4. Elliott wave count (D1)
    elliott = count_waves(structure_d1)

    # 5. Detect zones on H4
    obs = detect_order_blocks(
        h4_candles,
        structure_h4,
        min_impulse_candles=CFG["min_impulse_candles"],
        max_zones=CFG["max_active_zones_per_symbol"],
    )
    fvgs = detect_fair_value_gaps(h4_candles, max_zones=CFG["max_active_zones_per_symbol"])
    liquidity = detect_liquidity_pools(
        d1_candles,
        h4_candles,
        structure=structure_d1,
        max_zones=CFG["max_active_zones_per_symbol"],
    )

    # 6. Detect sweeps on H4 against known liquidity
    existing_zones = load_active_smc_zones(CFG["runtime_db_path"], symbol=symbol)
    all_raw_zones: list[dict[str, Any]] = obs + fvgs + liquidity
    sweeps = detect_sweeps(h4_candles, existing_zones + liquidity)

    # 7. Build unified candidate list
    candidates: list[dict[str, Any]] = []
    for raw in all_raw_zones:
        origin_time = str(raw.get("origin_candle_time", ""))
        zone_id = _make_zone_id(symbol, "H4", raw["zone_type"], origin_time)
        # Evaluate confluences
        all_candidates_so_far = all_raw_zones + [s for s in sweeps]
        confluences, quality_score = evaluate_confluences(
            raw, structure_d1, fibo, all_candidates_so_far
        )
        if quality_score < CFG["min_quality_score"]:
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
            "detected_at": utc_now_iso(),
            "invalidated_at": None,
            "distance_pct": dist,
        })

    # Deduplicate against already-persisted zones (same zone_id)
    existing_ids = {z["zone_id"] for z in existing_zones}
    new_zones = [z for z in candidates if z["zone_id"] not in existing_ids]

    # 8. Cap: enforce max_active_zones_per_symbol
    max_zones = CFG["max_active_zones_per_symbol"]
    # Sort by quality_score desc, keep the best
    new_zones.sort(key=lambda z: z["quality_score"], reverse=True)
    new_zones = new_zones[:max(0, max_zones - len(existing_ids))]

    # 9. Persist new zones
    for zone in new_zones:
        upsert_smc_zone(CFG["runtime_db_path"], zone)
        _persist_zone_json(zone)
        _emit("new_zone_detected", symbol, {"zone_id": zone["zone_id"], "zone_type": zone["zone_type"], "quality_score": zone["quality_score"]})

    # 10. Update existing zones: check approach + invalidation
    approaching_count = 0
    invalidated_count = 0
    all_active = existing_zones + new_zones
    for zone in all_active:
        if str(zone.get("status", "")) == "invalidated":
            continue
        if current_price is None:
            continue
        if _is_invalidated(zone, current_price):
            zone["status"] = "invalidated"
            zone["invalidated_at"] = utc_now_iso()
            zone["distance_pct"] = 0.0
            upsert_smc_zone(CFG["runtime_db_path"], zone)
            _emit("zone_invalidated", symbol, {"zone_id": zone["zone_id"], "zone_type": zone["zone_type"], "price": current_price})
            invalidated_count += 1
        else:
            dist = _distance_pct(zone, current_price)
            new_status = "approaching" if dist <= CFG["approach_pct"] else "active"
            if new_status != str(zone.get("status", "active")) or abs((zone.get("distance_pct") or 999) - dist) > 0.01:
                zone["status"] = new_status
                zone["distance_pct"] = dist
                upsert_smc_zone(CFG["runtime_db_path"], zone)
                if new_status == "approaching":
                    _emit(
                        "zone_approaching",
                        symbol,
                        {
                            "zone_id": zone["zone_id"],
                            "zone_type": zone["zone_type"],
                            "distance_pct": dist,
                            "quality_score": zone.get("quality_score", 0.0),
                        },
                    )
                    approaching_count += 1

    # 11. Persist sweep events
    for sweep in sweeps:
        _emit(
            "sweep_detected",
            symbol,
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
        "sweeps": len(sweeps),
        "structure_d1_trend": structure_d1.get("trend"),
        "elliott_pattern": elliott.get("pattern_type"),
        "scanned_at": utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Main scanner loop
# ---------------------------------------------------------------------------

def run_scanner_loop(service: MarketStateService | None = None) -> None:
    """Block forever, scanning all configured symbols every poll_seconds.

    Re-bootstraps MarketStateService at the start of each cycle so candle
    data stays current even though this process is separate from
    market_state_runtime.py.
    """
    if not CFG["enabled"]:
        print("[smc-scanner] disabled (SMC_SCANNER_ENABLED=false)")
        return

    from market_state_bootstrap import bootstrap_market_state

    ensure_runtime_db(CFG["runtime_db_path"])
    symbols = CFG["symbols"]
    poll = CFG["poll_seconds"]
    print(f"[smc-scanner] starting — symbols={symbols} poll={poll}s")

    while True:
        cycle_start = time.monotonic()
        # Fresh service each cycle — reads latest snapshots written by market_state_runtime
        try:
            fresh_service, _ = bootstrap_market_state(
                symbols=symbols,
                timeframes=["D1", "H4", "H1"],
                prefer_live_mt5=True,
                bars_per_key=max(CFG["d1_bars"], CFG["h4_bars"], CFG["h1_bars"]),
            )
        except Exception as exc:
            print(f"[smc-scanner] bootstrap failed: {exc} — skipping cycle")
            time.sleep(poll)
            continue

        results = []
        for symbol in symbols:
            try:
                result = scan_symbol(fresh_service, symbol)
                results.append(result)
                status = "skipped" if result.get("skipped") else (
                    f"new={result.get('new_zones',0)} approaching={result.get('approaching',0)} "
                    f"invalidated={result.get('invalidated',0)} sweeps={result.get('sweeps',0)}"
                )
                print(f"[smc-scanner] {symbol}: {status}")
            except Exception as exc:
                print(f"[smc-scanner] {symbol} error: {exc}")

        elapsed = time.monotonic() - cycle_start
        sleep_time = max(0.0, poll - elapsed)
        time.sleep(sleep_time)


def main() -> None:
    """Standalone entry point for testing the scanner."""
    run_scanner_loop()


if __name__ == "__main__":
    main()
