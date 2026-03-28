"""Quick DB diagnostic — safe for PowerShell (no f-string backslash)."""
import json
import sqlite3
from pathlib import Path

DB = Path("storage/runtime.db")
con = sqlite3.connect(str(DB), timeout=5)
con.row_factory = sqlite3.Row

def count(table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

print("=== DB state ===")
for tbl in ["fast_desk_signals", "fast_desk_trade_log", "smc_thesis_cache", "smc_events_log", "risk_events_log"]:
    print(f"  {tbl}: {count(tbl)} rows")

print("\n=== fast_desk_signals (last 10) ===")
rows = con.execute(
    "SELECT symbol, side, outcome, trigger, stop_loss_pips, evidence_json, generated_at "
    "FROM fast_desk_signals ORDER BY generated_at DESC LIMIT 10"
).fetchall()
for r in rows:
    ev = {}
    try:
        ev = json.loads(r["evidence_json"]) if r["evidence_json"] else {}
    except Exception:
        pass
    lots = ev.get("volume_lots", "?")
    pip_val = ev.get("pip_value_used", "?")
    exec_res = ev.get("exec_result", {})
    err = exec_res.get("error", "") if isinstance(exec_res, dict) else ""
    ok = exec_res.get("ok", "?") if isinstance(exec_res, dict) else "?"
    print(f"  {r['generated_at']} | {r['symbol']} {r['side']} | outcome={r['outcome']} | lots={lots} | pip_val={pip_val} | ok={ok} | err={err[:80]}")

if not rows:
    print("  (no rows)")

print("\n=== smc_thesis_cache ===")
rows2 = con.execute("SELECT symbol, bias, candidate_count_out, status FROM smc_thesis_cache").fetchall()
for r in rows2:
    print(f"  {r['symbol']} bias={r['bias']} candidates={r['candidate_count_out']} status={r['status']}")

print("\n=== risk_events_log (last 5) ===")
rows3 = con.execute("SELECT event_type, details_json, recorded_at FROM risk_events_log ORDER BY recorded_at DESC LIMIT 5").fetchall()
for r in rows3:
    print(f"  {r['recorded_at']} {r['event_type']}")

con.close()
