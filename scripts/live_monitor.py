"""Live monitor — queries control plane and runtime DB to show what's happening."""
import sqlite3
import json
import urllib.request
from datetime import datetime, timezone


BASE = "http://127.0.0.1:8765"
DB = "storage/runtime.db"


def get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=5)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def db_tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]


def main():
    print(f"\n{'='*60}")
    print(f"  LIVE MONITOR — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"{'='*60}\n")

    # ── 1. DESK STATUS ──
    ds = get("/api/v1/desk-status")
    fd = ds.get("fast_desk", {})
    smc = ds.get("smc_desk", {})
    print("── DESKS ──────────────────────────")
    print(f"  Fast Desk : {'ACTIVE' if fd.get('enabled') else 'INACTIVE'}  workers={fd.get('workers',0)}")
    fast_cfg = fd.get("config", {})
    print(f"    sessions={fast_cfg.get('allowed_sessions')}  min_conf={fast_cfg.get('min_signal_confidence')}  rr={fast_cfg.get('rr_ratio')}  h1_align={fast_cfg.get('require_h1_alignment')}")
    print(f"  SMC  Desk : {'ACTIVE' if smc.get('enabled') else 'INACTIVE'}  scanner={'ACTIVE' if smc.get('scanner_active') else 'OFF'}")
    smc_cfg = smc.get("config", {})
    print(f"    max_candidates={smc_cfg.get('max_candidates')}  min_rr={smc_cfg.get('min_rr')}  llm={smc_cfg.get('llm_enabled')}\n")

    # ── 2. POSITIONS / ORDERS ──
    pos_data = get("/positions")
    positions = pos_data.get("positions", [])
    orders = pos_data.get("orders", [])
    print("── OPEN POSITIONS ─────────────────")
    if positions:
        for p in positions:
            print(f"  {p.get('symbol')} {p.get('type')} vol={p.get('volume')} open={p.get('price_open')} pl={p.get('profit')}")
    else:
        print("  (none)")
    print("── PENDING ORDERS ─────────────────")
    if orders:
        for o in orders:
            print(f"  {o.get('symbol')} {o.get('type')} vol={o.get('volume')} price={o.get('price_order')}")
    else:
        print("  (none)\n")

    # ── 3. RISK ──
    risk = get("/risk/status")
    rk = risk.get("kernel", risk)
    print("── RISK ────────────────────────────")
    print(f"  kill_switch={'TRIPPED' if rk.get('kill_switch_tripped') else 'off'}  profile_global={rk.get('profile_global')}  fast={rk.get('profile_fast')}  smc={rk.get('profile_smc')}")

    # ── 4. DB TABLES ──
    print("\n── RUNTIME DB ──────────────────────")
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        tables = db_tables(conn)
        for t in tables:
            cnt = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            print(f"  {t}: {cnt} rows")

        # SMC candidates
        if "smc_candidates" in tables:
            print("\n── SMC CANDIDATES (last 10) ────────")
            rows = conn.execute(
                "SELECT symbol, bias, status, candidate_count, created_at "
                "FROM smc_candidates ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            if rows:
                for r in rows:
                    print(f"  {r['created_at'][:19]}  {r['symbol']:8}  bias={r['bias']:8}  status={r['status']:12}  candidates={r['candidate_count']}")
            else:
                print("  (empty)")

        # Fast signals
        for tbl in ["fast_signals", "fast_desk_signals", "fast_trades", "fast_desk_trades"]:
            if tbl in tables:
                print(f"\n── {tbl.upper()} (last 10) ─────────────")
                rows = conn.execute(
                    f"SELECT * FROM \"{tbl}\" ORDER BY rowid DESC LIMIT 10"
                ).fetchall()
                if rows:
                    cols = [d[0] for d in rows[0].description] if hasattr(rows[0], 'description') else rows[0].keys()
                    for r in rows:
                        print("  " + "  ".join(f"{k}={r[k]}" for k in list(cols)[:8]))
                else:
                    print("  (empty)")

        # Fast context (blocking reasons)
        for tbl in ["fast_context_log", "fast_context", "fast_desk_context"]:
            if tbl in tables:
                print(f"\n── {tbl.upper()} (last 10) ─────────────")
                rows = conn.execute(
                    f"SELECT * FROM \"{tbl}\" ORDER BY rowid DESC LIMIT 10"
                ).fetchall()
                if rows:
                    for r in rows:
                        d = dict(r)
                        print(f"  {str(d)[:160]}")
                else:
                    print("  (empty)")

        conn.close()
    except Exception as e:
        print(f"  DB error: {e}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
