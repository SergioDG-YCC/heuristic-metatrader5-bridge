"""
Fast Desk Diagnostic Script

Run this while the backend is running to diagnose why Fast Desk is not executing.

Usage:
    python scripts/fast_desk_diagnostic.py
"""
import urllib.request
import urllib.error
import json
import sqlite3

BACKEND_URL = "http://localhost:8765"

def get_json(url, timeout=5):
    """Simple HTTP GET with JSON parsing."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

def check_backend_status():
    """Check if backend is running and desks are enabled."""
    print("=" * 60)
    print("FAST DESK DIAGNOSTIC")
    print("=" * 60)
    
    # 1. Check /status
    print("\n1. Checking /status...")
    status = get_json(f"{BACKEND_URL}/status")
    if "error" in status:
        print(f"   ❌ ERROR: {status['error']}")
        return False
    
    print(f"   Status: {status.get('status', 'unknown')}")
    print(f"   Health: {status.get('health', {}).get('status', 'unknown')}")
    print(f"   Indicator: {status.get('indicator_enrichment', {}).get('status', 'unknown')}")
    
    # 2. Check Fast Desk config
    print("\n2. Checking Fast Desk config...")
    config = get_json(f"{BACKEND_URL}/api/v1/config/fast")
    if config.get('status') == 'success':
        cfg = config.get('config', {})
        print(f"   ✅ Config loaded")
        print(f"   - allowed_sessions: {cfg.get('allowed_sessions', [])}")
        print(f"   - spread_tolerance: {cfg.get('spread_tolerance', 'medium')}")
        print(f"   - risk_per_trade_percent: {cfg.get('risk_per_trade_percent', 1.0)}")
        print(f"   - rr_ratio: {cfg.get('rr_ratio', 2.0)}")
        print(f"   - require_h1_alignment: {cfg.get('require_h1_alignment', True)}")
    else:
        print(f"   ❌ Config not available: {config}")
    
    # 3. Check symbol specs
    print("\n3. Checking symbol specs (EURUSD, GBPUSD, USDJPY, BTCUSD)...")
    for symbol in ["EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]:
        spec = get_json(f"{BACKEND_URL}/specs/{symbol}")
        if "error" not in spec:
            print(f"   ✅ {symbol}:")
            print(f"      - digits: {spec.get('digits', 'N/A')}")
            print(f"      - point: {spec.get('point', 'N/A')}")
            print(f"      - tick_value: {spec.get('tick_value', 'N/A')}")
            print(f"      - contract_size: {spec.get('contract_size', 'N/A')}")
        else:
            print(f"   ❌ {symbol}: {spec['error']}")
    
    # 4. Check account state
    print("\n4. Checking account state...")
    account = get_json(f"{BACKEND_URL}/account")
    if "error" not in account:
        acct_state = account.get('account_state', {})
        print(f"   Balance: ${acct_state.get('balance', 0):,.2f}")
        print(f"   Equity: ${acct_state.get('equity', 0):,.2f}")
        print(f"   Free Margin: ${acct_state.get('free_margin', 0):,.2f}")
        print(f"   Leverage: {acct_state.get('leverage', 'N/A')}")
    else:
        print(f"   ❌ ERROR: {account['error']}")
    
    # 5. Check Risk Kernel status
    print("\n5. Checking Risk Kernel...")
    risk = get_json(f"{BACKEND_URL}/api/v1/config/risk")
    if risk.get('status') == 'success':
        cfg = risk.get('config', {})
        print(f"   ✅ Risk config loaded")
        print(f"   - profile_global: {cfg.get('profile_global', 'N/A')}")
        print(f"   - profile_fast: {cfg.get('profile_fast', 'N/A')}")
        print(f"   - fast_budget_weight: {cfg.get('fast_budget_weight', 'N/A')}")
        print(f"   - kill_switch_enabled: {cfg.get('kill_switch_enabled', 'N/A')}")
    else:
        print(f"   ❌ Risk config not available: {risk}")
    
    # 6. Check DB for signals
    print("\n6. Checking DB for fast_desk_signals...")
    try:
        db_path = "storage/runtime.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Count signals
        cursor.execute("SELECT COUNT(*) FROM fast_desk_signals")
        count = cursor.fetchone()[0]
        print(f"   Total signals in DB: {count}")
        
        # Last 5 signals
        cursor.execute("""
            SELECT symbol, side, trigger, outcome, processed_at, evidence_json
            FROM fast_desk_signals
            ORDER BY processed_at DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
        if rows:
            print(f"   Last 5 signals:")
            for row in rows:
                symbol, side, trigger, outcome, processed_at, evidence = row
                print(f"   - {symbol} {side} | {trigger} | {outcome} | {processed_at}")
                
                # Parse evidence for debugging
                if evidence:
                    try:
                        ev = json.loads(evidence)
                        print(f"      - pip_value_used: {ev.get('pip_value_used', 'N/A')}")
                        print(f"      - exec_result: {ev.get('exec_result', {})}")
                    except:
                        pass
        else:
            print(f"   ❌ NO SIGNALS IN DB - Fast Desk is not detecting setups")
        
        conn.close()
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nCRITICAL FINDINGS:")
    print("1. If indicator=waiting_first_snapshot → EA no está enviando indicadores")
    print("2. If NO SIGNALS IN DB → Fast Desk no detecta setups")
    print("\nNEXT STEPS:")
    print("1. Verificar que el EA esté corriendo en MT5")
    print("2. Verificar que el EA esté enviando snapshots")
    print("3. Revisar logs del backend por 'spread_exceeded', 'session_blocked', etc")

if __name__ == "__main__":
    check_backend_status()
