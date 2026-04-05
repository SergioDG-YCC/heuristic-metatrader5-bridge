"""Quick diagnostic for SMC Trader pipeline — checks thesis, config, and order flow."""
import sqlite3
import os
import sys
from pathlib import Path

DB = Path("storage/runtime.db")

def main():
    if not DB.exists():
        print("ERROR: runtime.db not found")
        return

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. List tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r["name"] for r in cur.fetchall()]
    print("=== TABLES ===")
    for t in tables:
        print(f"  {t}")
    print()

    # 2. Check for smc_thesis_orders table
    has_thesis_orders = "smc_thesis_orders" in tables
    print(f"smc_thesis_orders table exists: {has_thesis_orders}")

    # 3. Recent SMC theses
    if "smc_theses" in tables:
        cur.execute("SELECT * FROM smc_theses ORDER BY updated_at DESC LIMIT 5")
        rows = cur.fetchall()
        print(f"\n=== RECENT SMC THESES ({len(rows)}) ===")
        for r in rows:
            cols = r.keys()
            print(f"  --- thesis ---")
            for c in cols:
                val = r[c]
                if isinstance(val, str) and len(val) > 200:
                    val = val[:200] + "..."
                print(f"    {c}: {val}")
    else:
        print("\nWARNING: smc_theses table NOT found!")

    # 4. Check smc_thesis_orders
    if has_thesis_orders:
        cur.execute("SELECT COUNT(*) as cnt FROM smc_thesis_orders")
        cnt = cur.fetchone()["cnt"]
        print(f"\n=== SMC THESIS ORDERS: {cnt} rows ===")
        if cnt > 0:
            cur.execute("SELECT * FROM smc_thesis_orders ORDER BY mapped_at DESC LIMIT 5")
            for r in cur.fetchall():
                print(f"  {dict(r)}")

    # 5. Check ownership_registry for smc
    if "ownership_registry" in tables:
        cur.execute("SELECT * FROM ownership_registry WHERE owner='smc' OR desk='smc' ORDER BY registered_at DESC LIMIT 10")
        rows = cur.fetchall()
        print(f"\n=== OWNERSHIP (smc) ({len(rows)}) ===")
        for r in rows:
            print(f"  {dict(r)}")
    else:
        # Try alternate column names
        for t in tables:
            if "ownership" in t.lower():
                cur.execute(f"PRAGMA table_info({t})")
                cols = cur.fetchall()
                print(f"\n  ownership table '{t}' columns: {[c['name'] for c in cols]}")

    # 6. Check env vars
    print("\n=== SMC TRADER ENV VARS ===")
    for key in sorted(os.environ):
        if "SMC_TRADER" in key:
            print(f"  {key}={os.environ[key]}")

    # 7. Check if trader is enabled in config
    enabled = os.getenv("SMC_TRADER_ENABLED", "false")
    print(f"\nSMC_TRADER_ENABLED = {enabled}")

    conn.close()

if __name__ == "__main__":
    main()
