from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


USABLE_FEED_STATUSES = {"live", "idle", "market_closed"}


def is_trade_open_from_registry(
    session_groups: dict[str, Any],
    symbol_to_group: dict[str, Any],
    symbol: str,
    *,
    server_time_offset_seconds: int = 0,
    now_utc: datetime | None = None,
) -> bool:
    signature = symbol_to_group.get(str(symbol).upper())
    if not signature:
        return False
    group = session_groups.get(signature)
    if not isinstance(group, dict):
        return False
    trade_sessions = group.get("trade_sessions")
    if not isinstance(trade_sessions, dict):
        return False

    current_utc = now_utc or datetime.now(timezone.utc)
    python_weekday = current_utc.weekday()
    mt5_day = (python_weekday + 1) % 7
    seconds = current_utc.hour * 3600 + current_utc.minute * 60 + current_utc.second + int(server_time_offset_seconds)
    if seconds >= 86400:
        seconds -= 86400
        mt5_day = (mt5_day + 1) % 7
    elif seconds < 0:
        seconds += 86400
        mt5_day = (mt5_day - 1) % 7

    for window in trade_sessions.get(str(mt5_day), []):
        if not isinstance(window, dict):
            continue
        window_from = int(window.get("from", 0))
        window_to = int(window.get("to", 0))
        if window_from <= seconds < window_to:
            return True
    return False


def resolve_timeframe_feed(
    feed_rows: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
) -> tuple[bool, str | None]:
    normalized_symbol = str(symbol).upper()
    normalized_timeframe = str(timeframe).upper()
    for item in feed_rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() != normalized_symbol:
            continue
        if str(item.get("timeframe", "")).upper() != normalized_timeframe:
            continue
        feed_status = str(item.get("feed_status", "")).strip()
        return True, feed_status or None
    return False, None


def feed_is_usable(feed_status: str | None) -> bool:
    if not feed_status:
        return False
    return feed_status.strip().lower() in USABLE_FEED_STATUSES


def evaluate_symbol_session_gate(
    symbol: str,
    market_state_payload: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol).upper()

    raw_feed_rows = market_state_payload.get("feed_status")
    feed_rows = [row for row in raw_feed_rows if isinstance(row, dict)] if isinstance(raw_feed_rows, list) else []

    m5_exists, m5_feed_status = resolve_timeframe_feed(feed_rows, normalized_symbol, "M5")
    h1_exists, h1_feed_status = resolve_timeframe_feed(feed_rows, normalized_symbol, "H1")
    m5_available = m5_exists and feed_is_usable(m5_feed_status)
    h1_available = h1_exists and feed_is_usable(h1_feed_status)
    has_required_timeframes = m5_available and h1_available

    session_known = False
    trade_open_now = False
    server_time_offset = int(market_state_payload.get("server_time_offset_seconds", 0) or 0)
    broker_registry = market_state_payload.get("broker_session_registry")
    if isinstance(broker_registry, dict):
        symbol_to_group = broker_registry.get("symbol_to_session_group") or {}
        session_groups = broker_registry.get("session_groups") or {}
        if isinstance(symbol_to_group, dict) and normalized_symbol in symbol_to_group:
            session_known = True
            trade_open_now = is_trade_open_from_registry(
                session_groups,
                symbol_to_group,
                normalized_symbol,
                server_time_offset_seconds=server_time_offset,
                now_utc=now_utc,
            )

    if not session_known:
        gate_state = "blocked_no_session_data"
        reason = "session_gate_no_data"
    elif not trade_open_now:
        gate_state = "closed"
        reason = "session_gate_closed"
    elif not has_required_timeframes:
        gate_state = "blocked_chart_unavailable"
        reason = "session_gate_chart_unavailable"
    else:
        gate_state = "normal"
        reason = "session_open"

    is_normal = gate_state == "normal"
    return {
        "symbol": normalized_symbol,
        "session_known": session_known,
        "trade_open_now": trade_open_now,
        "has_required_timeframes": has_required_timeframes,
        "m5_available": m5_available,
        "h1_available": h1_available,
        "m5_feed_status": m5_feed_status,
        "h1_feed_status": h1_feed_status,
        "gate_state": gate_state,
        "allow_new_analysis": is_normal,
        "allow_new_entry": is_normal,
        "allow_risk_approval": is_normal,
        "allow_live_custody_only": True,
        "reason": reason,
    }
