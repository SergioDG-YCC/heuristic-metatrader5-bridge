from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from mt5_connector import CFG as MT5_CFG
from mt5_connector import MT5Connector, MT5ConnectorError
from runtime_db import runtime_db_path, upsert_execution_event_cache, upsert_trigger_cache
from trading_universe import is_operable_symbol

SCHEMA_CACHE: dict[str, Draft202012Validator] = {}
SCHEMA_REGISTRY_CACHE: dict[str, Registry] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    configured_storage = Path(os.getenv("STORAGE_ROOT", env_values.get("STORAGE_ROOT", str(repo_root / "python" / "storage"))))
    storage_root = configured_storage if configured_storage.is_absolute() else repo_root / configured_storage
    return {
        "repo_root": repo_root,
        "storage_root": storage_root,
        "runtime_db_path": runtime_db_path(
            storage_root,
            os.getenv("RUNTIME_DB_PATH", env_values.get("RUNTIME_DB_PATH")),
        ),
        "poll_seconds": float(os.getenv("EXECUTION_BRIDGE_POLL_SECONDS", env_values.get("EXECUTION_BRIDGE_POLL_SECONDS", "5"))),
        "enabled": os.getenv("EXECUTION_BRIDGE_ENABLED", env_values.get("EXECUTION_BRIDGE_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"},
        "retry_cooldown_seconds": int(os.getenv("EXECUTION_RETRY_COOLDOWN_SECONDS", env_values.get("EXECUTION_RETRY_COOLDOWN_SECONDS", "45"))),
        "max_retries_per_intent": int(os.getenv("EXECUTION_MAX_RETRIES_PER_INTENT", env_values.get("EXECUTION_MAX_RETRIES_PER_INTENT", "4"))),
    }


CFG = config()


def schema_path(name: str) -> Path:
    return CFG["repo_root"] / "python" / "schemas" / name


def get_schema_registry() -> Registry:
    cache_key = str(CFG["repo_root"])
    if cache_key in SCHEMA_REGISTRY_CACHE:
        return SCHEMA_REGISTRY_CACHE[cache_key]
    registry = Registry()
    for path in (CFG["repo_root"] / "python" / "schemas").glob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema_id = schema.get("$id")
        if isinstance(schema_id, str) and schema_id:
            registry = registry.with_resource(schema_id, Resource.from_contents(schema))
            registry = registry.with_resource(path.name, Resource.from_contents(schema))
    SCHEMA_REGISTRY_CACHE[cache_key] = registry
    return registry


def validate_payload(schema_name: str, payload: dict[str, Any]) -> list[str]:
    if schema_name not in SCHEMA_CACHE:
        schema = json.loads(schema_path(schema_name).read_text(encoding="utf-8"))
        SCHEMA_CACHE[schema_name] = Draft202012Validator(schema, registry=get_schema_registry())
    validator = SCHEMA_CACHE[schema_name]
    errors = []
    for err in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in err.path) or "$"
        errors.append(f"{location}: {err.message}")
    return errors


def persist_json(subdir: str, record_id: str, payload: dict[str, Any]) -> Path:
    target = CFG["storage_root"] / subdir
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{record_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CFG["runtime_db_path"])
    conn.row_factory = sqlite3.Row
    return conn


def decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, str) and value.strip():
        return json.loads(value)
    if isinstance(value, dict):
        return value
    return {}


def load_approved_trader_intents(limit: int = 10) -> list[dict[str, Any]]:
    if not CFG["runtime_db_path"].exists():
        return []
    conn = db_conn()
    try:
        try:
            rows = conn.execute(
                """
                SELECT trader_intent_payload_json
                FROM trader_intent_cache
                WHERE supervisor_status = 'approved'
                  AND status IN ('proposed', 'watching', 'blocked')
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()
    return [decode_json(row[0]) for row in rows]


def load_latest_risk_review(trader_intent_id: str) -> dict[str, Any] | None:
    if not trader_intent_id or not CFG["runtime_db_path"].exists():
        return None
    conn = db_conn()
    try:
        try:
            row = conn.execute(
                """
                SELECT risk_review_payload_json
                FROM risk_review_cache
                WHERE linked_trader_intent_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (trader_intent_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    return decode_json(row[0]) if row else None


def execution_exists_for_trader_intent(trader_intent_id: str) -> bool:
    if not trader_intent_id or not CFG["runtime_db_path"].exists():
        return False
    conn = db_conn()
    try:
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM execution_event_cache
                WHERE linked_trader_intent_id = ?
                  AND event_type IN ('submitted', 'placed', 'filled', 'sync')
                """,
                (trader_intent_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
    finally:
        conn.close()
    return bool(row and int(row[0]) > 0)


def execution_retry_state(trader_intent_id: str) -> dict[str, Any]:
    if not trader_intent_id or not CFG["runtime_db_path"].exists():
        return {"attempts": 0, "recent_attempt": False}
    conn = db_conn()
    try:
        try:
            rows = conn.execute(
                """
                SELECT created_at
                FROM execution_event_cache
                WHERE linked_trader_intent_id = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (trader_intent_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"attempts": 0, "recent_attempt": False}
    finally:
        conn.close()
    attempts = len(rows)
    recent_attempt = False
    if rows:
        latest_created_at = str(rows[0]["created_at"] if isinstance(rows[0], sqlite3.Row) else rows[0][0])
        try:
            created_dt = datetime.fromisoformat(latest_created_at.replace("Z", "+00:00"))
            recent_attempt = (utc_now() - created_dt).total_seconds() < CFG["retry_cooldown_seconds"]
        except ValueError:
            recent_attempt = False
    return {"attempts": attempts, "recent_attempt": recent_attempt}


def load_open_positions() -> list[dict[str, Any]]:
    if not CFG["runtime_db_path"].exists():
        return []
    conn = db_conn()
    try:
        try:
            rows = conn.execute("SELECT position_payload_json FROM position_cache WHERE status = 'open'").fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()
    return [decode_json(row[0]) for row in rows]


def load_working_orders() -> list[dict[str, Any]]:
    if not CFG["runtime_db_path"].exists():
        return []
    conn = db_conn()
    try:
        try:
            rows = conn.execute("SELECT order_payload_json FROM order_cache WHERE status IN ('placed', 'working')").fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()
    return [decode_json(row[0]) for row in rows]


def _load_active_account_mode() -> str:
    """Read account_mode from account_state_cache in runtime DB."""
    if not CFG["runtime_db_path"].exists():
        return "demo"
    conn = db_conn()
    try:
        try:
            row = conn.execute(
                "SELECT account_state_payload_json FROM account_state_cache ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return "demo"
    finally:
        conn.close()
    if not row:
        return "demo"
    state = decode_json(row[0])
    return str(state.get("account_mode", "demo")).strip().lower()


def build_execution_instruction(trader_intent: dict[str, Any], risk_review: dict[str, Any]) -> dict[str, Any]:
    execution_id = f"execution_{uuid.uuid4().hex}"
    side = str(trader_intent.get("trade_side", "")).lower()
    trader_ref = str(trader_intent.get("trader_intent_id", "")).replace("trader_intent_", "")[:8]
    execution_ref = execution_id.replace("execution_", "")[:8]
    strategy_type = str(trader_intent.get("strategy_type", "")).strip().lower()
    comment = f"ti:{trader_ref}|ex:{execution_ref}"
    account_mode = _load_active_account_mode()
    execution_mode = "live" if account_mode == "real" else "demo_only"
    payload = {
        "schema_version": "1.0.0",
        "execution_id": execution_id,
        "linked_trader_intent_id": str(trader_intent.get("trader_intent_id", "")),
        "linked_risk_review_id": str(risk_review.get("risk_review_id", "")),
        "symbol": str(trader_intent.get("symbol", "")).upper(),
        "side": side,
        "entry_type": str(trader_intent.get("entry_type", "market")).lower(),
        "volume": float(risk_review.get("suggested_lot", risk_review.get("max_lot_allowed", 0.0)) or 0.0),
        "entry_price": trader_intent.get("entry_price"),
        "stop_loss": trader_intent.get("stop_loss"),
        "take_profit": trader_intent.get("take_profit"),
        "trailing_stop": trader_intent.get("trailing_stop", {"enabled": False}),
        "valid_until": trader_intent.get("valid_until"),
        "execution_mode": execution_mode,
        "comment": comment[:160],
        "created_at": utc_now_iso(),
        "metadata": {
            "strategy_type": strategy_type,
            "strategy_group_id": str(trader_intent.get("strategy_group_id", "")),
            "source_timeframes": trader_intent.get("source_timeframes", []),
        },
    }
    constraints = trader_intent.get("execution_constraints")
    if isinstance(constraints, dict):
        payload["execution_constraints"] = constraints
    guidance = risk_review.get("execution_guidance")
    if isinstance(guidance, dict):
        preferred = str(guidance.get("preferred_entry_type", "")).strip().lower()
        if preferred in {"market", "limit", "stop"} and payload["entry_type"] == "none":
            payload["entry_type"] = preferred
    if payload["volume"] <= 0:
        payload["volume"] = float(risk_review.get("max_lot_allowed", 0.01) or 0.01)
    if payload["entry_type"] == "none":
        payload["entry_type"] = "market"
    # NOTE: risk_guidance is intentionally NOT injected into the payload;
    # it is not part of the execution_instruction schema.
    return payload


def normalize_instruction_volume(connector: MT5Connector, instruction: dict[str, Any]) -> dict[str, Any]:
    assert connector._mt5 is not None
    normalized = dict(instruction)
    symbol = str(normalized.get("symbol", "")).upper()
    if not symbol:
        return normalized
    connector.ensure_symbol(symbol)
    info = connector._mt5.symbol_info(symbol)
    if info is None:
        return normalized
    volume = float(normalized.get("volume", 0.0) or 0.0)
    min_volume = float(getattr(info, "volume_min", 0.01) or 0.01)
    max_volume = float(getattr(info, "volume_max", 0.0) or 0.0)
    step = float(getattr(info, "volume_step", 0.01) or 0.01)
    if volume <= 0:
        volume = min_volume
    steps = math.floor((volume + 1e-12) / step)
    volume = round(max(min_volume, steps * step), 8)
    if max_volume > 0:
        volume = min(volume, max_volume)
    decimals = max(0, len(str(step).split(".", 1)[1].rstrip("0")) if "." in str(step) else "")
    normalized["volume"] = round(volume, decimals)
    return normalized


def _price_decimals(info: Any) -> int:
    digits = int(getattr(info, "digits", 2) or 2)
    return max(0, digits)


def _quantize_price(value: float, tick_size: float, digits: int) -> float:
    if tick_size <= 0:
        return round(value, digits)
    ticks = round(value / tick_size)
    return round(ticks * tick_size, digits)


def normalize_instruction_prices(connector: MT5Connector, instruction: dict[str, Any]) -> dict[str, Any]:
    assert connector._mt5 is not None
    normalized = dict(instruction)
    symbol = str(normalized.get("symbol", "")).upper()
    side = str(normalized.get("side", "")).lower()
    entry_type = str(normalized.get("entry_type", "")).lower()
    if not symbol or side not in {"buy", "sell"}:
        return normalized
    connector.ensure_symbol(symbol)
    info = connector._mt5.symbol_info(symbol)
    if info is None:
        return normalized
    tick = connector.symbol_tick(symbol)
    bid = float(tick.get("bid", 0.0) or 0.0)
    ask = float(tick.get("ask", 0.0) or 0.0)
    market_price = ask if side == "buy" else bid
    digits = _price_decimals(info)
    point = float(getattr(info, "point", 0.0) or 0.0)
    tick_size = float(getattr(info, "trade_tick_size", 0.0) or point or 0.0)
    stops_level_points = float(getattr(info, "trade_stops_level", 0.0) or 0.0)
    min_stop_distance = max(tick_size, point * stops_level_points if point > 0 else tick_size)
    if market_price <= 0:
        return normalized

    entry_price_raw = float(normalized.get("entry_price", market_price) or market_price)
    entry_price = _quantize_price(entry_price_raw, tick_size, digits)

    # In lab mode, prioritize execution over pending precision when the pending price is invalid.
    if entry_type in {"limit", "stop"}:
        if side == "buy":
            invalid_pending = (entry_type == "limit" and entry_price >= ask) or (entry_type == "stop" and entry_price <= ask)
        else:
            invalid_pending = (entry_type == "limit" and entry_price <= bid) or (entry_type == "stop" and entry_price >= bid)
        if invalid_pending or abs(entry_price - market_price) < min_stop_distance:
            normalized["entry_type"] = "market"
            entry_type = "market"
            entry_price = _quantize_price(market_price, tick_size, digits)

    if entry_type == "market":
        entry_price = _quantize_price(market_price, tick_size, digits)
    normalized["entry_price"] = entry_price

    stop_loss = normalized.get("stop_loss")
    take_profit = normalized.get("take_profit")
    sl_value = float(stop_loss) if isinstance(stop_loss, (int, float)) and float(stop_loss) > 0 else None
    tp_value = float(take_profit) if isinstance(take_profit, (int, float)) and float(take_profit) > 0 else None

    # Sanity check: SL/TP deben ser precios de mercado cercanos al entry (2% para mesa scalping-intradía)
    if sl_value is not None and entry_price > 0 and abs(sl_value - entry_price) / entry_price > 0.02:
        sl_value = None
    if tp_value is not None and entry_price > 0 and abs(tp_value - entry_price) / entry_price > 0.02:
        tp_value = None

    if side == "buy":
        if sl_value is not None:
            sl_target = min(sl_value, entry_price - min_stop_distance)
            sl_target = _quantize_price(sl_target, tick_size, digits)
            if sl_target <= 0 or sl_target >= entry_price:
                sl_value = None
            else:
                sl_value = sl_target
        if tp_value is not None:
            tp_target = max(tp_value, entry_price + min_stop_distance)
            tp_target = _quantize_price(tp_target, tick_size, digits)
            if tp_target <= entry_price:
                tp_value = None
            else:
                tp_value = tp_target
    else:
        if sl_value is not None:
            sl_target = max(sl_value, entry_price + min_stop_distance)
            sl_target = _quantize_price(sl_target, tick_size, digits)
            if sl_target <= entry_price:
                sl_value = None
            else:
                sl_value = sl_target
        if tp_value is not None:
            tp_target = min(tp_value, entry_price - min_stop_distance)
            tp_target = _quantize_price(tp_target, tick_size, digits)
            if tp_target <= 0 or tp_target >= entry_price:
                tp_value = None
            else:
                tp_value = tp_target

    if sl_value is None:
        normalized.pop("stop_loss", None)
    else:
        normalized["stop_loss"] = sl_value
    if tp_value is None:
        normalized.pop("take_profit", None)
    else:
        normalized["take_profit"] = tp_value
    return normalized


def persist_execution_event(payload: dict[str, Any]) -> None:
    persist_json("execution_runtime", str(payload.get("execution_event_id", "")), payload)
    upsert_execution_event_cache(CFG["runtime_db_path"], payload)
    trigger_payload = {
        "trigger_id": str(payload.get("execution_event_id", "")),
        "symbol": str(payload.get("symbol", "")).upper(),
        "timeframe": "LIVE",
        "status": "pending",
        "priority": "high",
        "reason": f"{payload.get('event_type')}:{payload.get('status')}",
        "created_at": str(payload.get("created_at", "")),
        "linked_execution_id": str(payload.get("execution_id", "")),
    }
    persist_json("execution_triggers_runtime", str(payload.get("execution_event_id", "")), trigger_payload)
    upsert_trigger_cache(
        CFG["runtime_db_path"],
        trigger_id=str(payload.get("execution_event_id", "")),
        trigger_kind="execution",
        symbol=str(payload.get("symbol", "")),
        timeframe="LIVE",
        linked_thesis_id="",
        status="pending",
        priority="high",
        trigger_ref=str(payload.get("event_type", "")),
        reason=str(payload.get("reason", ""))[:500],
        created_at=str(payload.get("created_at", "")),
        updated_at=str(payload.get("created_at", "")),
        trigger_payload=trigger_payload,
    )


def build_execution_event(
    *,
    execution_id: str,
    linked_trader_intent_id: str,
    linked_risk_review_id: str,
    symbol: str,
    event_type: str,
    status: str,
    response: dict[str, Any] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    response = response or {}
    payload = {
        "schema_version": "1.0.0",
        "execution_event_id": f"execution_event_{uuid.uuid4().hex}",
        "execution_id": execution_id,
        "linked_trader_intent_id": linked_trader_intent_id,
        "linked_risk_review_id": linked_risk_review_id,
        "symbol": symbol.upper(),
        "event_type": event_type,
        "status": status,
        "reason": reason[:500] or str(response.get("comment", ""))[:500],
        "payload": response,
        "created_at": utc_now_iso(),
    }
    order_id = int(response.get("order", 0) or 0)
    deal_id = int(response.get("deal", 0) or 0)
    position_id = int(response.get("position", 0) or 0)
    price = response.get("price")
    volume = response.get("volume")
    if order_id > 0:
        payload["mt5_order_id"] = order_id
    if deal_id > 0:
        payload["mt5_deal_id"] = deal_id
    if position_id > 0:
        payload["mt5_position_id"] = position_id
    if isinstance(price, (int, float)) and float(price) > 0:
        payload["price"] = float(price)
    if isinstance(volume, (int, float)) and float(volume) >= 0:
        payload["volume"] = float(volume)
    return payload


def apply_post_fill_levels(
    connector: MT5Connector,
    instruction: dict[str, Any],
    response: dict[str, Any],
    linked_risk_review_id: str,
) -> dict[str, Any] | None:
    if not response.get("ok"):
        return None
    position_id = int(response.get("position", 0) or 0)
    if position_id <= 0:
        position_id = int(connector.find_open_position_id(str(instruction.get("symbol", "")), str(instruction.get("comment", ""))) or 0)
    if position_id <= 0:
        return None
    if not instruction.get("stop_loss") and not instruction.get("take_profit"):
        return None
    try:
        modify_response = connector.modify_position_levels(
            symbol=str(instruction.get("symbol", "")),
            position_id=position_id,
            stop_loss=float(instruction["stop_loss"]) if instruction.get("stop_loss") else None,
            take_profit=float(instruction["take_profit"]) if instruction.get("take_profit") else None,
        )
    except Exception as exc:
        return build_execution_event(
            execution_id=str(instruction.get("execution_id", "")),
            linked_trader_intent_id=str(instruction.get("linked_trader_intent_id", "")),
            linked_risk_review_id=linked_risk_review_id,
            symbol=str(instruction.get("symbol", "")),
            event_type="modified",
            status="bridge_error",
            reason=f"post_fill_levels_failed: {exc}",
        )
    return build_execution_event(
        execution_id=str(instruction.get("execution_id", "")),
        linked_trader_intent_id=str(instruction.get("linked_trader_intent_id", "")),
        linked_risk_review_id=linked_risk_review_id,
        symbol=str(instruction.get("symbol", "")),
        event_type="modified" if modify_response.get("ok") else "rejected",
        status="ok" if modify_response.get("ok") else "rejected",
        response=modify_response,
        reason="Post-fill SL/TP adjustment.",
    )


def submit_new_executions(connector: MT5Connector) -> dict[str, Any]:
    processed = []
    allowed_risk_decisions = {"approved", "approved_limited", "force_execute"}
    for trader_intent in load_approved_trader_intents():
        trader_intent_id = str(trader_intent.get("trader_intent_id", ""))
        if not is_operable_symbol(str(trader_intent.get("symbol", ""))):
            continue
        if not trader_intent_id or execution_exists_for_trader_intent(trader_intent_id):
            continue
        retry_state = execution_retry_state(trader_intent_id)
        if retry_state["recent_attempt"] or int(retry_state["attempts"]) >= CFG["max_retries_per_intent"]:
            continue
        risk_review = load_latest_risk_review(trader_intent_id)
        if not risk_review or str(risk_review.get("decision", "")).lower() not in allowed_risk_decisions:
            continue
        instruction = build_execution_instruction(trader_intent, risk_review)
        instruction = normalize_instruction_volume(connector, instruction)
        instruction = normalize_instruction_prices(connector, instruction)
        intended_levels = {
            "stop_loss": instruction.get("stop_loss"),
            "take_profit": instruction.get("take_profit"),
        }
        errors = validate_payload("execution_instruction.schema.json", instruction)
        if errors:
            event = build_execution_event(
                execution_id=instruction["execution_id"],
                linked_trader_intent_id=trader_intent_id,
                linked_risk_review_id=str(risk_review.get("risk_review_id", "")),
                symbol=str(trader_intent.get("symbol", "")),
                event_type="rejected",
                status="invalid_instruction",
                reason="; ".join(errors),
            )
            persist_execution_event(event)
            processed.append(event)
            continue
        try:
            response = connector.send_execution_instruction(instruction)
            event_type = "placed" if str(instruction.get("entry_type")) != "market" else "filled"
            status = "ok" if response.get("ok") else "rejected"
            event = build_execution_event(
                execution_id=instruction["execution_id"],
                linked_trader_intent_id=trader_intent_id,
                linked_risk_review_id=str(risk_review.get("risk_review_id", "")),
                symbol=str(trader_intent.get("symbol", "")),
                event_type=event_type if response.get("ok") else "rejected",
                status=status,
                response=response,
                reason=str(response.get("comment", "")),
            )
        except Exception as exc:
            event = build_execution_event(
                execution_id=instruction["execution_id"],
                linked_trader_intent_id=trader_intent_id,
                linked_risk_review_id=str(risk_review.get("risk_review_id", "")),
                symbol=str(trader_intent.get("symbol", "")),
                event_type="rejected",
                status="bridge_error",
                reason=str(exc),
            )
        validate_errors = validate_payload("execution_event.schema.json", event)
        if not validate_errors:
            persist_execution_event(event)
        persist_json("execution_instructions_runtime", instruction["execution_id"], instruction)
        processed.append(event)
        if event.get("event_type") == "filled" and event.get("status") == "ok" and (intended_levels.get("stop_loss") or intended_levels.get("take_profit")):
            post_fill_instruction = dict(instruction)
            post_fill_instruction["stop_loss"] = intended_levels.get("stop_loss")
            post_fill_instruction["take_profit"] = intended_levels.get("take_profit")
            if isinstance(response.get("price"), (int, float)) and float(response.get("price")) > 0:
                post_fill_instruction["entry_price"] = float(response.get("price"))
            post_fill_instruction = normalize_instruction_prices(connector, post_fill_instruction)
            post_fill_event = apply_post_fill_levels(
                connector,
                post_fill_instruction,
                response,
                str(risk_review.get("risk_review_id", "")),
            )
            if post_fill_event and not validate_payload("execution_event.schema.json", post_fill_event):
                persist_execution_event(post_fill_event)
                processed.append(post_fill_event)
            if post_fill_event and str(post_fill_event.get("status", "")).lower() not in {"ok"}:
                from message_utils import persist_message
                persist_message(
                    db_path=CFG["runtime_db_path"],
                    agent_role="bridge",
                    message_type="protective_update",
                    symbol=str(trader_intent.get("symbol", "")),
                    timeframe="LIVE",
                    importance="urgent",
                    linked_thesis_id=trader_intent.get("linked_thesis_id"),
                    content={
                        "display_text": "ALERTA: posici\u00f3n abierta sin protecci\u00f3n SL/TP. Post-fill adjustment fall\u00f3.",
                        "message": "El bridge no pudo aplicar SL/TP post-fill. El live_execution_trader DEBE intervenir.",
                        "execution_id": str(instruction.get("execution_id", "")),
                        "trader_intent_id": trader_intent_id,
                        "intended_stop_loss": intended_levels.get("stop_loss"),
                        "intended_take_profit": intended_levels.get("take_profit"),
                    },
                )
    return {"processed": processed, "processed_count": len(processed)}


def maintain_trailing_stops(connector: MT5Connector) -> dict[str, Any]:
    processed = []
    for position in load_open_positions():
        linked_execution_id = str(position.get("linked_execution_id", "")).strip()
        linked_trader_intent_id = str(position.get("linked_trader_intent_id", "")).strip()
        if not linked_execution_id or not linked_trader_intent_id:
            continue
        trader_path = CFG["storage_root"] / "trader_runtime" / f"{linked_trader_intent_id}.json"
        if not trader_path.exists():
            continue
        trader_intent = json.loads(trader_path.read_text(encoding="utf-8"))
        trailing = trader_intent.get("trailing_stop")
        if not isinstance(trailing, dict) or not bool(trailing.get("enabled", False)):
            continue
        activation_price = float(trailing.get("activation_price", 0.0) or 0.0)
        distance = float(trailing.get("distance", 0.0) or 0.0)
        step = float(trailing.get("step", 0.0) or 0.0)
        if activation_price <= 0 or distance <= 0 or step <= 0:
            continue
        current_price = float(position.get("price_current", 0.0) or 0.0)
        price_open = float(position.get("price_open", 0.0) or 0.0)
        current_sl = float(position.get("stop_loss", 0.0) or 0.0)
        side = str(position.get("side", "")).lower()
        if side == "buy":
            if current_price < activation_price:
                continue
            proposed_sl = current_price - distance
            if current_sl > 0 and proposed_sl <= (current_sl + step):
                continue
        else:
            if current_price > activation_price:
                continue
            proposed_sl = current_price + distance
            if current_sl > 0 and proposed_sl >= (current_sl - step):
                continue
        try:
            response = connector.modify_position_levels(
                symbol=str(position.get("symbol", "")),
                position_id=int(position.get("position_id", 0) or 0),
                stop_loss=proposed_sl,
                take_profit=float(position.get("take_profit", 0.0) or 0.0) or None,
            )
            event = build_execution_event(
                execution_id=linked_execution_id,
                linked_trader_intent_id=linked_trader_intent_id,
                linked_risk_review_id="",
                symbol=str(position.get("symbol", "")),
                event_type="trailing_updated" if response.get("ok") else "modified",
                status="ok" if response.get("ok") else "rejected",
                response=response,
                reason=f"Trailing stop updated from {current_sl or price_open} to {proposed_sl}",
            )
            if not validate_payload("execution_event.schema.json", event):
                persist_execution_event(event)
                processed.append(event)
        except Exception:
            continue
    return {"processed": processed, "processed_count": len(processed)}


def cancel_expired_orders(connector: MT5Connector) -> dict[str, Any]:
    processed = []
    now = utc_now()
    for order in load_working_orders():
        linked_trader_intent_id = str(order.get("linked_trader_intent_id", "")).strip()
        linked_execution_id = str(order.get("linked_execution_id", "")).strip()
        if not linked_trader_intent_id or not linked_execution_id:
            continue
        trader_path = CFG["storage_root"] / "trader_runtime" / f"{linked_trader_intent_id}.json"
        if not trader_path.exists():
            continue
        trader_intent = json.loads(trader_path.read_text(encoding="utf-8"))
        valid_until = str(trader_intent.get("valid_until", "")).strip()
        if not valid_until:
            continue
        try:
            valid_until_dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError:
            continue
        if valid_until_dt > now:
            continue
        try:
            response = connector.remove_order(int(order.get("order_id", 0) or 0))
            event = build_execution_event(
                execution_id=linked_execution_id,
                linked_trader_intent_id=linked_trader_intent_id,
                linked_risk_review_id="",
                symbol=str(order.get("symbol", "")),
                event_type="cancelled" if response.get("ok") else "modified",
                status="ok" if response.get("ok") else "rejected",
                response=response,
                reason="Pending order expired by valid_until.",
            )
            if not validate_payload("execution_event.schema.json", event):
                persist_execution_event(event)
                processed.append(event)
        except Exception:
            continue
    return {"processed": processed, "processed_count": len(processed)}


def runtime_loop() -> None:
    if not CFG["enabled"]:
        print("[execution-bridge] disabled")
        while True:
            time.sleep(CFG["poll_seconds"])
    connector = MT5Connector(terminal_path=MT5_CFG["terminal_path"])
    connector.connect()
    try:
        while True:
            summary = submit_new_executions(connector)
            summary["trailing"] = maintain_trailing_stops(connector)
            summary["cancelled"] = cancel_expired_orders(connector)
            processed_count = summary["processed_count"] + summary["trailing"]["processed_count"] + summary["cancelled"]["processed_count"]
            if processed_count > 0:
                print(f"[execution-bridge] processed {processed_count} execution event(s)")
            time.sleep(CFG["poll_seconds"])
    finally:
        connector.shutdown()


def main() -> None:
    try:
        runtime_loop()
    except MT5ConnectorError as exc:
        persist_json("live", "execution_bridge", {"status": "degraded", "reason": str(exc), "updated_at": utc_now_iso()})
        raise


if __name__ == "__main__":
    main()
