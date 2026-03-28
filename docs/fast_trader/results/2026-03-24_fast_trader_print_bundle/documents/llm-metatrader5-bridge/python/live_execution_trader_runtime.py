from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_models import load_env_file, resolve_agent_models
from analysis_input_builder import build_analysis_input_from_runtime, build_analysis_query
from llm_metrics_runtime import begin_llm_request, finish_llm_request, record_llm_fallback
from message_utils import persist_message
from mt5_connector import CFG as MT5_CFG
from mt5_connector import MT5Connector
from prompt_loader import load_prompt
from runtime_db import ensure_runtime_db, runtime_db_connection, runtime_db_path, upsert_live_operation_action_cache, upsert_live_operation_review_cache, upsert_symbol_outlook_cache
from thesis_runtime import load_recent_thesis
from trading_universe import is_operable_symbol
from llm_request_gate import acquire_llm_slot, release_llm_slot

try:
    from main_desk_session_gate import get_main_desk_session_gate as _get_main_desk_gate
except ImportError:
    _get_main_desk_gate = None  # type: ignore

_last_position_eval: dict[int, dict[str, Any]] = {}  # ticket → last eval state


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BCHUSD", "BTCEUR", "ETHEUR"}


def _is_crypto(symbol: str) -> bool:
    return symbol.strip().upper() in _CRYPTO_SYMBOLS


def config() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    env_values = load_env_file(repo_root / ".env")
    models = resolve_agent_models(repo_root)
    localai_base_url = os.getenv("LOCALAI_BASE_URL", env_values.get("LOCALAI_BASE_URL", "http://127.0.0.1:8080")).rstrip("/")
    timeout_seconds = float(os.getenv("LOCALAI_TIMEOUT_SECONDS", env_values.get("LOCALAI_TIMEOUT_SECONDS", "20")))
    configured_storage = Path(os.getenv("STORAGE_ROOT", env_values.get("STORAGE_ROOT", str(repo_root / "python" / "storage"))))
    storage_root = configured_storage if configured_storage.is_absolute() else repo_root / configured_storage
    watch_timeframes = [item.strip().upper() for item in os.getenv("MT5_WATCH_TIMEFRAMES", env_values.get("MT5_WATCH_TIMEFRAMES", "M5,H1")).split(",") if item.strip()]
    return {
        "repo_root": repo_root,
        "storage_root": storage_root,
        "runtime_db_path": runtime_db_path(
            storage_root,
            os.getenv("RUNTIME_DB_PATH", env_values.get("RUNTIME_DB_PATH")),
        ),
        "watch_timeframes": watch_timeframes or ["M5", "H1"],
        "poll_seconds": float(os.getenv("LIVE_EXECUTION_TRADER_POLL_SECONDS", env_values.get("LIVE_EXECUTION_TRADER_POLL_SECONDS", "20"))),
        "max_pairs_per_cycle": int(os.getenv("LIVE_EXECUTION_TRADER_MAX_PAIRS_PER_CYCLE", env_values.get("LIVE_EXECUTION_TRADER_MAX_PAIRS_PER_CYCLE", "12"))),
        "emit_min_interval_seconds": int(os.getenv("LIVE_EXECUTION_TRADER_EMIT_MIN_INTERVAL_SECONDS", env_values.get("LIVE_EXECUTION_TRADER_EMIT_MIN_INTERVAL_SECONDS", "180"))),
        "stale_order_seconds": int(os.getenv("LIVE_EXECUTION_TRADER_STALE_ORDER_SECONDS", env_values.get("LIVE_EXECUTION_TRADER_STALE_ORDER_SECONDS", "1200"))),
        "auto_execute": os.getenv("LIVE_EXECUTION_TRADER_AUTO_EXECUTE", env_values.get("LIVE_EXECUTION_TRADER_AUTO_EXECUTE", "true")).strip().lower() in {"1", "true", "yes", "on"},
        "live_execution_trader_model": models["live_execution_trader"],
        "localai_base_url": localai_base_url,
        "timeout_seconds": timeout_seconds,
    }


CFG = config()
ensure_runtime_db(CFG["runtime_db_path"])


def decode_json_text(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def list_live_symbols() -> list[str]:
    if not CFG["runtime_db_path"].exists():
        return []
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        rows = conn.execute(
            """
            SELECT symbol
            FROM (
                SELECT symbol, updated_at AS ts FROM position_cache
                UNION ALL
                SELECT symbol, updated_at AS ts FROM order_cache
            )
            WHERE COALESCE(symbol, '') <> ''
            ORDER BY ts DESC
            """
        ).fetchall()
    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row[0] or "").strip().upper()
        if not symbol or symbol in seen or not is_operable_symbol(symbol):
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def list_review_pairs(limit: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for symbol in list_live_symbols():
        thesis_timeframes = [tf for tf in CFG["watch_timeframes"] if load_recent_thesis(symbol, tf)]
        candidate_timeframes = thesis_timeframes or CFG["watch_timeframes"][:1]
        for timeframe in candidate_timeframes:
            pair = (symbol, timeframe)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
            if len(pairs) >= limit:
                return pairs
    return pairs


def latest_review_row(review_key: str) -> dict[str, Any] | None:
    if not CFG["runtime_db_path"].exists():
        return None
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT review_id, source_signature, updated_at, payload_json
            FROM live_operation_review_cache
            WHERE review_key = ?
            LIMIT 1
            """,
            (review_key,),
        ).fetchone()
    return dict(row) if row else None


def iso_to_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def build_source_signature(symbol: str, timeframe: str, thesis: dict[str, Any] | None, live_operations: dict[str, Any], risk_context: dict[str, Any]) -> str:
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "thesis_id": str((thesis or {}).get("thesis_id", "")),
        "thesis_status": str((thesis or {}).get("status", "")),
        "kill_switch_state": str(((risk_context.get("latest_risk_review") or {}) if isinstance(risk_context, dict) else {}).get("kill_switch_state", "")),
        "positions": [
            {
                "position_id": item.get("position_id"),
                "stop_loss": item.get("stop_loss"),
                "take_profit": item.get("take_profit"),
                "profit": item.get("profit"),
                "updated_at": item.get("updated_at"),
                "ownership_status": ((item.get("operation_origin") or {}).get("ownership_status") if isinstance(item, dict) else ""),
            }
            for item in (live_operations.get("open_positions") if isinstance(live_operations.get("open_positions"), list) else [])
            if isinstance(item, dict)
        ],
        "orders": [
            {
                "order_id": item.get("order_id"),
                "price_open": item.get("price_open"),
                "stop_loss": item.get("stop_loss"),
                "take_profit": item.get("take_profit"),
                "updated_at": item.get("updated_at"),
                "status": item.get("status"),
                "ownership_status": ((item.get("operation_origin") or {}).get("ownership_status") if isinstance(item, dict) else ""),
            }
            for item in (live_operations.get("pending_orders") if isinstance(live_operations.get("pending_orders"), list) else [])
            if isinstance(item, dict)
        ],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _should_reevaluate_position(ticket: int, position: dict[str, Any],
                                market_price: float, equity: float) -> tuple[bool, str]:
    """Heuristic gate: re-evaluate only if something material changed.

    Scalping-aware: positions < 30min get tighter thresholds.
    """
    import time as _time
    last = _last_position_eval.get(ticket)
    if last is None:
        return True, "first_eval"

    sl = float(position.get("stop_loss", 0) or 0)
    tp = float(position.get("take_profit", 0) or 0)
    entry = float(position.get("price_open", market_price) or market_price)

    # Determine if this is a scalping position (< 30 min old)
    opened_at = str(position.get("time_open", "") or position.get("opened_at", "") or "").strip()
    position_age_s = 9999.0  # Default: treat as non-scalp
    if opened_at:
        try:
            open_ts = datetime.fromisoformat(opened_at.replace("Z", "+00:00")).timestamp()
            position_age_s = _time.time() - open_ts
        except Exception:
            pass

    is_scalp = position_age_s < 1800  # < 30 minutes

    # Adaptive thresholds
    if is_scalp:
        stale_max = 60       # 1 min for scalps (was 900s)
        pnl_shift_threshold = 0.3  # 0.3% equity (was 1.0%)
    else:
        stale_max = 300      # 5 min for intraday (was 900s)
        pnl_shift_threshold = 0.5  # 0.5% equity (was 1.0%)

    # Approaching SL (within 30% of remaining distance)
    if sl and abs(entry - sl) > 0:
        sl_proximity = abs(market_price - sl) / abs(entry - sl)
        if sl_proximity < 0.30:
            return True, f"approaching_sl={sl_proximity:.0%}"

    # Approaching TP (within 30% of remaining distance)
    if tp and abs(entry - tp) > 0:
        tp_proximity = abs(market_price - tp) / abs(entry - tp)
        if tp_proximity < 0.30:
            return True, f"approaching_tp={tp_proximity:.0%}"

    # PnL shift
    last_pnl_pct = float(last.get("profit_pct", 0))
    curr_pnl_pct = float(position.get("profit", 0) or 0) / max(1.0, equity) * 100
    if abs(curr_pnl_pct - last_pnl_pct) > pnl_shift_threshold:
        return True, f"pnl_shift={last_pnl_pct:.1f}%->{curr_pnl_pct:.1f}%"

    # Stale safety net
    age = _time.time() - last.get("ts", 0)
    if age > stale_max:
        return True, f"stale={age:.0f}s(max={stale_max})"

    return False, "position_within_parameters"


def _record_position_eval(ticket: int, position: dict[str, Any],
                          equity: float) -> None:
    """Registra el estado de la posición tras evaluarla."""
    import time as _time
    _last_position_eval[ticket] = {
        "profit_pct": float(position.get("profit", 0) or 0) / max(1.0, equity) * 100,
        "ts": _time.time(),
    }


def _load_market_context(symbol: str, timeframe: str) -> dict[str, Any]:
    """Carga chart context completo del runtime para darle visión de mercado al live trader."""
    try:
        query = build_analysis_query(
            symbol=symbol,
            timeframe=timeframe,
            requested_blocks=[
                "state_summary", "structure", "session",
                "indicator_enrichment", "account_state",
            ],
            reason="live_execution_trader_market_vision",
            requested_by_role="trader",
            depth="compact",
        )
        analysis_input = build_analysis_input_from_runtime(query)
        resolved = analysis_input.get("resolved_blocks") if isinstance(analysis_input.get("resolved_blocks"), dict) else {}
        return {
            "state_summary": resolved.get("state_summary") if isinstance(resolved.get("state_summary"), dict) else None,
            "structure": resolved.get("structure") if isinstance(resolved.get("structure"), dict) else None,
            "session": resolved.get("session") if isinstance(resolved.get("session"), dict) else None,
            "indicator_enrichment": resolved.get("indicator_enrichment") if isinstance(resolved.get("indicator_enrichment"), dict) else None,
            "account_state": resolved.get("account_state") if isinstance(resolved.get("account_state"), dict) else None,
        }
    except Exception:
        return {}


def classify_review_context(symbol: str, timeframe: str) -> dict[str, Any] | None:
    """Clasifica contexto de revisión para un par con exposición viva."""
    thesis = load_recent_thesis(symbol, timeframe)
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        pos_rows = conn.execute(
            "SELECT position_payload_json FROM position_cache "
            "WHERE symbol = ? AND status = 'open'",
            (symbol.upper(),),
        ).fetchall()
        ord_rows = conn.execute(
            "SELECT order_payload_json FROM order_cache "
            "WHERE symbol = ? AND status IN ('placed', 'working')",
            (symbol.upper(),),
        ).fetchall()
    positions = [decode_json_text(r[0], {}) for r in pos_rows if r[0]]
    orders = [decode_json_text(r[0], {}) for r in ord_rows if r[0]]
    if not positions and not orders:
        return None
    unprotected_positions = [
        p for p in positions
        if float(p.get("stop_loss", 0) or 0) <= 0
        or float(p.get("take_profit", 0) or 0) <= 0
    ]
    unprotected_orders = [
        o for o in orders
        if float(o.get("stop_loss", 0) or 0) <= 0
        or float(o.get("take_profit", 0) or 0) <= 0
    ]
    stale_orders = [
        o for o in orders
        if CFG["stale_order_seconds"] > 0
        and (time.time() - iso_to_ts(str(o.get("updated_at", "")))) > CFG["stale_order_seconds"]
    ]
    kill_switch_state = "armed"
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT risk_review_payload_json FROM risk_review_cache "
            "WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if row:
            risk_review = decode_json_text(row[0], {})
            kill_switch_state = str(risk_review.get("kill_switch_state", "armed")).strip().lower()
    market_context = _load_market_context(symbol, timeframe)
    return {
        "positions": positions,
        "orders": orders,
        "thesis": thesis,
        "unprotected_positions": unprotected_positions,
        "unprotected_orders": unprotected_orders,
        "stale_orders": stale_orders,
        "kill_switch_state": kill_switch_state,
        "market_context": market_context,
    }


def build_review(symbol: str, timeframe: str) -> dict[str, Any] | None:
    thesis = load_recent_thesis(symbol, timeframe)
    query = build_analysis_query(
        symbol=symbol,
        timeframe=timeframe,
        requested_blocks=[
            "live_operations",
            "risk_context",
        ],
        reason="live_execution_trader_review",
        requested_by_role="trader",
        thesis_id=str((thesis or {}).get("thesis_id", "")),
        depth="compact",
    )
    analysis_input = build_analysis_input_from_runtime(query)
    resolved = analysis_input.get("resolved_blocks") if isinstance(analysis_input.get("resolved_blocks"), dict) else {}
    live_operations = resolved.get("live_operations") if isinstance(resolved.get("live_operations"), dict) else {}
    risk_context = resolved.get("risk_context") if isinstance(resolved.get("risk_context"), dict) else {}
    if not live_operations:
        return None

    positions = [item for item in (live_operations.get("open_positions") or []) if isinstance(item, dict)]
    orders = [item for item in (live_operations.get("pending_orders") or []) if isinstance(item, dict)]
    if not positions and not orders:
        return None

    ownership_summary = live_operations.get("ownership_summary") if isinstance(live_operations.get("ownership_summary"), dict) else {}
    latest_review = risk_context.get("latest_risk_review") if isinstance(risk_context.get("latest_risk_review"), dict) else {}
    kill_switch_state = str(latest_review.get("kill_switch_state", "armed")).strip().lower()
    unprotected_positions = [
        item for item in positions
        if float(item.get("stop_loss", 0) or 0) <= 0 or float(item.get("take_profit", 0) or 0) <= 0
    ]
    unprotected_orders = [
        item for item in orders
        if float(item.get("stop_loss", 0) or 0) <= 0 or float(item.get("take_profit", 0) or 0) <= 0
    ]
    stale_orders = [
        item for item in orders
        if CFG["stale_order_seconds"] > 0 and (time.time() - iso_to_ts(str(item.get("updated_at", "")).strip())) > CFG["stale_order_seconds"]
    ]
    inherited_positions = int(ownership_summary.get("inherited_position_count", 0) or 0)
    inherited_orders = int(ownership_summary.get("inherited_order_count", 0) or 0)

    operation_scope = "mixed" if positions and orders else "positions" if positions else "orders"
    if unprotected_positions or unprotected_orders:
        action = "add_protection"
        urgency = "urgent"
        message_type = "protective_update"
        display_text = (
            f"Live {symbol}/{timeframe} exposure is missing protection. "
            f"{len(unprotected_positions)} position(s) and {len(unprotected_orders)} pending order(s) need immediate SL/TP review."
        )
    elif kill_switch_state == "tripped":
        action = "reduce_or_close"
        urgency = "high"
        message_type = "position_review" if positions else "order_review"
        display_text = (
            f"Risk kill-switch is tripped while {symbol}/{timeframe} still has live exposure. "
            "Trader must reduce, cancel, or exit deliberately instead of going passive."
        )
    elif stale_orders:
        action = "cancel_or_replace_stale_orders"
        urgency = "high"
        message_type = "order_review"
        display_text = f"{symbol}/{timeframe} has {len(stale_orders)} stale pending order(s) that require cancellation or replacement review."
    elif inherited_positions or inherited_orders:
        action = "assume_and_manage"
        urgency = "high"
        message_type = "position_review" if positions else "order_review"
        display_text = (
            f"{symbol}/{timeframe} still carries inherited live exposure. "
            "Trader must adopt ownership and define maintenance, tightening, or exit."
        )
    else:
        action = "maintain_and_monitor"
        urgency = "normal"
        message_type = "position_review" if positions else "order_review"
        display_text = f"Trader reviewed live {symbol}/{timeframe} exposure and must keep monitoring structure, protection, and pending order quality."

    review_id = f"live_review_{uuid.uuid4().hex}"
    review_key = f"{symbol}:{timeframe}:live_execution"
    source_signature = build_source_signature(symbol, timeframe, thesis, live_operations, risk_context)
    payload = {
        "review_id": review_id,
        "review_key": review_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "operation_scope": operation_scope,
        "action": action,
        "urgency": urgency,
        "linked_thesis_id": str((thesis or {}).get("thesis_id", "")).strip() or None,
        "source_signature": source_signature,
        "display_text": display_text,
        "message": display_text,
        "summary": display_text,
        "position_count": len(positions),
        "pending_order_count": len(orders),
        "unprotected_position_count": len(unprotected_positions),
        "unprotected_order_count": len(unprotected_orders),
        "stale_order_count": len(stale_orders),
        "kill_switch_state": kill_switch_state,
        "ownership_summary": ownership_summary,
        "analysis_input_query_id": str(analysis_input.get("analysis_input_id", "")).strip(),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "message_type": message_type,
    }
    return payload


def should_emit_review(review: dict[str, Any]) -> bool:
    existing = latest_review_row(str(review.get("review_key", "")))
    if not existing:
        return True
    if str(existing.get("source_signature", "")).strip() != str(review.get("source_signature", "")).strip():
        return True
    last_updated = iso_to_ts(str(existing.get("updated_at", "")).strip())
    return (time.time() - last_updated) >= CFG["emit_min_interval_seconds"]


def build_default_protection(position: dict[str, Any], thesis: dict[str, Any] | None) -> tuple[float | None, float | None]:
    side = str(position.get("side", "")).strip().lower()
    entry = float(position.get("price_open", 0.0) or 0.0)
    current = float(position.get("price_current", 0.0) or 0.0)
    base_price = current if current > 0 else entry
    if base_price <= 0 or side not in {"buy", "sell"}:
        return None, None
    watch_levels = (thesis or {}).get("watch_levels") if isinstance((thesis or {}).get("watch_levels"), list) else []
    watch_prices = [float(item.get("price", 0.0)) for item in watch_levels if isinstance(item, dict) and isinstance(item.get("price"), (int, float)) and float(item.get("price")) > 0]
    fallback_distance = max(base_price * 0.0030, 0.0001) if _is_crypto(str(position.get("symbol", ""))) else max(base_price * 0.0015, 0.0001)
    if side == "buy":
        stop = next((price for price in watch_prices if 0 < price < base_price), 0.0) or (entry - fallback_distance if entry > 0 else base_price - fallback_distance)
        risk_distance = max(base_price - stop, fallback_distance)
        target = base_price + (risk_distance * 4.0)
    else:
        stop = next((price for price in watch_prices if price > base_price), 0.0) or (entry + fallback_distance if entry > 0 else base_price + fallback_distance)
        risk_distance = max(stop - base_price, fallback_distance)
        target = base_price - (risk_distance * 4.0)
    return float(stop), float(target)


def build_trailing_payload(position: dict[str, Any],
                           atr_value: float | None = None) -> dict[str, Any] | None:
    entry = float(position.get("price_open", 0.0) or 0.0)
    current = float(position.get("price_current", 0.0) or 0.0)
    if entry <= 0 or current <= 0:
        return None
    # ATR-calibrated distance if available, else fallback to fixed
    if atr_value and atr_value > 0:
        distance = atr_value * 1.5
        step_val = atr_value * 0.5
    else:
        distance = max(entry * 0.0025, 0.0001)
        step_val = distance * 0.5
    return {
        "enabled": True,
        "activation_price": current,
        "distance": distance,
        "step": step_val,
    }


# ---------------------------------------------------------------------------
# Post-LLM enforcement: hard overrides that apply AFTER any LLM/heuristic
# ---------------------------------------------------------------------------

MAX_LOSS_PCT = 0.015  # 1.5% of entry price → forced close

# --- CAPA 1 Heuristic Layer Configuration ---
# Risk posture → max loss per-position (replaces fixed MAX_LOSS_PCT)
_RISK_POSTURE_LOSS_PCT: dict[str, float] = {
    "low": 0.008,     # 0.8%
    "medium": 0.012,   # 1.2%
    "high": 0.015,     # 1.5%
    "chaos": 0.025,    # 2.5%
}

# Risk posture → max equity drawdown (from .env RISK_{POSTURE}_MAX_DRAWDOWN_PERCENT)
_RISK_POSTURE_MAX_DD: dict[str, float] = {
    "low": 0.02,
    "medium": 0.035,
    "high": 0.05,
    "chaos": 0.15,
}


def _get_risk_posture() -> str:
    """Read current executive risk posture from .env."""
    repo_root = Path(__file__).resolve().parents[1]
    env_values = load_env_file(repo_root / ".env")
    return str(os.getenv("EXECUTIVE_RISK_POSTURE",
                         env_values.get("EXECUTIVE_RISK_POSTURE", "medium"))).strip().lower()


def _load_account_state() -> dict[str, Any]:
    """Read latest account state (balance, equity) from runtime DB."""
    if not CFG["runtime_db_path"].exists():
        return {}
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT account_payload_json FROM account_state_cache "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {}
    return decode_json_text(row[0], {})


def _load_m5_candles(symbol: str) -> list[dict[str, Any]]:
    """Load recent M5 candles from the persisted market state for reversal detection.

    Returns list of dicts with keys: open, high, low, close, timestamp.
    Ordered oldest → newest. Returns [] if unavailable.
    """
    try:
        query = build_analysis_query(
            symbol=symbol,
            timeframe="M5",
            requested_blocks=["state_summary"],
            reason="heuristic_m5_candles",
            requested_by_role="trader",
            depth="compact",
        )
        analysis_input = build_analysis_input_from_runtime(query)
        resolved = analysis_input.get("resolved_blocks") if isinstance(analysis_input.get("resolved_blocks"), dict) else {}
        state_summary = resolved.get("state_summary") if isinstance(resolved.get("state_summary"), dict) else {}
        # The state_summary contains recent_bars from the market_state chart context
        recent_bars = state_summary.get("recent_bars")
        if isinstance(recent_bars, list) and len(recent_bars) >= 2:
            return recent_bars
        return []
    except Exception:
        return []


def _load_indicator_values(symbol: str, timeframe: str) -> dict[str, Any]:
    """Load indicator enrichment values (ATR_14, RSI_14, etc.) from market context."""
    try:
        query = build_analysis_query(
            symbol=symbol,
            timeframe=timeframe,
            requested_blocks=["indicator_enrichment"],
            reason="heuristic_indicators",
            requested_by_role="trader",
            depth="compact",
        )
        analysis_input = build_analysis_input_from_runtime(query)
        resolved = analysis_input.get("resolved_blocks") if isinstance(analysis_input.get("resolved_blocks"), dict) else {}
        enrichment = resolved.get("indicator_enrichment") if isinstance(resolved.get("indicator_enrichment"), dict) else {}
        values = enrichment.get("indicator_values") if isinstance(enrichment.get("indicator_values"), dict) else {}
        return values
    except Exception:
        return {}


def _enforce_loss_cut(actions: list[dict[str, Any]], review: dict[str, Any],
                      context: dict[str, Any]) -> list[dict[str, Any]]:
    """Force-close any position whose floating loss exceeds MAX_LOSS_PCT.

    This is a hard override — it does not matter what the LLM decided, whether
    a thesis is active, or what the kill-switch state is.
    """
    close_ids = {a.get("target_position_id") for a in actions if a.get("action_type") == "close_position"}
    for pos in context.get("positions", []):
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id or pos_id in close_ids:
            continue
        entry = float(pos.get("price_open", 0) or 0)
        current = float(pos.get("price_current", 0) or 0)
        if entry <= 0 or current <= 0:
            continue
        side = str(pos.get("side", "")).strip().lower()
        is_losing = (side == "buy" and current < entry) or (side == "sell" and current > entry)
        if not is_losing:
            continue
        loss_pct = abs(current - entry) / entry
        if loss_pct >= MAX_LOSS_PCT:
            # Remove any existing action for this position
            actions = [a for a in actions if a.get("target_position_id") != pos_id]
            cut_action = _make_base_action(review)
            cut_action["action_type"] = "close_position"
            cut_action["urgency"] = "urgent"
            cut_action["target_position_id"] = pos_id
            cut_action["reason"] = f"Forced loss cut: {loss_pct:.2%} exceeds {MAX_LOSS_PCT:.2%} threshold."
            actions.append(cut_action)
    return actions


def _enforce_trailing(actions: list[dict[str, Any]], review: dict[str, Any],
                      context: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensure every profitable position has trailing stop enabled."""
    trailing_ids: set[int] = set()
    close_ids: set[int] = set()
    for a in actions:
        pid = a.get("target_position_id")
        if not pid:
            continue
        if a.get("action_type") == "close_position":
            close_ids.add(pid)
        elif a.get("action_type") == "enable_trailing_stop":
            ts = a.get("trailing_stop")
            if isinstance(ts, dict) and ts.get("enabled"):
                trailing_ids.add(pid)
    for pos in context.get("positions", []):
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id or pos_id in trailing_ids or pos_id in close_ids:
            continue
        profit = float(pos.get("profit", 0) or 0)
        if profit <= 0:
            continue
        trail_action = _make_base_action(review)
        trail_action["action_type"] = "enable_trailing_stop"
        trail_action["target_position_id"] = pos_id
        _t_symbol = str(pos.get("symbol", ""))
        _t_atr = float(_load_indicator_values(_t_symbol, "M5").get("atr_14", 0) or 0) or None if _t_symbol else None
        trail_action["trailing_stop"] = build_trailing_payload(pos, atr_value=_t_atr)
        sl, tp = build_default_protection(pos, context.get("thesis"))
        trail_action["stop_loss"] = sl
        trail_action["take_profit"] = float(pos.get("take_profit", 0) or 0) or tp
        trail_action["reason"] = "Enforced trailing: profitable position must have trailing stop."
        actions.append(trail_action)
    return actions


def _enforce_no_passive_underwater(actions: list[dict[str, Any]],
                                   context: dict[str, Any]) -> list[dict[str, Any]]:
    """Replace maintain_and_monitor with tighten_stop for any losing position."""
    for action in actions:
        if action.get("action_type") != "maintain_and_monitor":
            continue
        pos_id = action.get("target_position_id")
        if not pos_id:
            continue
        pos = next((p for p in context.get("positions", [])
                     if int(p.get("position_id", 0) or 0) == pos_id), None)
        if pos and float(pos.get("profit", 0) or 0) < 0:
            action["action_type"] = "tighten_stop"
            action["urgency"] = "high"
            action["reason"] = (str(action.get("reason", "")) + " [OVERRIDE: passive monitoring not allowed on losing position]").strip()
            sl, tp = build_default_protection(pos, context.get("thesis"))
            action["stop_loss"] = sl
            action["take_profit"] = tp
    return actions


def _apply_enforcement(actions: list[dict[str, Any]], review: dict[str, Any],
                       context: dict[str, Any]) -> list[dict[str, Any]]:
    """Chain all post-decision enforcement rules."""
    actions = _enforce_no_passive_underwater(actions, context)
    actions = _enforce_loss_cut(actions, review, context)
    actions = _enforce_trailing(actions, review, context)
    return actions


# ---------------------------------------------------------------------------
# CAPA 1: Pre-LLM heuristic functions — executed BEFORE LLM decision
# ---------------------------------------------------------------------------

def _heuristic_equity_drawdown(positions: list[dict[str, Any]],
                                connector: MT5Connector | None,
                                account: dict[str, Any] | None = None) -> list[int]:
    """H1: Close losing positions if equity drawdown exceeds posture threshold.

    Returns list of position_ids that were closed.
    """
    closed_ids: list[int] = []
    if account is None:
        account = _load_account_state()
    balance = float(account.get("balance", 0) or 0)
    equity = float(account.get("equity", 0) or 0)
    if balance <= 0 or equity <= 0:
        return closed_ids
    drawdown_pct = (balance - equity) / balance
    posture = _get_risk_posture()
    max_dd = _RISK_POSTURE_MAX_DD.get(posture, 0.05)
    if drawdown_pct <= max_dd:
        return closed_ids
    # Sort positions by profit ascending (biggest loser first)
    losers = sorted(
        [p for p in positions if float(p.get("profit", 0) or 0) < 0],
        key=lambda p: float(p.get("profit", 0) or 0),
    )
    if not losers:
        return closed_ids
    print(f"[live-execution-trader] H1 EQUITY BREAKER: drawdown={drawdown_pct:.2%} > {max_dd:.2%} — closing {len(losers)} loser(s)")
    for pos in losers:
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id:
            continue
        if connector:
            try:
                connector.close_position(
                    symbol=str(pos.get("symbol", "")),
                    position_id=pos_id,
                    side=str(pos.get("side", "")),
                    volume=float(pos.get("volume", 0) or 0),
                )
            except Exception as exc:
                print(f"[live-execution-trader] H1 close {pos_id} failed: {exc}")
                continue
        closed_ids.append(pos_id)
    return closed_ids


def _heuristic_instant_shield(positions: list[dict[str, Any]],
                               thesis: dict[str, Any] | None,
                               connector: MT5Connector | None) -> list[int]:
    """H4: Immediately apply SL/TP to any unprotected position.

    Returns list of position_ids that were shielded.
    """
    shielded_ids: list[int] = []
    for pos in positions:
        sl = float(pos.get("stop_loss", 0) or 0)
        tp = float(pos.get("take_profit", 0) or 0)
        if sl > 0 and tp > 0:
            continue
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id:
            continue
        new_sl, new_tp = build_default_protection(pos, thesis)
        if not new_sl and not new_tp:
            continue
        apply_sl = new_sl if sl <= 0 else None
        apply_tp = new_tp if tp <= 0 else None
        if not apply_sl and not apply_tp:
            continue
        print(f"[live-execution-trader] H4 INSTANT SHIELD: pos {pos_id} SL={apply_sl} TP={apply_tp}")
        if connector:
            try:
                connector.modify_position_levels(
                    symbol=str(pos.get("symbol", "")),
                    position_id=pos_id,
                    stop_loss=apply_sl or (sl if sl > 0 else None),
                    take_profit=apply_tp or (tp if tp > 0 else None),
                )
            except Exception as exc:
                print(f"[live-execution-trader] H4 shield {pos_id} failed: {exc}")
                continue
        shielded_ids.append(pos_id)
    return shielded_ids


def _heuristic_m5_reversal_profit_take(symbol: str,
                                        positions: list[dict[str, Any]],
                                        connector: MT5Connector | None) -> list[int]:
    """H2: Close profitable positions if M5 shows trend reversal in last 1-2 candles.

    A trader humano de scalping cierra inmediatamente cuando ve reversión en M5.
    Returns list of position_ids closed.
    """
    closed_ids: list[int] = []
    candles = _load_m5_candles(symbol)
    if len(candles) < 2:
        return closed_ids
    c_last = candles[-1]  # most recent candle
    c_prev = candles[-2]  # previous candle
    last_close = float(c_last.get("close", 0) or 0)
    last_open = float(c_last.get("open", 0) or 0)
    prev_low = float(c_prev.get("low", 0) or 0)
    prev_high = float(c_prev.get("high", 0) or 0)
    if last_close <= 0 or last_open <= 0 or prev_low <= 0 or prev_high <= 0:
        return closed_ids
    for pos in positions:
        profit = float(pos.get("profit", 0) or 0)
        if profit <= 0:
            continue
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id:
            continue
        side = str(pos.get("side", "")).strip().lower()
        reversal = False
        if side == "buy":
            # Bearish reversal: last candle is bearish AND closes below previous low
            reversal = (last_close < last_open) and (last_close < prev_low)
        elif side == "sell":
            # Bullish reversal: last candle is bullish AND closes above previous high
            reversal = (last_close > last_open) and (last_close > prev_high)
        if not reversal:
            continue
        print(f"[live-execution-trader] H2 M5 REVERSAL PROFIT-TAKE: pos {pos_id} {side} profit={profit:.2f}")
        if connector:
            try:
                connector.close_position(
                    symbol=str(pos.get("symbol", "")),
                    position_id=pos_id,
                    side=side,
                    volume=float(pos.get("volume", 0) or 0),
                )
            except Exception as exc:
                print(f"[live-execution-trader] H2 close {pos_id} failed: {exc}")
                continue
        closed_ids.append(pos_id)
    return closed_ids


def _heuristic_volatility_profit_lock(symbol: str,
                                       positions: list[dict[str, Any]],
                                       equity: float,
                                       connector: MT5Connector | None) -> list[int]:
    """H3: Lock profits when volatility spikes (ATR M5 scaled to H1 > 1.5× ATR H1).

    Close if profit > 0.3% equity, or tighten trailing if smaller profit.
    Returns list of position_ids CLOSED only (tightened positions stay for LLM).
    """
    closed_ids: list[int] = []
    m5_indicators = _load_indicator_values(symbol, "M5")
    h1_indicators = _load_indicator_values(symbol, "H1")
    atr_m5 = float(m5_indicators.get("atr_14", 0) or 0)
    atr_h1 = float(h1_indicators.get("atr_14", 0) or 0)
    if atr_m5 <= 0 or atr_h1 <= 0:
        return closed_ids
    # Normalize: scale M5 ATR to H1 timeframe (12 M5 bars = 1 H1 bar)
    atr_m5_scaled = atr_m5 * 12
    if atr_m5_scaled <= atr_h1 * 1.5:
        return closed_ids  # No volatility spike
    equity = max(equity, 1.0)
    for pos in positions:
        profit = float(pos.get("profit", 0) or 0)
        if profit <= 0:
            continue
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id:
            continue
        profit_pct = profit / equity
        side = str(pos.get("side", "")).strip().lower()
        if profit_pct > 0.003:
            # Significant profit in volatile market → close
            print(f"[live-execution-trader] H3 VOLATILITY LOCK CLOSE: pos {pos_id} profit={profit:.2f} atr_m5_scaled={atr_m5_scaled:.6f} vs atr_h1={atr_h1:.6f}")
            if connector:
                try:
                    connector.close_position(
                        symbol=str(pos.get("symbol", "")),
                        position_id=pos_id,
                        side=side,
                        volume=float(pos.get("volume", 0) or 0),
                    )
                except Exception as exc:
                    print(f"[live-execution-trader] H3 close {pos_id} failed: {exc}")
                    continue
            closed_ids.append(pos_id)
        else:
            # Smaller profit → tighten SL using tight ATR distance
            # NOT added to closed_ids — LLM can still refine these positions
            current = float(pos.get("price_current", 0) or 0)
            if current <= 0:
                continue
            tight_distance = atr_m5 * 0.5
            if side == "buy":
                tight_sl = current - tight_distance
            elif side == "sell":
                tight_sl = current + tight_distance
            else:
                continue
            current_sl = float(pos.get("stop_loss", 0) or 0)
            # Only tighten, never widen
            if side == "buy" and current_sl > 0 and tight_sl <= current_sl:
                continue
            if side == "sell" and current_sl > 0 and tight_sl >= current_sl:
                continue
            print(f"[live-execution-trader] H3 VOLATILITY TIGHTEN: pos {pos_id} SL={tight_sl:.5f}")
            if connector:
                try:
                    connector.modify_position_levels(
                        symbol=str(pos.get("symbol", "")),
                        position_id=pos_id,
                        stop_loss=tight_sl,
                        take_profit=float(pos.get("take_profit", 0) or 0) or None,
                    )
                except Exception as exc:
                    print(f"[live-execution-trader] H3 tighten {pos_id} failed: {exc}")
                    continue
    return closed_ids


def _heuristic_fast_loss_cut(positions: list[dict[str, Any]],
                              connector: MT5Connector | None) -> list[int]:
    """H5: Fast loss cut with dynamic thresholds per risk posture.

    Three triggers:
    1. Loss exceeds 2× original SL distance (slippage/gap beyond SL)
    2. No SL and loss > 0.5% of entry price
    3. Loss exceeds posture-based MAX_LOSS_PCT

    Returns list of position_ids closed.
    """
    closed_ids: list[int] = []
    posture = _get_risk_posture()
    max_loss = _RISK_POSTURE_LOSS_PCT.get(posture, MAX_LOSS_PCT)
    for pos in positions:
        pos_id = int(pos.get("position_id", 0) or 0)
        if not pos_id:
            continue
        entry = float(pos.get("price_open", 0) or 0)
        current = float(pos.get("price_current", 0) or 0)
        if entry <= 0 or current <= 0:
            continue
        side = str(pos.get("side", "")).strip().lower()
        is_losing = (side == "buy" and current < entry) or (side == "sell" and current > entry)
        if not is_losing:
            continue
        loss_pct = abs(current - entry) / entry
        sl = float(pos.get("stop_loss", 0) or 0)
        sl_distance = abs(sl - entry) / entry if sl > 0 and entry > 0 else 0.0
        should_cut = False
        reason = ""
        # Trigger 1: loss exceeds 2× SL distance (slippage/gap)
        if sl_distance > 0 and loss_pct > 2 * sl_distance:
            should_cut = True
            reason = f"loss {loss_pct:.2%} > 2× SL distance {sl_distance:.2%}"
        # Trigger 2: no SL and loss > 0.5%
        elif sl_distance == 0 and loss_pct > 0.005:
            should_cut = True
            reason = f"no SL and loss {loss_pct:.2%} > 0.5%"
        # Trigger 3: posture-based max loss
        elif loss_pct >= max_loss:
            should_cut = True
            reason = f"loss {loss_pct:.2%} >= posture max {max_loss:.2%}"
        if not should_cut:
            continue
        print(f"[live-execution-trader] H5 FAST LOSS CUT: pos {pos_id} — {reason}")
        if connector:
            try:
                connector.close_position(
                    symbol=str(pos.get("symbol", "")),
                    position_id=pos_id,
                    side=side,
                    volume=float(pos.get("volume", 0) or 0),
                )
            except Exception as exc:
                print(f"[live-execution-trader] H5 close {pos_id} failed: {exc}")
                continue
        closed_ids.append(pos_id)
    return closed_ids


def _run_heuristic_layer(symbol: str, positions: list[dict[str, Any]],
                          thesis: dict[str, Any] | None,
                          connector: MT5Connector | None) -> set[int]:
    """CAPA 1: Execute all pre-LLM heuristics. Returns set of position_ids handled.

    Order of execution:
    1. H1: Equity drawdown circuit-breaker
    2. H4: Instant shield (unprotected positions)
    3. H2: M5 trend-reversal profit-take
    4. H3: High-volatility profit lock
    5. H5: Fast loss cut

    Positions handled here are excluded from CAPA 2 (LLM).
    """
    handled: set[int] = set()
    account = _load_account_state()
    equity = float(account.get("equity", 0) or 0)
    # H1: Equity drawdown — acts on all positions globally
    h1_closed = _heuristic_equity_drawdown(positions, connector, account=account)
    handled.update(h1_closed)
    remaining = [p for p in positions if int(p.get("position_id", 0) or 0) not in handled]
    # H4: Instant shield — protect naked positions immediately
    h4_shielded = _heuristic_instant_shield(remaining, thesis, connector)
    # Note: shielded positions are NOT excluded from LLM - LLM can refine the SL/TP
    # H2: M5 reversal profit-take
    h2_closed = _heuristic_m5_reversal_profit_take(symbol, remaining, connector)
    handled.update(h2_closed)
    remaining = [p for p in remaining if int(p.get("position_id", 0) or 0) not in handled]
    # H3: Volatility profit lock
    h3_acted = _heuristic_volatility_profit_lock(symbol, remaining, equity, connector)
    handled.update(h3_acted)
    remaining = [p for p in remaining if int(p.get("position_id", 0) or 0) not in handled]
    # H5: Fast loss cut
    h5_closed = _heuristic_fast_loss_cut(remaining, connector)
    handled.update(h5_closed)
    if handled:
        print(f"[live-execution-trader] CAPA 1 handled {len(handled)} position(s) for {symbol}: {sorted(handled)}")
    return handled


def build_llm_messages(review: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    market_ctx = context.get("market_context") or {}
    compact = {
        "review": {
            "symbol": review.get("symbol"),
            "timeframe": review.get("timeframe"),
            "action": review.get("action"),
            "urgency": review.get("urgency"),
            "operation_scope": review.get("operation_scope"),
            "display_text": review.get("display_text"),
            "position_count": review.get("position_count"),
            "pending_order_count": review.get("pending_order_count"),
            "unprotected_position_count": review.get("unprotected_position_count"),
            "unprotected_order_count": review.get("unprotected_order_count"),
            "stale_order_count": review.get("stale_order_count"),
            "kill_switch_state": review.get("kill_switch_state"),
        },
        "market": {
            "state_summary": market_ctx.get("state_summary"),
            "structure": market_ctx.get("structure"),
            "session": market_ctx.get("session"),
            "indicators": market_ctx.get("indicator_enrichment"),
        },
        "account": market_ctx.get("account_state"),
        "positions": [
            {
                "position_id": p.get("position_id"),
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "volume": p.get("volume"),
                "price_open": p.get("price_open"),
                "price_current": p.get("price_current"),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "profit": p.get("profit"),
            }
            for p in context.get("positions", [])[:10]
        ],
        "orders": [
            {
                "order_id": o.get("order_id"),
                "symbol": o.get("symbol"),
                "order_type": o.get("order_type"),
                "price_open": o.get("price_open"),
                "stop_loss": o.get("stop_loss"),
                "take_profit": o.get("take_profit"),
                "status": o.get("status"),
            }
            for o in context.get("orders", [])[:10]
        ],
        "thesis": {
            "thesis_id": (context.get("thesis") or {}).get("thesis_id"),
            "status": (context.get("thesis") or {}).get("status"),
            "bias": (context.get("thesis") or {}).get("bias"),
            "confidence": (context.get("thesis") or {}).get("confidence"),
        } if context.get("thesis") else None,
        "kill_switch_state": context.get("kill_switch_state", "armed"),
    }
    system = load_prompt(CFG["repo_root"], "live_execution_trader", "system")
    user = load_prompt(
        CFG["repo_root"],
        "live_execution_trader",
        "user",
        compact_json=json.dumps(compact, ensure_ascii=True),
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_localai(messages: list[dict[str, str]], *, symbol: str = "", timeframe: str = "", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    metric = begin_llm_request(role="live_execution_trader", model=CFG["live_execution_trader_model"], symbol=symbol, timeframe=timeframe, meta=meta)
    payload = {
        "model": CFG["live_execution_trader_model"],
        "messages": messages,
        "temperature": 0.15,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{CFG['localai_base_url']}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if not acquire_llm_slot("live_execution_trader"):
        raise TimeoutError("[live_execution_trader] LLM gate timeout")
    try:
        with urllib.request.urlopen(req, timeout=CFG["timeout_seconds"]) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        finish_llm_request(metric, status="failed", error=exc)
        raise RuntimeError(f"LocalAI HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        finish_llm_request(metric, status="failed", error=exc)
        raise RuntimeError(f"LocalAI connection failed: {exc.reason}") from exc
    finally:
        release_llm_slot("live_execution_trader")
    result = json.loads(body)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        finish_llm_request(metric, status="failed", error="choices array missing")
        raise ValueError("choices array missing")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        finish_llm_request(metric, status="failed", error="no content in response")
        raise ValueError("no content in response")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        finish_llm_request(metric, status="failed", error="response is not a JSON object")
        raise ValueError("response is not a JSON object")
    finish_llm_request(metric, status="ok")
    return parsed


VALID_ACTION_TYPES = {
    "maintain_and_monitor", "add_protection", "tighten_stop", "extend_take_profit",
    "enable_trailing_stop", "cancel_order", "close_position", "reduce_position", "request_analysis",
}


def _parse_llm_action(raw: dict[str, Any], review: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    """Parsea y valida una acción individual del LLM. Retorna None si inválida."""
    action_type = str(raw.get("action_type", "")).strip().lower()
    if action_type not in VALID_ACTION_TYPES:
        return None
    # Validar que target_position_id y target_order_id existan en el contexto
    valid_pos_ids = {int(p.get("position_id", 0) or 0) for p in context.get("positions", [])}
    valid_ord_ids = {int(o.get("order_id", 0) or 0) for o in context.get("orders", [])}
    raw_pos_id = int(raw.get("target_position_id", 0) or 0) or None
    raw_ord_id = int(raw.get("target_order_id", 0) or 0) or None
    if raw_pos_id and raw_pos_id not in valid_pos_ids:
        raw_pos_id = None  # LLM inventó un ID inexistente
    if raw_ord_id and raw_ord_id not in valid_ord_ids:
        raw_ord_id = None
    # Acciones que requieren target válido
    if action_type in {"add_protection", "tighten_stop", "enable_trailing_stop", "close_position", "reduce_position"} and not raw_pos_id:
        if action_type == "cancel_order" and not raw_ord_id:
            return None
        if action_type != "cancel_order" and not raw_pos_id:
            return None
    action = {
        "schema_version": "1.0.0",
        "action_id": f"live_action_{uuid.uuid4().hex}",
        "review_id": str(review.get("review_id", "")),
        "symbol": str(review.get("symbol", "")),
        "timeframe": str(review.get("timeframe", "")),
        "operation_scope": str(review.get("operation_scope", "")),
        "action_type": action_type,
        "status": "planned",
        "urgency": str(raw.get("urgency", review.get("urgency", "normal"))).lower(),
        "linked_thesis_id": review.get("linked_thesis_id"),
        "target_position_id": raw_pos_id,
        "target_order_id": raw_ord_id,
        "source_signature": str(review.get("source_signature", "")),
        "reason": str(raw.get("reason", ""))[:500],
        "stop_loss": float(raw["stop_loss"]) if isinstance(raw.get("stop_loss"), (int, float)) and float(raw.get("stop_loss", 0) or 0) > 0 else None,
        "take_profit": float(raw["take_profit"]) if isinstance(raw.get("take_profit"), (int, float)) and float(raw.get("take_profit", 0) or 0) > 0 else None,
        "close_fraction": float(raw["close_fraction"]) if isinstance(raw.get("close_fraction"), (int, float)) and float(raw.get("close_fraction", 0) or 0) > 0 else None,
        "trailing_stop": raw.get("trailing_stop") if isinstance(raw.get("trailing_stop"), dict) else None,
        "response": None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    if action["urgency"] not in {"normal", "high", "urgent"}:
        action["urgency"] = "normal"
    # --- Validar precios: dirección correcta por side + rango razonable ---
    if action["action_type"] in {"add_protection", "tighten_stop", "enable_trailing_stop"}:
        target_pos = None
        if action.get("target_position_id"):
            target_pos = next((p for p in context.get("positions", []) if int(p.get("position_id", 0) or 0) == action["target_position_id"]), None)
        if target_pos:
            ref_price = float(target_pos.get("price_current", 0) or 0) or float(target_pos.get("price_open", 0) or 0)
            side = str(target_pos.get("side", "")).strip().lower()
            sl_val = action.get("stop_loss")
            tp_val = action.get("take_profit")
            # Check 1: precios dentro del 2% del mercado (scalping-intradía desk)
            sl_range_ok = sl_val and ref_price > 0 and abs(sl_val - ref_price) / ref_price < 0.02
            tp_range_ok = tp_val and ref_price > 0 and abs(tp_val - ref_price) / ref_price < 0.02
            # Check 2: dirección correcta según side
            if side == "buy":
                sl_dir_ok = sl_val and ref_price > 0 and sl_val < ref_price
                tp_dir_ok = tp_val and ref_price > 0 and tp_val > ref_price
            elif side == "sell":
                sl_dir_ok = sl_val and ref_price > 0 and sl_val > ref_price
                tp_dir_ok = tp_val and ref_price > 0 and tp_val < ref_price
            else:
                sl_dir_ok = sl_range_ok
                tp_dir_ok = tp_range_ok
            sl_ok = sl_range_ok and sl_dir_ok
            tp_ok = tp_range_ok and tp_dir_ok
            if not sl_ok or not tp_ok:
                fb_sl, fb_tp = build_default_protection(target_pos, context.get("thesis"))
                if not sl_ok and fb_sl:
                    action["stop_loss"] = fb_sl
                if not tp_ok and fb_tp:
                    action["take_profit"] = fb_tp
    return action


def build_actions(review: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM como decisor primario (multi-acción), heurística como fallback + gap-fill."""
    try:
        messages = build_llm_messages(review, context)
        llm_response = call_localai(messages, symbol=str(review.get("symbol", "")).upper(), timeframe=str(review.get("timeframe", "")).upper())
        raw_actions = llm_response.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError("LLM did not return an actions array")
        actions: list[dict[str, Any]] = []
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_llm_action(raw, review, context)
            if parsed:
                actions.append(parsed)
        if not actions:
            raise ValueError("No valid actions parsed from LLM response")
        # Gap-fill: cubrir posiciones desprotegidas que la LLM no incluyó
        covered_pos_ids = {a.get("target_position_id") for a in actions if a.get("target_position_id")}
        covered_ord_ids = {a.get("target_order_id") for a in actions if a.get("target_order_id")}
        thesis = context.get("thesis")
        for pos in context.get("unprotected_positions", []):
            pos_id = int(pos.get("position_id", 0) or 0)
            if pos_id and pos_id not in covered_pos_ids:
                gap_action = _make_base_action(review)
                gap_action["action_type"] = "add_protection"
                gap_action["urgency"] = "high"
                gap_action["target_position_id"] = pos_id
                sl, tp = build_default_protection(pos, thesis)
                gap_action["stop_loss"] = sl
                gap_action["take_profit"] = tp
                gap_action["reason"] = "Gap-fill: LLM did not cover this unprotected position."
                actions.append(gap_action)
        for order in context.get("unprotected_orders", []):
            ord_id = int(order.get("order_id", 0) or 0)
            if ord_id and ord_id not in covered_ord_ids:
                price_open = float(order.get("price_open", 0.0) or 0.0)
                if price_open <= 0:
                    continue
                gap_action = _make_base_action(review)
                side = "buy" if "buy" in str(order.get("order_type", "")).lower() else "sell"
                distance = max(price_open * 0.0025, 0.0001)
                gap_action["action_type"] = "add_protection"
                gap_action["urgency"] = "high"
                gap_action["target_order_id"] = ord_id
                gap_action["stop_loss"] = price_open - distance if side == "buy" else price_open + distance
                gap_action["take_profit"] = price_open + (distance * 2.0) if side == "buy" else price_open - (distance * 2.0)
                gap_action["reason"] = "Gap-fill: LLM did not cover this unprotected order."
                actions.append(gap_action)
        # --- Post-LLM enforcement: loss cut, trailing, no-passive ---
        actions = _apply_enforcement(actions, review, context)
        # Persist symbol outlook for web UI
        symbol_outlook = str(llm_response.get("symbol_outlook", "")).strip()
        if symbol_outlook:
            _persist_outlook(review, context, actions, symbol_outlook)
        return actions
    except Exception:
        fallback_actions = build_actions_heuristic(review, context)
        record_llm_fallback(
            role="live_execution_trader",
            model=CFG["live_execution_trader_model"],
            symbol=str(review.get("symbol", "")).upper(),
            timeframe=str(review.get("timeframe", "")).upper(),
        )
        _persist_outlook(review, context, fallback_actions, "Heuristic fallback — no LLM outlook available.")
        return fallback_actions


def _persist_outlook(review: dict[str, Any], context: dict[str, Any],
                     actions: list[dict[str, Any]], outlook_text: str) -> None:
    try:
        action_types = [a.get("action_type", "") for a in actions]
        summary_parts = []
        from collections import Counter
        for atype, count in Counter(action_types).items():
            summary_parts.append(f"{atype}x{count}" if count > 1 else str(atype))
        bias = "neutral"
        lower = outlook_text.lower()
        if any(w in lower for w in ("bullish", "long", "upward", "buy")):
            bias = "bullish"
        elif any(w in lower for w in ("bearish", "short", "downward", "sell")):
            bias = "bearish"
        now = utc_now_iso()
        upsert_symbol_outlook_cache(CFG["runtime_db_path"], {
            "symbol": review.get("symbol", ""),
            "timeframe": review.get("timeframe", ""),
            "outlook": outlook_text,
            "bias": bias,
            "actions_summary": ", ".join(summary_parts),
            "position_count": int(review.get("position_count", 0) or 0),
            "unprotected_count": int(review.get("unprotected_position_count", 0) or 0),
            "created_at": now,
            "updated_at": now,
        })
    except Exception as exc:
        print(f"[live-execution-trader] outlook persist failed: {exc}")


def _make_base_action(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "action_id": f"live_action_{uuid.uuid4().hex}",
        "review_id": str(review.get("review_id", "")),
        "symbol": str(review.get("symbol", "")),
        "timeframe": str(review.get("timeframe", "")),
        "operation_scope": str(review.get("operation_scope", "")),
        "action_type": "maintain_and_monitor",
        "status": "planned",
        "urgency": str(review.get("urgency", "normal")),
        "linked_thesis_id": review.get("linked_thesis_id"),
        "target_position_id": None,
        "target_order_id": None,
        "source_signature": str(review.get("source_signature", "")),
        "reason": str(review.get("message", "")),
        "stop_loss": None,
        "take_profit": None,
        "close_fraction": None,
        "trailing_stop": None,
        "response": None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }


def build_actions_heuristic(review: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Genera una lista de acciones heurísticas — una por posición/orden que lo necesite."""
    positions = context["positions"]
    orders = context["orders"]
    thesis = context["thesis"]
    unprotected_positions = context["unprotected_positions"]
    unprotected_orders = context["unprotected_orders"]
    stale_orders = context["stale_orders"]
    actions: list[dict[str, Any]] = []
    _h_symbol = str(review.get("symbol", ""))
    _h_atr_m5 = float(_load_indicator_values(_h_symbol, "M5").get("atr_14", 0) or 0) or None if _h_symbol else None
    # 1. Proteger cada posición desprotegida
    for target in unprotected_positions:
        action = _make_base_action(review)
        sl, tp = build_default_protection(target, thesis)
        action["action_type"] = "add_protection"
        action["target_position_id"] = int(target.get("position_id", 0) or 0) or None
        action["stop_loss"] = sl
        action["take_profit"] = tp
        if float(target.get("profit", 0.0) or 0.0) > 0:
            action["trailing_stop"] = build_trailing_payload(target, atr_value=_h_atr_m5)
        actions.append(action)
    # 2. Proteger cada orden desprotegida
    for target in unprotected_orders:
        price_open = float(target.get("price_open", 0.0) or 0.0)
        if price_open <= 0:
            continue
        action = _make_base_action(review)
        side = "buy" if "buy" in str(target.get("order_type", "")).lower() else "sell"
        distance = max(price_open * 0.0025, 0.0001)
        action["action_type"] = "add_protection"
        action["target_order_id"] = int(target.get("order_id", 0) or 0) or None
        action["stop_loss"] = price_open - distance if side == "buy" else price_open + distance
        action["take_profit"] = price_open + (distance * 2.0) if side == "buy" else price_open - (distance * 2.0)
        actions.append(action)
    # 3. Cancelar cada orden stale
    for target in stale_orders:
        action = _make_base_action(review)
        action["action_type"] = "cancel_order"
        action["urgency"] = "high"
        action["target_order_id"] = int(target.get("order_id", 0) or 0) or None
        action["reason"] = "Pending order is stale and should be cancelled or replaced."
        actions.append(action)
    # 4. Kill switch tripped — tighten o cerrar cada posición
    if not actions and context["kill_switch_state"] == "tripped" and positions:
        for target in positions:
            action = _make_base_action(review)
            if float(target.get("profit", 0.0) or 0.0) < 0 and not context.get("thesis"):
                action["action_type"] = "close_position"
                action["urgency"] = "urgent"
                action["target_position_id"] = int(target.get("position_id", 0) or 0) or None
                action["reason"] = "Risk kill-switch tripped, position in loss, no active thesis. Closing."
            else:
                action["action_type"] = "tighten_stop"
                action["urgency"] = "high"
                action["target_position_id"] = int(target.get("position_id", 0) or 0) or None
                sl, tp = build_default_protection(target, thesis)
                action["stop_loss"] = sl
                action["take_profit"] = float(target.get("take_profit", 0.0) or 0.0) or tp
                action["reason"] = "Risk posture is tripped; tighten protection on live exposure."
            actions.append(action)
    # 5. Trailing para posiciones con profit (si no hay nada más)
    if not actions:
        profitable_positions = [item for item in positions if float(item.get("profit", 0.0) or 0.0) > 0]
        for target in profitable_positions:
            action = _make_base_action(review)
            action["action_type"] = "enable_trailing_stop"
            action["target_position_id"] = int(target.get("position_id", 0) or 0) or None
            sl, tp = build_default_protection(target, thesis)
            action["stop_loss"] = sl
            action["take_profit"] = float(target.get("take_profit", 0.0) or 0.0) or tp
            action["trailing_stop"] = build_trailing_payload(target, atr_value=_h_atr_m5)
            action["reason"] = "Profit is developing; convert fixed exposure into protected/trailing management."
            actions.append(action)
    # Fallback: al menos un maintain_and_monitor
    if not actions:
        actions.append(_make_base_action(review))
    # --- Post-heuristic enforcement: loss cut, trailing, no-passive ---
    actions = _apply_enforcement(actions, review, context)
    return actions


def apply_action(action: dict[str, Any], context: dict[str, Any], connector: MT5Connector | None) -> dict[str, Any]:
    if not CFG["auto_execute"] or connector is None:
        return action
    positions = {int(item.get("position_id", 0) or 0): item for item in context["positions"]}
    orders = {int(item.get("order_id", 0) or 0): item for item in context["orders"]}
    try:
        action_type = str(action.get("action_type", "")).strip().lower()
        if action_type in {"add_protection", "tighten_stop", "enable_trailing_stop"} and action.get("target_position_id"):
            target = positions.get(int(action["target_position_id"]))
            if not target:
                action["status"] = "failed"
                action["response"] = {"error": "target position missing"}
                return action
            response = connector.modify_position_levels(
                symbol=str(target.get("symbol", "")),
                position_id=int(target.get("position_id", 0) or 0),
                stop_loss=float(action["stop_loss"]) if isinstance(action.get("stop_loss"), (int, float)) and float(action.get("stop_loss", 0) or 0) > 0 else None,
                take_profit=float(action["take_profit"]) if isinstance(action.get("take_profit"), (int, float)) and float(action.get("take_profit", 0) or 0) > 0 else None,
            )
            action["response"] = response
            action["status"] = "executed" if response.get("ok") else "rejected"
            return action
        if action_type == "add_protection" and action.get("target_order_id"):
            target = orders.get(int(action["target_order_id"]))
            if not target:
                action["status"] = "failed"
                action["response"] = {"error": "target order missing"}
                return action
            response = connector.modify_order_levels(
                symbol=str(target.get("symbol", "")),
                order_id=int(target.get("order_id", 0) or 0),
                price_open=float(target.get("price_open", 0.0) or 0.0) or None,
                stop_loss=float(action["stop_loss"]) if isinstance(action.get("stop_loss"), (int, float)) and float(action.get("stop_loss", 0) or 0) > 0 else None,
                take_profit=float(action["take_profit"]) if isinstance(action.get("take_profit"), (int, float)) and float(action.get("take_profit", 0) or 0) > 0 else None,
            )
            action["response"] = response
            action["status"] = "executed" if response.get("ok") else "rejected"
            return action
        if action_type == "cancel_order" and action.get("target_order_id"):
            response = connector.remove_order(int(action["target_order_id"]))
            action["response"] = response
            action["status"] = "executed" if response.get("ok") else "rejected"
            return action
        if action_type == "close_position" and action.get("target_position_id"):
            target = positions.get(int(action["target_position_id"]))
            if not target:
                action["status"] = "failed"
                action["response"] = {"error": "target position missing"}
                return action
            response = connector.close_position(
                symbol=str(target.get("symbol", "")),
                position_id=int(target.get("position_id", 0) or 0),
                side=str(target.get("side", "")),
                volume=float(target.get("volume", 0.0) or 0.0),
            )
            action["response"] = response
            action["status"] = "executed" if response.get("ok") else "rejected"
            return action
        if action_type == "reduce_position" and action.get("target_position_id"):
            target = positions.get(int(action["target_position_id"]))
            if not target:
                action["status"] = "failed"
                action["response"] = {"error": "target position missing"}
                return action
            close_fraction = float(action.get("close_fraction", 0.5) or 0.5)
            close_volume = float(target.get("volume", 0.0) or 0.0) * min(max(close_fraction, 0.01), 1.0)
            response = connector.close_position(
                symbol=str(target.get("symbol", "")),
                position_id=int(target.get("position_id", 0) or 0),
                side=str(target.get("side", "")),
                volume=close_volume,
            )
            action["response"] = response
            action["status"] = "executed" if response.get("ok") else "rejected"
            return action
    except Exception as exc:
        action["status"] = "failed"
        action["response"] = {"error": str(exc)}
        return action
    return action


def process_live_pair(symbol: str, timeframe: str) -> dict[str, Any] | None:
    # Hard-stop: no work at all outside normal gate state.
    if _get_main_desk_gate is not None:
        try:
            if _get_main_desk_gate(symbol)["gate_state"] != "normal":
                return None
        except Exception:
            pass
    context = classify_review_context(symbol, timeframe)
    if not context:
        return None
    # --- CAPA 1: Pre-LLM heuristic layer ---
    connector_h = None
    if CFG["auto_execute"]:
        try:
            connector_h = MT5Connector(terminal_path=MT5_CFG["terminal_path"])
            connector_h.connect()
        except Exception:
            connector_h = None
    try:
        heuristic_handled = _run_heuristic_layer(
            symbol,
            context["positions"],
            context.get("thesis"),
            connector_h,
        )
    finally:
        if connector_h is not None:
            connector_h.shutdown()
    # Persist heuristic actions
    if heuristic_handled:
        for pos_id in heuristic_handled:
            h_action = _make_base_action({"review_id": f"heuristic_{symbol}_{timeframe}", "symbol": symbol, "timeframe": timeframe, "operation_scope": "positions", "urgency": "urgent", "linked_thesis_id": None, "source_signature": "", "message": "CAPA 1 heuristic action"})
            h_action["action_type"] = "close_position"
            h_action["target_position_id"] = pos_id
            h_action["reason"] = "CAPA 1 heuristic: pre-LLM protective action"
            upsert_live_operation_action_cache(CFG["runtime_db_path"], h_action)
    # Filter out handled positions from context before LLM
    if heuristic_handled:
        context["positions"] = [p for p in context["positions"] if int(p.get("position_id", 0) or 0) not in heuristic_handled]
        context["unprotected_positions"] = [p for p in context.get("unprotected_positions", []) if int(p.get("position_id", 0) or 0) not in heuristic_handled]
        # If no positions/orders left, we're done
        if not context["positions"] and not context["orders"]:
            return {"review": {"review_id": f"heuristic_{symbol}_{timeframe}", "symbol": symbol, "timeframe": timeframe}, "actions": []}
    review = build_review(symbol, timeframe)
    if not review:
        return None
    # --- Position heuristic gate ---
    positions_for_gate = context.get("positions", [])
    account_state = (context.get("market_context") or {}).get("account_state") or {}
    equity = float(account_state.get("equity", 0) or 0)
    any_needs_eval = False
    eval_reasons: list[str] = []
    for pos in positions_for_gate:
        ticket = int(pos.get("position_id", 0) or 0)
        if not ticket:
            continue
        market_price = float(pos.get("price_current", 0) or 0)
        should_eval, reason = _should_reevaluate_position(ticket, pos, market_price, equity)
        if should_eval:
            any_needs_eval = True
            eval_reasons.append(f"{ticket}:{reason}")
    if positions_for_gate and not any_needs_eval:
        print(f"[live-execution-trader] SKIP {symbol} {timeframe}: all positions within parameters")
        return None
    if eval_reasons:
        print(f"[live-execution-trader] EVAL {symbol} {timeframe}: {', '.join(eval_reasons)}")
    actions = build_actions(review, context)
    # Record position evaluations after successful build_actions
    for pos in positions_for_gate:
        ticket = int(pos.get("position_id", 0) or 0)
        if ticket:
            _record_position_eval(ticket, pos, equity)
    emit_message = should_emit_review(review)
    connector = None
    if CFG["auto_execute"]:
        connector = MT5Connector(terminal_path=MT5_CFG["terminal_path"])
        connector.connect()
    try:
        # Enviar cada acción granularmente — si una falla, no bloquea al resto
        for action in actions:
            try:
                action = apply_action(action, context, connector)
            except Exception as exc:
                action["status"] = "failed"
                action["response"] = {"error": str(exc)}
            upsert_live_operation_action_cache(CFG["runtime_db_path"], action)
    finally:
        if connector is not None:
            connector.shutdown()
    upsert_live_operation_review_cache(CFG["runtime_db_path"], review)
    if emit_message:
        action_summary = [
            {"action_type": a.get("action_type"), "status": a.get("status"),
             "target_position_id": a.get("target_position_id"), "target_order_id": a.get("target_order_id"),
             "stop_loss": a.get("stop_loss"), "take_profit": a.get("take_profit")}
            for a in actions
        ]
        persist_message(
            db_path=CFG["runtime_db_path"],
            agent_role="trader",
            message_type=str(review.get("message_type", "position_review")),
            symbol=symbol,
            timeframe=timeframe,
            importance=str(review.get("urgency", "normal")).lower(),
            linked_thesis_id=review.get("linked_thesis_id"),
            content={
                "display_text": review.get("display_text"),
                "message": review.get("message"),
                "summary": review.get("summary"),
                "action": review.get("action"),
                "urgency": review.get("urgency"),
                "actions": action_summary,
                "position_count": review.get("position_count"),
                "pending_order_count": review.get("pending_order_count"),
                "unprotected_position_count": review.get("unprotected_position_count"),
                "unprotected_order_count": review.get("unprotected_order_count"),
                "stale_order_count": review.get("stale_order_count"),
                "kill_switch_state": review.get("kill_switch_state"),
            },
        )
    return {"review": review, "actions": actions}


def run_live_execution_trader_cycle() -> dict[str, Any]:
    # Clean up stale position entries from heuristic gate cache
    if CFG["runtime_db_path"].exists():
        with runtime_db_connection(CFG["runtime_db_path"]) as conn:
            rows = conn.execute("SELECT position_id FROM position_cache WHERE status = 'open'").fetchall()
        active_tickets = {int(r[0]) for r in rows if r[0]}
        stale = [t for t in _last_position_eval if t not in active_tickets]
        for t in stale:
            del _last_position_eval[t]
    processed: list[dict[str, Any]] = []
    for symbol, timeframe in list_review_pairs(CFG["max_pairs_per_cycle"]):
        try:
            result = process_live_pair(symbol, timeframe)
            if result:
                review = result["review"]
                for action in result["actions"]:
                    processed.append(
                        {
                            "review_id": str(review.get("review_id", "")),
                            "action_id": str(action.get("action_id", "")),
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "action": str(action.get("action_type", "")),
                            "status": str(action.get("status", "")),
                            "urgency": str(action.get("urgency", "")),
                        }
                    )
        except Exception as exc:
            print(f"[live-execution-trader] {symbol} {timeframe} failed: {exc}")
    trailing_summary = maintain_custodian_trailing()
    if trailing_summary["processed_count"] > 0:
        print(f"[live-execution-trader] trailing maintenance: {trailing_summary['processed_count']} update(s)")
    return {
        "processed": processed,
        "processed_count": len(processed),
        "completed_at": utc_now_iso(),
    }


def maintain_custodian_trailing() -> dict[str, Any]:
    """Recalcula trailing stops activos gestionados por el custodio."""
    processed: list[dict[str, Any]] = []
    if not CFG["runtime_db_path"].exists():
        return {"processed": processed, "processed_count": 0}
    with runtime_db_connection(CFG["runtime_db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        action_rows = conn.execute(
            "SELECT payload_json FROM live_operation_action_cache "
            "WHERE action_type = 'enable_trailing_stop' AND status = 'executed'"
        ).fetchall()
    if not action_rows:
        return {"processed": processed, "processed_count": 0}
    connector = None
    if CFG["auto_execute"]:
        try:
            connector = MT5Connector(terminal_path=MT5_CFG["terminal_path"])
            connector.connect()
        except Exception:
            return {"processed": processed, "processed_count": 0}
    try:
        for row in action_rows:
            action_data = decode_json_text(row[0] if row else None, {})
            trailing = action_data.get("trailing_stop")
            if not isinstance(trailing, dict) or not bool(trailing.get("enabled", False)):
                continue
            position_id = int(action_data.get("target_position_id", 0) or 0)
            if position_id <= 0:
                continue
            symbol = str(action_data.get("symbol", "")).upper()
            # Hard-stop: no trailing maintenance for symbols outside normal gate state.
            if _get_main_desk_gate is not None:
                try:
                    if _get_main_desk_gate(symbol)["gate_state"] != "normal":
                        continue
                except Exception:
                    pass
            activation_price = float(trailing.get("activation_price", 0.0) or 0.0)
            distance = float(trailing.get("distance", 0.0) or 0.0)
            step = float(trailing.get("step", 0.0) or 0.0)
            if activation_price <= 0 or distance <= 0 or step <= 0:
                continue
            with runtime_db_connection(CFG["runtime_db_path"]) as conn:
                conn.row_factory = sqlite3.Row
                pos_row = conn.execute(
                    "SELECT position_payload_json FROM position_cache "
                    "WHERE position_id = ? AND status = 'open'",
                    (position_id,),
                ).fetchone()
            if not pos_row:
                continue
            position = decode_json_text(pos_row[0], {})
            current_price = float(position.get("price_current", 0.0) or 0.0)
            current_sl = float(position.get("stop_loss", 0.0) or 0.0)
            side = str(position.get("side", "")).lower()
            if side == "buy":
                if current_price < activation_price:
                    continue
                proposed_sl = current_price - distance
                if current_sl > 0 and proposed_sl <= (current_sl + step):
                    continue
            elif side == "sell":
                if current_price > activation_price:
                    continue
                proposed_sl = current_price + distance
                if current_sl > 0 and proposed_sl >= (current_sl - step):
                    continue
            else:
                continue
            # Si tesis invalidada, convertir trailing en cierre
            thesis = load_recent_thesis(symbol, action_data.get("timeframe", "M5"))
            if thesis and str(thesis.get("status", "")).lower() in {"invalidated", "closed", "expired"}:
                if connector:
                    try:
                        response = connector.close_position(
                            symbol=symbol,
                            position_id=position_id,
                            side=side,
                            volume=float(position.get("volume", 0.0) or 0.0),
                        )
                        processed.append({"position_id": position_id, "action": "close_thesis_invalidated", "ok": response.get("ok")})
                    except Exception:
                        pass
                continue
            if connector:
                try:
                    response = connector.modify_position_levels(
                        symbol=symbol,
                        position_id=position_id,
                        stop_loss=proposed_sl,
                        take_profit=float(position.get("take_profit", 0.0) or 0.0) or None,
                    )
                    processed.append({"position_id": position_id, "action": "trailing_updated", "ok": response.get("ok")})
                except Exception:
                    continue
    finally:
        if connector is not None:
            connector.shutdown()
    return {"processed": processed, "processed_count": len(processed)}


def runtime_loop() -> None:
    while True:
        summary = run_live_execution_trader_cycle()
        if summary["processed_count"] > 0:
            print(f"[live-execution-trader] processed {summary['processed_count']} live review(s)")
        time.sleep(CFG["poll_seconds"])


def main() -> None:
    runtime_loop()


if __name__ == "__main__":
    main()
