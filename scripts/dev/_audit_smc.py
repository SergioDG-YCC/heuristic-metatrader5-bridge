"""Audit script: dump SMC thesis, orders, positions and ownership for review."""
import sqlite3
import json
from pathlib import Path

DB = Path("storage/runtime.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row


def j(val):
    try:
        return json.loads(val or "[]")
    except Exception:
        return val


# ─── THESIS ────────────────────────────────────────────────────────────────
print("\n" + "="*80)
print("SMC THESIS")
print("="*80)
rows = conn.execute(
    "SELECT symbol, bias, status, validator_decision, "
    "operation_candidates_json, last_review_at, next_review_not_before "
    "FROM smc_thesis_cache ORDER BY last_review_at DESC"
).fetchall()
for r in rows:
    cands = j(r["operation_candidates_json"])
    c0 = cands[0] if cands else {}
    print(f"\n  SYMBOL : {r['symbol']}")
    print(f"  BIAS   : {r['bias']}  STATUS: {r['status']}  VALIDATOR: {r['validator_decision']}")
    print(f"  REVIEW : last={r['last_review_at']}  next_not_before={r['next_review_not_before']}")
    if c0:
        print(f"  CAND   : side={c0.get('side')}  quality={c0.get('quality')}")
        print(f"           entry_low={c0.get('entry_zone_low')}  entry_high={c0.get('entry_zone_high')}")
        print(f"           sl={c0.get('stop_loss')}  tp1={c0.get('take_profit_1')}  tp2={c0.get('take_profit_2')}")
        print(f"           rr={c0.get('rr_ratio')}  entry_model={c0.get('entry_model')}")
    else:
        print("  CAND   : NONE")

# ─── SMC ORDER OWNERSHIP ───────────────────────────────────────────────────
print("\n" + "="*80)
print("OPERATION OWNERSHIP (SMC active)")
print("="*80)
own_rows = conn.execute(
    "SELECT operation_uid, operation_type, lifecycle_status, desk_owner, "
    "mt5_order_id, mt5_position_id, metadata_json, created_at, updated_at "
    "FROM operation_ownership WHERE lifecycle_status='active' ORDER BY created_at DESC"
).fetchall()
if not own_rows:
    print("  (no active SMC operations in ownership table)")
for r in own_rows:
    meta = j(r['metadata_json'])
    print(f"\n  [{r['operation_type'].upper()}] uid={r['operation_uid']}  desk={r['desk_owner']}")
    print(f"  order_id={r['mt5_order_id']}  pos_id={r['mt5_position_id']}  lifecycle={r['lifecycle_status']}")
    print(f"  meta={meta}")
    print(f"  created={r['created_at']}  updated={r['updated_at']}")

# ─── LIVE ORDER CACHE ─────────────────────────────────────────────────────
print("\n" + "="*80)
print("ORDER CACHE (pending orders live from MT5)")
print("="*80)
try:
    ord_rows = conn.execute(
        "SELECT order_id, symbol, order_type, volume_initial, volume_current, "
        "price_open, stop_loss, take_profit, comment, status, created_at, updated_at, order_payload_json "
        "FROM order_cache ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    if not ord_rows:
        print("  (no pending orders in order_cache)")
    for r in ord_rows:
        pay = j(r['order_payload_json'])
        print(f"\n  order_id={r['order_id']}  {r['symbol']}  type={r['order_type']}  status={r['status']}")
        print(f"  price_open={r['price_open']}  sl={r['stop_loss']}  tp={r['take_profit']}  vol={r['volume_current']}")
        print(f"  created={r['created_at']}  updated={r['updated_at']}  comment={r['comment']}")
        print(f"  payload={pay}")
except Exception as e:
    print(f"  ERROR: {e}")

# ─── LIVE POSITION CACHE ──────────────────────────────────────────────────
print("\n" + "="*80)
print("POSITION CACHE (open positions live from MT5)")
print("="*80)
try:
    pos_rows = conn.execute(
        "SELECT position_id, symbol, side, volume, price_open, price_current, "
        "stop_loss, take_profit, profit, comment, status, opened_at, updated_at, position_payload_json "
        "FROM position_cache ORDER BY opened_at DESC LIMIT 20"
    ).fetchall()
    if not pos_rows:
        print("  (no open positions in position_cache)")
    for r in pos_rows:
        pay = j(r['position_payload_json'])
        print(f"\n  pos_id={r['position_id']}  {r['symbol']} {r['side']}  status={r['status']}")
        print(f"  open={r['price_open']}  current={r['price_current']}  sl={r['stop_loss']}  tp={r['take_profit']}  vol={r['volume']}")
        print(f"  profit={r['profit']}  opened={r['opened_at']}  updated={r['updated_at']}  comment={r['comment']}")
        if pay and isinstance(pay, dict):
            print(f"  payload_keys={list(pay.keys())}")
except Exception as e:
    print(f"  ERROR: {e}")

# ─── EXECUTION EVENTS (recent) ────────────────────────────────────────────
print("\n" + "="*80)
print("EXECUTION EVENTS (last 30)")
print("="*80)
try:
    ev_rows = conn.execute(
        "SELECT symbol, event_type, status, mt5_order_id, mt5_position_id, "
        "price, volume, reason, created_at, execution_event_payload_json "
        "FROM execution_event_cache ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    if not ev_rows:
        print("  (no execution events)")
    for r in ev_rows:
        pay = j(r['execution_event_payload_json'])
        print(f"  {r['created_at']}  [{r['event_type']}]  {r['symbol']}  order={r['mt5_order_id']}  pos={r['mt5_position_id']}  price={r['price']}  vol={r['volume']}  status={r['status']}  reason={r['reason']}")
except Exception as e:
    print(f"  ERROR: {e}")

# ─── SMC THESIS ORDERS (internal ownership log) ───────────────────────────
print("\n" + "="*80)
print("SMC_THESIS_ORDERS (last 20)")
print("="*80)
try:
    to_rows = conn.execute(
        "SELECT * FROM smc_thesis_orders ORDER BY rowid DESC LIMIT 20"
    ).fetchall()
    if not to_rows:
        print("  (empty)")
    for r in to_rows:
        print(dict(r))
except Exception as e:
    print(f"  ERROR: {e}")

# ─── POSITION vs THESIS ZONE COMPARISON ─────────────────────────────────
print()
print('='*80)
print('POSITION OPEN PRICE vs CURRENT THESIS ENTRY ZONE')
print('='*80)
pos_all = conn.execute(
    'SELECT position_id, symbol, side, price_open, stop_loss, take_profit, '
    'profit, opened_at, comment FROM position_cache ORDER BY opened_at DESC'
).fetchall()
for p in pos_all:
    sym = p['symbol']
    thesis_row = conn.execute(
        'SELECT bias, status, operation_candidates_json FROM smc_thesis_cache '
        'WHERE symbol=? ORDER BY last_review_at DESC LIMIT 1', (sym,)
    ).fetchone()
    cands = j(thesis_row['operation_candidates_json']) if thesis_row else []
    c0 = cands[0] if cands else {}
    entry_low = c0.get('entry_zone_low', '?')
    entry_high = c0.get('entry_zone_high', '?')
    rr = c0.get('rr_ratio', '?')
    if entry_low != '?' and entry_high != '?' and entry_low:
        mid = round((float(entry_low) + float(entry_high)) / 2, 6)
        delta = round(abs(p['price_open'] - mid), 6)
    else:
        mid = '?'
        delta = '?'
    print()
    print(f'  {p["opened_at"]} | {sym} {p["side"]}')
    print(f'  open={p["price_open"]}  thesis_zone=[{entry_low} - {entry_high}]  mid={mid}  delta={delta}')
    print(f'  sl={p["stop_loss"]}  tp={p["take_profit"]}  profit={p["profit"]}  comment={p["comment"]}')

# ─── OWNERSHIP EVENTS ────────────────────────────────────────────────────
print()
print('='*80)
print('OPERATION OWNERSHIP EVENTS (last 50)')
print('='*80)
try:
    cols = conn.execute('PRAGMA table_info(operation_ownership_events)').fetchall()
    print('Columns:', [c[1] for c in cols])
    evs = conn.execute('SELECT * FROM operation_ownership_events ORDER BY rowid DESC LIMIT 50').fetchall()
    for e in evs:
        print(dict(e))
except Exception as ex:
    print('ERROR:', ex)

# ─── THESIS HISTORY for active positions ─────────────────────────────────
print()
print('='*80)
print('ALL THESIS VERSIONS per position symbol (USDCHF, CHFJPY, AUDNZD, USDCAD, EURGBP)')
print('='*80)
for sym in ('USDCHF', 'CHFJPY', 'AUDNZD', 'USDCAD', 'EURGBP'):
    rows2 = conn.execute(
        'SELECT bias, status, validator_decision, operation_candidates_json, '
        'last_review_at, next_review_not_before '
        'FROM smc_thesis_cache WHERE symbol=? ORDER BY last_review_at ASC', (sym,)
    ).fetchall()
    print(f'\n  --- {sym} ({len(rows2)} thesis records) ---')
    for r in rows2:
        cands = j(r['operation_candidates_json'])
        c0 = cands[0] if cands else {}
        if c0:
            ezl = c0.get('entry_zone_low', '?')
            ezh = c0.get('entry_zone_high', '?')
            side = c0.get('side', '?')
            print(f'    {r["last_review_at"]} bias={r["bias"]} status={r["status"]} val={r["validator_decision"]} cand={side} zone=[{ezl}-{ezh}]')
        else:
            print(f'    {r["last_review_at"]} bias={r["bias"]} status={r["status"]} val={r["validator_decision"]} NO_CANDIDATES')


# ─── ORDER_CACHE HISTORY ────────────────────────────────────────────────────
print()
print('='*80)
print('ORDER_CACHE HISTORY (all orders)')
print('='*80)
ord_all = conn.execute(
    'SELECT order_id, symbol, order_type, price_open, stop_loss, take_profit, '
    'status, comment, created_at, updated_at FROM order_cache ORDER BY created_at DESC LIMIT 40'
).fetchall()
if not ord_all:
    print('  (empty)')
for r in ord_all:
    print(f'  {r["created_at"]} {r["symbol"]} type={r["order_type"]} price={r["price_open"]} sl={r["stop_loss"]} tp={r["take_profit"]} status={r["status"]} comment={r["comment"]}')

conn.close()
