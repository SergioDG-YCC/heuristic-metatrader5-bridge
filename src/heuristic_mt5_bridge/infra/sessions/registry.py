"""
Thread-safe in-memory broker session registry.

This is shared operational state, not desk-specific state.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any


_lock = threading.Lock()

_session_groups: dict[str, dict[str, Any]] = {}
_symbol_to_session_group: dict[str, str] = {}
_active_symbols: set[str] = set()
_registry_meta: dict[str, Any] = {}

_pending_symbols: set[str] = set()
_failed_symbols: set[str] = set()

_server_time_offset_seconds: int = 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_sessions(raw: dict[str, Any]) -> dict[str, list[dict[str, int]]]:
    result: dict[str, list[dict[str, int]]] = {}
    for day_key in sorted(raw.keys(), key=lambda key: int(key)):
        windows = raw[day_key]
        normalized = sorted(
            [{"from": int(window["from"]), "to": int(window["to"])} for window in windows if window],
            key=lambda window: (window["from"], window["to"]),
        )
        result[day_key] = normalized
    return result


def _compute_signature(trade_sessions: dict[str, Any], quote_sessions: dict[str, Any]) -> str:
    canonical = json.dumps({"trade": trade_sessions, "quote": quote_sessions}, sort_keys=True)
    return "sig_" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def queue_bootstrap(symbols: list[str]) -> None:
    with _lock:
        _pending_symbols.update(symbol.upper() for symbol in symbols)


def add_pending_symbols(symbols: list[str]) -> None:
    with _lock:
        _pending_symbols.update(symbol.upper() for symbol in symbols)


def mark_symbol_failed(symbol: str) -> None:
    with _lock:
        _failed_symbols.add(symbol.upper())


def get_fetch_request() -> list[str] | None:
    with _lock:
        wanted = _pending_symbols | _failed_symbols
        return sorted(wanted) if wanted else None


def apply_incoming_sessions(incoming: dict[str, Any]) -> None:
    global _session_groups, _symbol_to_session_group, _active_symbols, _registry_meta

    new_groups: dict[str, dict[str, Any]] = {}
    new_symbol_to_group: dict[str, str] = {}
    fetched: set[str] = set()

    with _lock:
        existing_symbol_to_group = dict(_symbol_to_session_group)
        existing_groups = dict(_session_groups)

    for raw_symbol, data in incoming.items():
        symbol = raw_symbol.upper()
        fetched.add(symbol)
        try:
            trade_norm = _normalize_sessions(data.get("trade") or {})
            quote_norm = _normalize_sessions(data.get("quote") or {})
        except Exception:
            with _lock:
                _failed_symbols.add(symbol)
            continue

        signature = _compute_signature(trade_norm, quote_norm)
        if signature not in new_groups:
            new_groups[signature] = {
                "trade_sessions": trade_norm,
                "quote_sessions": quote_norm,
                "symbols": [],
            }
        new_groups[signature]["symbols"].append(symbol)
        new_symbol_to_group[symbol] = signature

    for symbol, signature in existing_symbol_to_group.items():
        if symbol in new_symbol_to_group:
            continue
        if signature in existing_groups:
            if signature not in new_groups:
                new_groups[signature] = dict(existing_groups[signature])
                new_groups[signature]["symbols"] = []
            if symbol not in new_groups[signature]["symbols"]:
                new_groups[signature]["symbols"].append(symbol)
        new_symbol_to_group[symbol] = signature

    with _lock:
        _session_groups = new_groups
        _symbol_to_session_group = new_symbol_to_group
        _active_symbols = set(new_symbol_to_group.keys())
        _pending_symbols.difference_update(fetched)
        _failed_symbols.difference_update(fetched)
        _registry_meta = {
            "generated_at": _utc_now_iso(),
            "symbol_count": len(_active_symbols),
            "group_count": len(new_groups),
        }


def remove_active_symbols(symbols: list[str]) -> None:
    global _session_groups, _symbol_to_session_group, _active_symbols

    to_remove = {symbol.upper() for symbol in symbols}
    with _lock:
        for symbol in to_remove:
            signature = _symbol_to_session_group.pop(symbol, None)
            if signature and signature in _session_groups:
                try:
                    _session_groups[signature]["symbols"].remove(symbol)
                except ValueError:
                    pass
                if not _session_groups[signature]["symbols"]:
                    del _session_groups[signature]
        _active_symbols.difference_update(to_remove)
        _pending_symbols.difference_update(to_remove)
        _failed_symbols.difference_update(to_remove)
        if _registry_meta:
            _registry_meta["symbol_count"] = len(_active_symbols)
            _registry_meta["group_count"] = len(_session_groups)


def get_session_registry() -> dict[str, Any]:
    with _lock:
        return {
            "session_groups": {
                signature: {
                    "trade_sessions": group["trade_sessions"],
                    "quote_sessions": group["quote_sessions"],
                    "symbols": list(group["symbols"]),
                }
                for signature, group in _session_groups.items()
            },
            "symbol_to_session_group": dict(_symbol_to_session_group),
            "active_symbols": sorted(_active_symbols),
            "registry_meta": dict(_registry_meta),
            "pending_symbols": sorted(_pending_symbols),
            "failed_symbols": sorted(_failed_symbols),
        }


def get_symbol_session_group(symbol: str) -> str | None:
    with _lock:
        return _symbol_to_session_group.get(symbol.upper())


def set_server_time_offset(offset_seconds: int) -> None:
    global _server_time_offset_seconds
    with _lock:
        _server_time_offset_seconds = int(offset_seconds)


def get_server_time_offset() -> int:
    with _lock:
        return _server_time_offset_seconds

