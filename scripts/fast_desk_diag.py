"""Diagnostic: run Fast Desk context + setup engine against live market state."""
from __future__ import annotations
import sys, json, datetime, urllib.request
sys.path.insert(0, "src")

from heuristic_mt5_bridge.fast_desk.context.service import FastContextService, FastContextConfig
from heuristic_mt5_bridge.fast_desk.setup.engine import FastSetupEngine, FastSetupConfig
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
import sqlite3

BASE = "http://localhost:8765"

def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=8) as r:
        return json.loads(r.read())

def vol_regime(candles: list) -> tuple[float, str]:
    sample = candles[-24:]
    ranges, bodies = [], []
    for c in sample:
        h, l = float(c.get("high") or 0), float(c.get("low") or 0)
        o, cl = float(c.get("open") or 0), float(c.get("close") or 0)
        if h > 0 and l > 0:
            ranges.append(max(0.0, h - l))
            bodies.append(abs(cl - o))
    avg_rng = sum(ranges) / len(ranges) if ranges else 0
    avg_bdy = sum(bodies) / len(bodies) if bodies else 0
    ratio = avg_rng / avg_bdy if avg_bdy > 0 else 0
    r = "very_low" if ratio < 1.6 else "low" if ratio < 2.2 else "normal" if ratio < 3.5 else "high"
    return ratio, r

def feed_age(candles: list) -> float:
    if not candles:
        return 9999.0
    ts_raw = candles[-1].get("timestamp", "")
    try:
        last_dt = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - last_dt).total_seconds()
    except Exception:
        return 9999.0

def main():
    # Load symbol specs from DB
    db = sqlite3.connect("storage/runtime.db")
    db.row_factory = sqlite3.Row
    spec_rows = db.execute("SELECT * FROM symbol_spec_cache").fetchall()
    db.close()

    spec_map: dict[str, dict] = {}
    for row in spec_rows:
        d = dict(row)
        sym = d.get("symbol", "")
        if sym:
            spec_map[sym] = d

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "BTCUSD"]
    print("=" * 80)
    print("FAST DESK DIAGNOSTIC")
    print("=" * 80)

    for sym in symbols:
        print(f"\n--- {sym} ---")
        try:
            c1  = get(f"/chart/{sym}/M1?bars=220").get("candles", [])
            c5  = get(f"/chart/{sym}/M5?bars=220").get("candles", [])
            ch1 = get(f"/chart/{sym}/H1?bars=220").get("candles", [])
        except Exception as e:
            print(f"  ERROR fetching candles: {e}")
            continue

        print(f"  Bars: M1={len(c1)} M5={len(c5)} H1={len(ch1)}")

        age = feed_age(c1)
        stale = age > 180
        print(f"  M1 feed age: {age:.0f}s  stale={stale}")

        ratio, regime = vol_regime(c5)
        no_trade = regime == "very_low"
        print(f"  Volatility: ratio={ratio:.2f} regime={regime}  no_trade_regime={no_trade}")

        if len(c1) < 30 or len(c5) < 40 or len(ch1) < 20:
            print("  BLOCKED: insufficient candles")
            continue

        # Check spread via tick endpoint
        try:
            tick_data = get(f"/chart/{sym}/M1?bars=1")
            # We'll use close from last M1 bar as tick price proxy
            last_close = float(c1[-1].get("close", 0) or 0) if c1 else 0
            print(f"  Last M1 close: {last_close}")
        except Exception:
            pass

        # Context check (no actual connector — spread check won't fire)
        spec = spec_map.get(sym, {})
        pip_size = float(spec.get("pip_size") or spec.get("point") or 0.0001)
        point_size = float(spec.get("point") or pip_size)
        print(f"  Spec: pip_size={pip_size}  point_size={point_size}")

        cfg = FastContextConfig(
            spread_tolerance="high",
            max_slippage_pct=0.10,
            stale_feed_seconds=180,
            require_h1_alignment=True,
            allowed_sessions=("global",),
        )
        ctx_svc = FastContextService(cfg)
        ctx = ctx_svc.build_context(
            symbol=sym,
            candles_m1=c1,
            candles_m5=c5,
            candles_h1=ch1,
            pip_size=pip_size,
            point_size=point_size,
            connector=None,
            prefetched_tick=None,
            symbol_spec=spec,
        )
        print(f"  Context: allowed={ctx.allowed}  h1_bias={ctx.h1_bias}  session={ctx.session_name}")
        if ctx.reasons:
            print(f"  BLOCKED reasons: {ctx.reasons}")

        if not ctx.allowed:
            continue

        # Setup detection
        setup_cfg = FastSetupConfig(rr_ratio=2.0, min_confidence=0.55)
        setup_eng = FastSetupEngine(setup_cfg)
        setups = setup_eng.detect_setups(
            symbol=sym,
            candles_m5=c5,
            candles_h1=ch1,
            pip_size=pip_size,
            h1_bias=ctx.h1_bias,
        )
        print(f"  Setups found: {len(setups)}")
        from heuristic_mt5_bridge.fast_desk.trigger.engine import FastTriggerEngine, FastTriggerConfig
        from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskEngine, FastRiskConfig
        from heuristic_mt5_bridge.fast_desk.policies.entry import FastEntryPolicy
        trigger_eng = FastTriggerEngine(FastTriggerConfig(displacement_body_factor=1.8))
        risk_eng = FastRiskEngine()
        entry_pol = FastEntryPolicy()
        h1_align = True
        
        # Simulate the full scan_and_execute pipeline
        # account state  
        balance = 1182668.28
        equity = 1182668.28
        account_state = {"balance": balance, "equity": equity, "drawdown_percent": 0.0}
        
        # risk kernel result (from /risk/status)
        risk_decision = {"allowed": True, "risk_per_trade_pct": 1.449032, "limits": {"max_positions_total": 14, "max_positions_per_symbol": 5}, "global_limits": {"max_drawdown_pct": 15.0, "max_positions_total": 20}}
        
        dynamic_risk = FastRiskConfig(
            risk_per_trade_percent=float(risk_decision.get("risk_per_trade_pct", 1.449032)),
            max_drawdown_percent=15.0,
            max_positions_per_symbol=5,
            max_positions_total=14,
        )
        
        pip_val_from_spec = float(spec.get("tick_value") or pip_size or 0.0001)
        print(f"  Pipeline params: balance={balance}  risk_pct={dynamic_risk.risk_per_trade_percent:.4f}  pip_value={pip_val_from_spec}")
        print(f"  account_safe={risk_eng.check_account_safe(account_state, dynamic_risk)}")
        
        for s in setups[:5]:
            if h1_align and ctx.h1_bias in {"buy", "sell"} and s.side != ctx.h1_bias:
                print(f"    {s.setup_type} {s.side}  FILTERED(h1_align)")
                continue
            trig = trigger_eng.confirm(setup=s, candles_m1=c1, pip_size=pip_size)
            # Entry policy check
            ep_allowed, ep_reasons = entry_pol.can_open(sym, s.side, [], dynamic_risk)
            # Lot size
            lot = risk_eng.calculate_lot_size(balance, dynamic_risk.risk_per_trade_percent, s.risk_pips, pip_val_from_spec)
            print(f"    {s.setup_type} {s.side}  entry={s.entry_price:.5f}  risk_pips={s.risk_pips:.1f}  lot={lot:.2f}  trigger={trig.trigger_type}/{trig.confirmed}  entry_policy={ep_allowed}")
            if ep_allowed and trig.confirmed:
                print(f"      *** WOULD EXECUTE: lot={lot} {'PENDING-'+s.pending_entry_type if s.requires_pending else 'MARKET'} ***")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
