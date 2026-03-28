from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from heuristic_mt5_bridge.core.config.env import getenv, load_env_file, repo_root_from
from heuristic_mt5_bridge.core.llm.model_discovery import LLMModelDiscovery
from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeService, build_runtime_service


def utc_now_iso() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

_service: CoreRuntimeService | None = None
_runtime_task: asyncio.Task[Any] | None = None
_STATUS_INTERVAL = 30  # seconds between periodic console status lines


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_smc_llm_model() -> str:
    """Return the active SMC LLM model, preferring runtime config over process env."""
    if _service and hasattr(_service, "smc_desk_config") and _service.smc_desk_config:
        runtime_model = getattr(_service.smc_desk_config, "llm_model", None)
        if isinstance(runtime_model, str) and runtime_model.strip():
            return runtime_model.strip()
    return os.environ.get("SMC_LLM_MODEL", "gemma-3-4b-it-qat")


def _print_startup_banner(svc: CoreRuntimeService, host: str, port: int) -> None:
    bi = svc.broker_identity
    broker = bi.get("broker_name", bi.get("broker_server", "unknown"))
    server = bi.get("broker_server", "unknown")
    account = bi.get("account_login", "unknown")
    # balance/currency come from account_state (populated after bootstrap)
    acct_st = svc.account_payload.get("account_state", {}) if isinstance(svc.account_payload, dict) else {}
    balance = acct_st.get("balance", "")
    currency = acct_st.get("currency", "")
    symbols = svc.subscribed_universe
    timeframes = svc.config.watch_timeframes
    db_path = svc.config.runtime_db_path
    smc = "enabled" if svc._smc_desk is not None else "disabled"

    sep = "=" * 60
    print(sep, flush=True)
    print(f"  Heuristic MT5 Bridge — Control Plane", flush=True)
    print(sep, flush=True)
    print(f"  broker   : {broker} ({server})", flush=True)
    print(f"  account  : {account}  {balance} {currency}", flush=True)
    print(f"  symbols  : {', '.join(symbols) if symbols else '(none)'}", flush=True)
    print(f"  tf       : {', '.join(timeframes)}", flush=True)
    print(f"  smc_desk : {smc}", flush=True)
    print(f"  db       : {db_path}", flush=True)
    print(f"  endpoint : http://{host}:{port}", flush=True)
    print(sep, flush=True)


async def _console_status_loop(svc: CoreRuntimeService) -> None:
    try:
        while True:
            await asyncio.sleep(_STATUS_INTERVAL)
            state = svc.health
            status = state.get("status", "?")
            market = state.get("market_state", "up")
            indicator = state.get("indicator_bridge", "up")
            account_st = state.get("account_state", "up")
            symbol_count = len(svc.subscribed_universe)
            positions_count = 0
            orders_count = 0
            if isinstance(svc.account_payload, dict):
                exp = svc.account_payload.get("exposure_state") or {}
                positions_count = int(exp.get("open_position_count", 0) or 0)
                orders_count = len(svc.account_payload.get("orders") or [])
            print(
                f"[{_now_utc()}] status={status} | market={market} | "
                f"indicator={indicator} | account={account_st} | "
                f"symbols={symbol_count} | positions={positions_count} | orders={orders_count}",
                flush=True,
            )
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _service, _runtime_task
    repo_root = Path(repo_root_from(__file__))
    env_values = load_env_file(repo_root / ".env") or {}
    host = getenv("CONTROL_PLANE_HOST", env_values, "0.0.0.0").strip() or "0.0.0.0"
    port = int(getenv("CONTROL_PLANE_PORT", env_values, "8765"))

    print(f"[{_now_utc()}] bootstrapping runtime...", flush=True)
    _service = await build_runtime_service(repo_root)
    await _service.bootstrap()
    _print_startup_banner(_service, host, port)

    _status_task = asyncio.create_task(_console_status_loop(_service), name="console_status")
    _runtime_task = asyncio.create_task(_service.run_forever(), name="core_runtime")
    try:
        yield
    finally:
        _status_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await _status_task
        if _runtime_task and not _runtime_task.done():
            _runtime_task.cancel()
            try:
                await _runtime_task
            except (asyncio.CancelledError, Exception):
                pass
        if _service:
            await _service.shutdown()
        print(f"[{_now_utc()}] control plane shut down.", flush=True)


app = FastAPI(title="Heuristic MT5 Bridge — Control Plane", lifespan=lifespan)


def _require_service() -> CoreRuntimeService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return _service


def _feed_row_for_symbol_timeframe(
    svc: CoreRuntimeService,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    for row in svc.feed_status_rows:
        if (
            str(row.get("symbol", "")).upper() == symbol
            and str(row.get("timeframe", "")).upper() == timeframe
        ):
            return row
    return None


def _to_float_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None


def _build_tick_stream_payload(
    svc: CoreRuntimeService,
    *,
    symbol: str,
    timeframe: str,
    live_tick: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feed_row = _feed_row_for_symbol_timeframe(svc, symbol, timeframe)
    candles = svc.market_state.get_candles(symbol, timeframe, bars=1)
    last_candle = candles[-1] if candles else None

    bid = _to_float_or_none((live_tick or {}).get("bid"))
    ask = _to_float_or_none((live_tick or {}).get("ask"))
    if bid is None:
        bid = _to_float_or_none(feed_row.get("bid") if isinstance(feed_row, dict) else None)
    if ask is None:
        ask = _to_float_or_none(feed_row.get("ask") if isinstance(feed_row, dict) else None)
    spread = round(ask - bid, 10) if bid is not None and ask is not None else None
    if spread is not None and spread < 0:
        spread = None

    bar_payload: dict[str, Any] | None = None
    if isinstance(last_candle, dict):
        bar_payload = {
            "timestamp": last_candle.get("timestamp"),
            "open": last_candle.get("open"),
            "high": last_candle.get("high"),
            "low": last_candle.get("low"),
            "close": last_candle.get("close"),
            "tick_volume": last_candle.get("tick_volume"),
        }

    return {
        "status": "success",
        "symbol": symbol,
        "timeframe": timeframe,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "last_bar_time": bar_payload.get("timestamp") if isinstance(bar_payload, dict) else None,
        "bar": bar_payload,
        "feed_status": str(feed_row.get("feed_status", "unknown")) if isinstance(feed_row, dict) else "unknown",
        "tick_time": (live_tick or {}).get("time"),
        "updated_at": utc_now_iso(),
    }


class SubscribeRequest(BaseModel):
    symbol: str


class DeskAssignmentRequest(BaseModel):
    desks: list[str]


class OwnershipReassignRequest(BaseModel):
    position_id: int | None = None
    order_id: int | None = None
    target_owner: str
    reevaluation_required: bool = False
    reason: str | None = None


class RiskProfileUpdateRequest(BaseModel):
    profile_global: int | None = None
    profile_fast: int | None = None
    profile_smc: int | None = None
    overrides: dict[str, Any] | None = None
    reason: str | None = None


class KillSwitchRequest(BaseModel):
    reason: str | None = None
    manual_override: bool = False


# ---------------------------------------------------------------------------
# Configuration API Request Models
# ---------------------------------------------------------------------------

class LLMModelSetRequest(BaseModel):
    model_id: str


class SMCConfigUpdateRequest(BaseModel):
    max_candidates: int | None = None
    min_rr: float | None = None
    next_review_hint_seconds: int | None = None
    d1_bars: int | None = None
    h4_bars: int | None = None
    h1_bars: int | None = None
    llm_enabled: bool | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int | None = None
    llm_max_tokens: int | None = None
    llm_temperature: float | None = None
    spread_tolerance: str | None = None
    spread_thresholds: dict[str, dict[str, float]] | None = None


class FastConfigUpdateRequest(BaseModel):
    scan_interval: float | None = None
    guard_interval: float | None = None
    signal_cooldown: float | None = None
    risk_per_trade_percent: float | None = None
    max_positions_per_symbol: int | None = None
    max_positions_total: int | None = None
    max_lot_size: float | None = None
    min_signal_confidence: float | None = None
    atr_multiplier_sl: float | None = None
    rr_ratio: float | None = None
    min_rr: float | None = None
    spread_tolerance: str | None = None
    require_h1_alignment: bool | None = None
    enable_pending_orders: bool | None = None
    enable_structural_trailing: bool | None = None
    enable_atr_trailing: bool | None = None
    enable_scale_out: bool | None = None
    pending_ttl_seconds: int | None = None
    allowed_sessions: list[str] | None = None
    spread_thresholds: dict[str, dict[str, float]] | None = None


class OwnershipConfigUpdateRequest(BaseModel):
    auto_adopt_foreign: bool | None = None
    history_retention_days: int | None = None


class RiskConfigUpdateRequest(BaseModel):
    profile_global: int | None = None
    profile_fast: int | None = None
    profile_smc: int | None = None
    fast_budget_weight: float | None = None
    smc_budget_weight: float | None = None
    kill_switch_enabled: bool | None = None
    overrides: dict[str, float] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/status")
async def status() -> dict[str, Any]:
    return _require_service().build_live_state()


@app.get("/chart/{symbol}/{timeframe}")
async def chart(symbol: str, timeframe: str, bars: int = 200) -> dict[str, Any]:
    svc = _require_service()
    ctx = svc.market_state.build_chart_context(symbol.upper(), timeframe.upper())
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"No chart data for {symbol}/{timeframe}")
    candles = svc.market_state.get_candles(symbol.upper(), timeframe.upper(), bars=bars)
    return {"chart_context": ctx, "candles": candles}


@app.get("/specs/{symbol}")
async def specs_symbol(symbol: str) -> dict[str, Any]:
    svc = _require_service()
    spec = svc.spec_registry.get(symbol.upper())
    if spec is None:
        raise HTTPException(status_code=404, detail=f"No spec for {symbol}")
    return spec


@app.get("/specs")
async def specs_all() -> dict[str, Any]:
    return _require_service().spec_registry.all_specs()


@app.get("/account")
async def account() -> dict[str, Any]:
    return _require_service().account_payload or {}


@app.get("/positions")
async def positions() -> dict[str, Any]:
    """Returns open positions list + pending orders list."""
    svc = _require_service()
    if not isinstance(svc.account_payload, dict):
        return {"positions": [], "orders": []}
    return {
        "positions": svc.account_payload.get("positions") or [],
        "orders": svc.account_payload.get("orders") or [],
    }


@app.get("/exposure")
async def exposure() -> dict[str, Any]:
    """Returns aggregate exposure state (gross/net volume, floating P&L by symbol)."""
    svc = _require_service()
    if isinstance(svc.account_payload, dict):
        return svc.account_payload.get("exposure_state") or {}
    return {}


@app.get("/catalog")
async def catalog() -> dict[str, Any]:
    svc = _require_service()
    return {"symbols": svc.symbol_catalog, "status": svc.symbol_catalog_status}


@app.post("/subscribe")
async def subscribe(req: SubscribeRequest) -> dict[str, Any]:
    svc = _require_service()
    changed = await svc.subscribe_symbol(req.symbol.upper())
    return {"symbol": req.symbol.upper(), "changed": changed, "subscribed_universe": svc.subscribed_universe}


@app.post("/unsubscribe")
async def unsubscribe(req: SubscribeRequest) -> dict[str, Any]:
    svc = _require_service()
    changed = await svc.unsubscribe_symbol(req.symbol.upper())
    return {"symbol": req.symbol.upper(), "changed": changed, "subscribed_universe": svc.subscribed_universe}


# ── Desk Assignments ──────────────────────────────────────────────────────────

@app.get("/api/v1/symbols/desk-assignments")
async def get_desk_assignments() -> dict[str, Any]:
    svc = _require_service()
    return {"assignments": svc.get_all_symbol_desk_assignments()}


@app.put("/api/v1/symbols/{symbol}/desks")
async def set_symbol_desks(symbol: str, req: DeskAssignmentRequest) -> dict[str, Any]:
    svc = _require_service()
    sym = symbol.upper()
    if sym not in svc.subscribed_universe:
        raise HTTPException(status_code=404, detail=f"{sym} is not subscribed")
    valid_desks = {"fast", "smc"}
    desks = {d.lower() for d in req.desks} & valid_desks
    if not desks:
        raise HTTPException(status_code=400, detail=f"Must assign at least one desk from {sorted(valid_desks)}")
    await svc.set_symbol_desks(sym, desks)
    return {"symbol": sym, "desks": sorted(desks)}


@app.get("/ownership")
async def ownership_all() -> dict[str, Any]:
    return _require_service().ownership_all()


@app.get("/ownership/open")
async def ownership_open() -> dict[str, Any]:
    return _require_service().ownership_open()


@app.get("/ownership/history")
async def ownership_history() -> dict[str, Any]:
    return _require_service().ownership_history()


@app.post("/ownership/reassign")
async def ownership_reassign(req: OwnershipReassignRequest) -> dict[str, Any]:
    if req.position_id is None and req.order_id is None:
        raise HTTPException(status_code=400, detail="Either position_id or order_id is required")
    try:
        return _require_service().ownership_reassign(
            target_owner=req.target_owner,
            position_id=req.position_id,
            order_id=req.order_id,
            reevaluation_required=req.reevaluation_required,
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/risk/status")
async def risk_status() -> dict[str, Any]:
    return _require_service().risk_status_payload()


@app.get("/risk/limits")
async def risk_limits() -> dict[str, Any]:
    return _require_service().risk_limits_payload()


@app.get("/risk/profile")
async def risk_profile() -> dict[str, Any]:
    return _require_service().risk_profile_payload()


@app.put("/risk/profile")
async def risk_profile_update(req: RiskProfileUpdateRequest) -> dict[str, Any]:
    try:
        return _require_service().update_risk_profile(
            profile_global=req.profile_global,
            profile_fast=req.profile_fast,
            profile_smc=req.profile_smc,
            overrides=req.overrides,
            reason=req.reason or "api_profile_update",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/risk/kill-switch/trip")
async def risk_kill_switch_trip(req: KillSwitchRequest) -> dict[str, Any]:
    reason = req.reason or "manual_trip"
    try:
        return _require_service().trip_risk_kill_switch(
            reason=reason,
            manual_override=req.manual_override,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/risk/kill-switch/reset")
async def risk_kill_switch_reset(req: KillSwitchRequest) -> dict[str, Any]:
    try:
        return _require_service().reset_risk_kill_switch(
            reason=req.reason,
            manual_override=req.manual_override,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Configuration API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/llm/models")
async def list_llm_models() -> dict[str, Any]:
    """List available LLM models from LocalAI."""
    localai_url = os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
    discovery = LLMModelDiscovery(localai_base_url=localai_url)
    
    try:
        models = discovery.list_models()
        return {
            "status": "success",
            "models": [m.to_dict() for m in models],
            "count": len(models),
        }
    except RuntimeError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "models": [],
            "count": 0,
        }


@app.get("/api/v1/llm/status")
async def llm_status() -> dict[str, Any]:
    """Get LLM service status and current configuration."""
    localai_url = os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
    discovery = LLMModelDiscovery(localai_base_url=localai_url)
    status = discovery.get_status()

    current_model = _current_smc_llm_model()

    return {
        "status": "success",
        "localai_url": localai_url,
        "default_model": status.default_model,
        "current_model": current_model,
        "llm_enabled": os.getenv("SMC_LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
        "available": status.available,
        "models_count": status.models_count,
    }


@app.put("/api/v1/llm/models/default")
async def set_default_llm_model(req: LLMModelSetRequest) -> dict[str, Any]:
    """Set default LLM model for SMC Desk (runtime only).

    Does NOT change LocalAI configuration — only updates runtime config so the
    bridge uses this model for SMC validation. LocalAI must already have it loaded.
    """
    if not req.model_id or not req.model_id.strip():
        return {
            "status": "error",
            "error": "model_id is required",
            "model_id": req.model_id,
        }

    model_id = req.model_id.strip()

    # Update runtime config if SMC Desk is active
    if _service and hasattr(_service, "smc_desk_config") and _service.smc_desk_config:
        _service.smc_desk_config.llm_model = model_id

    os.environ["SMC_LLM_MODEL"] = model_id

    print(f"[INFO] LLM model changed to: {model_id} (runtime only)", flush=True)

    return {
        "status": "success",
        "model_id": model_id,
        "message": f"LLM model changed to {model_id}. Runtime only — LocalAI must have this model loaded.",
    }


@app.get("/api/v1/config/smc")
async def get_smc_config() -> dict[str, Any]:
    """Get current SMC Desk configuration."""
    svc = _require_service()
    
    # Try to get config from running service
    if hasattr(svc, "smc_desk_config") and svc.smc_desk_config:
        if hasattr(svc.smc_desk_config, "to_dict"):
            config_dict = svc.smc_desk_config.to_dict()
        else:
            config_dict = {}
        
        return {
            "status": "success",
            "config": config_dict,
        }
    
    # Fallback: return default config from env vars
    # This allows WebUI to show/edit config even if SMC Desk is not enabled
    return {
        "status": "success",
        "config": {
            "llm_model": os.getenv("SMC_LLM_MODEL", "gemma-3-4b-it-qat"),
            "llm_enabled": os.getenv("SMC_LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
            "llm_timeout_seconds": int(os.getenv("SMC_LLM_TIMEOUT_SECONDS", "60")),
            "llm_max_tokens": int(os.getenv("SMC_LLM_MAX_TOKENS", "500")),
            "llm_temperature": float(os.getenv("SMC_LLM_TEMPERATURE", "0.1")),
            "max_candidates": int(os.getenv("SMC_HEURISTIC_MAX_CANDIDATES", "3")),
            "min_rr": float(os.getenv("SMC_MIN_RR", "3.0")),
            "spread_tolerance": os.getenv("SMC_SPREAD_TOLERANCE", "high"),
        },
    }


@app.put("/api/v1/config/smc")
async def update_smc_config(req: SMCConfigUpdateRequest) -> dict[str, Any]:
    """Update SMC Desk configuration at runtime."""
    svc = _require_service()
    if not hasattr(svc, "smc_desk_config") or not svc.smc_desk_config:
        # Desk inactive: persist to process env so next start picks it up
        _SMC_ENV_MAP = {
            "llm_model": "SMC_LLM_MODEL",
            "llm_enabled": "SMC_LLM_ENABLED",
            "llm_timeout_seconds": "SMC_LLM_TIMEOUT_SECONDS",
            "llm_max_tokens": "SMC_LLM_MAX_TOKENS",
            "llm_temperature": "SMC_LLM_TEMPERATURE",
            "max_candidates": "SMC_HEURISTIC_MAX_CANDIDATES",
            "min_rr": "SMC_MIN_RR",
            "spread_tolerance": "SMC_SPREAD_TOLERANCE",
        }
        for field, env_key in _SMC_ENV_MAP.items():
            value = getattr(req, field, None)
            if value is not None:
                os.environ[env_key] = str(value)
        return {
            "status": "success",
            "config": {
                "llm_model": os.environ.get("SMC_LLM_MODEL", "gemma-3-4b-it-qat"),
                "llm_enabled": os.environ.get("SMC_LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
                "llm_timeout_seconds": int(os.environ.get("SMC_LLM_TIMEOUT_SECONDS", "60")),
                "llm_max_tokens": int(os.environ.get("SMC_LLM_MAX_TOKENS", "500")),
                "llm_temperature": float(os.environ.get("SMC_LLM_TEMPERATURE", "0.1")),
                "max_candidates": int(os.environ.get("SMC_HEURISTIC_MAX_CANDIDATES", "3")),
                "min_rr": float(os.environ.get("SMC_MIN_RR", "3.0")),
                "spread_tolerance": os.environ.get("SMC_SPREAD_TOLERANCE", "high"),
            },
            "message": "SMC Desk not active. Config saved in process env — restart required to persist to .env.",
        }

    # Validate spread_tolerance
    if req.spread_tolerance is not None and req.spread_tolerance not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="spread_tolerance must be 'low', 'medium', or 'high'")
    
    # Validate spread_thresholds structure
    if req.spread_thresholds is not None:
        _VALID_LEVELS = {"low", "medium", "high"}
        _VALID_CLASSES = {"forex_major", "forex_minor", "metals", "indices", "crypto", "other"}
        for level, classes in req.spread_thresholds.items():
            if level not in _VALID_LEVELS:
                raise HTTPException(status_code=422, detail=f"Invalid threshold level: {level}")
            if not isinstance(classes, dict):
                raise HTTPException(status_code=422, detail=f"Threshold values for '{level}' must be a dict")
            for cls_name, val in classes.items():
                if cls_name not in _VALID_CLASSES:
                    raise HTTPException(status_code=422, detail=f"Invalid asset class: {cls_name}")
                if not isinstance(val, (int, float)) or val <= 0:
                    raise HTTPException(status_code=422, detail=f"Threshold for {level}.{cls_name} must be > 0")

    # Update config fields that are provided
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    
    for key, value in update_data.items():
        if hasattr(svc.smc_desk_config, key):
            setattr(svc.smc_desk_config, key, value)
    
    return {
        "status": "success",
        "config": svc.smc_desk_config.to_dict() if hasattr(svc.smc_desk_config, "to_dict") else update_data,
        "message": "SMC configuration updated (runtime only, restart to persist to .env)",
    }


@app.get("/api/v1/config/fast")
async def get_fast_config() -> dict[str, Any]:
    """Get current Fast Desk configuration."""
    svc = _require_service()
    
    # Try to get config from running service
    if hasattr(svc, "fast_desk_config") and svc.fast_desk_config:
        if hasattr(svc.fast_desk_config, "to_dict"):
            config_dict = svc.fast_desk_config.to_dict()
        else:
            config_dict = {}
        
        return {
            "status": "success",
            "config": config_dict,
        }
    
    # Fallback: return default config from env vars
    # This allows WebUI to show/edit config even if Fast Desk is not enabled
    return {
        "status": "success",
        "config": {
            "scan_interval": float(os.getenv("FAST_TRADER_SCAN_INTERVAL", os.getenv("FAST_DESK_SCAN_INTERVAL", "5.0"))),
            "guard_interval": float(os.getenv("FAST_TRADER_GUARD_INTERVAL", os.getenv("FAST_DESK_CUSTODY_INTERVAL", "2.0"))),
            "signal_cooldown": float(os.getenv("FAST_TRADER_SIGNAL_COOLDOWN", os.getenv("FAST_DESK_SIGNAL_COOLDOWN", "60.0"))),
            "risk_per_trade_percent": float(os.getenv("FAST_TRADER_RISK_PERCENT", os.getenv("FAST_DESK_RISK_PERCENT", "1.0"))),
            "max_positions_per_symbol": int(os.getenv("FAST_TRADER_MAX_POSITIONS_PER_SYMBOL", os.getenv("FAST_DESK_MAX_POSITIONS_PER_SYMBOL", "1"))),
            "max_positions_total": int(os.getenv("FAST_TRADER_MAX_POSITIONS_TOTAL", os.getenv("FAST_DESK_MAX_POSITIONS_TOTAL", "4"))),
            "max_lot_size": float(os.getenv("FAST_TRADER_MAX_LOT_SIZE", os.getenv("FAST_DESK_MAX_LOT_SIZE", "10.0"))),
            "min_signal_confidence": float(os.getenv("FAST_TRADER_MIN_CONFIDENCE", os.getenv("FAST_DESK_MIN_CONFIDENCE", "0.60"))),
            "atr_multiplier_sl": float(os.getenv("FAST_TRADER_ATR_MULTIPLIER_SL", os.getenv("FAST_DESK_ATR_MULTIPLIER_SL", "1.5"))),
            "rr_ratio": float(os.getenv("FAST_TRADER_RR_RATIO", os.getenv("FAST_DESK_RR_RATIO", "3.0"))),
            "min_rr": float(os.getenv("FAST_TRADER_MIN_RR", os.getenv("FAST_DESK_MIN_RR", "3.0"))),
            "spread_tolerance": os.getenv("FAST_TRADER_SPREAD_TOLERANCE", os.getenv("FAST_DESK_SPREAD_TOLERANCE", "medium")),
            "allowed_sessions": os.getenv("FAST_TRADER_ALLOWED_SESSIONS", os.getenv("FAST_DESK_ALLOWED_SESSIONS", "london,overlap,new_york")).split(","),
        },
    }


@app.put("/api/v1/config/fast")
async def update_fast_config(req: FastConfigUpdateRequest) -> dict[str, Any]:
    """Update Fast Desk configuration at runtime."""
    svc = _require_service()
    if not hasattr(svc, "fast_desk_config") or not svc.fast_desk_config:
        # Desk inactive: persist to process env so next start picks it up
        _FAST_ENV_MAP = {
            "scan_interval": "FAST_TRADER_SCAN_INTERVAL",
            "guard_interval": "FAST_TRADER_GUARD_INTERVAL",
            "signal_cooldown": "FAST_TRADER_SIGNAL_COOLDOWN",
            "risk_per_trade_percent": "FAST_TRADER_RISK_PERCENT",
            "max_positions_per_symbol": "FAST_TRADER_MAX_POSITIONS_PER_SYMBOL",
            "max_positions_total": "FAST_TRADER_MAX_POSITIONS_TOTAL",
            "max_lot_size": "FAST_TRADER_MAX_LOT_SIZE",
            "min_signal_confidence": "FAST_TRADER_MIN_CONFIDENCE",
            "atr_multiplier_sl": "FAST_TRADER_ATR_MULTIPLIER_SL",
            "rr_ratio": "FAST_TRADER_RR_RATIO",
            "min_rr": "FAST_TRADER_MIN_RR",
            "spread_tolerance": "FAST_TRADER_SPREAD_TOLERANCE",
        }
        for field, env_key in _FAST_ENV_MAP.items():
            value = getattr(req, field, None)
            if value is not None:
                os.environ[env_key] = str(value)
        if req.allowed_sessions is not None:
            os.environ["FAST_TRADER_ALLOWED_SESSIONS"] = ",".join(req.allowed_sessions)
        return {
            "status": "success",
            "config": {
                "scan_interval": float(os.environ.get("FAST_TRADER_SCAN_INTERVAL", "5.0")),
                "guard_interval": float(os.environ.get("FAST_TRADER_GUARD_INTERVAL", "2.0")),
                "signal_cooldown": float(os.environ.get("FAST_TRADER_SIGNAL_COOLDOWN", "60.0")),
                "risk_per_trade_percent": float(os.environ.get("FAST_TRADER_RISK_PERCENT", "1.0")),
                "max_positions_per_symbol": int(os.environ.get("FAST_TRADER_MAX_POSITIONS_PER_SYMBOL", "1")),
                "max_positions_total": int(os.environ.get("FAST_TRADER_MAX_POSITIONS_TOTAL", "4")),
                "max_lot_size": float(os.environ.get("FAST_TRADER_MAX_LOT_SIZE", "10.0")),
                "min_signal_confidence": float(os.environ.get("FAST_TRADER_MIN_CONFIDENCE", "0.60")),
                "atr_multiplier_sl": float(os.environ.get("FAST_TRADER_ATR_MULTIPLIER_SL", "1.5")),
                "rr_ratio": float(os.environ.get("FAST_TRADER_RR_RATIO", "3.0")),
                "min_rr": float(os.environ.get("FAST_TRADER_MIN_RR", "3.0")),
                "spread_tolerance": os.environ.get("FAST_TRADER_SPREAD_TOLERANCE", "medium"),
                "allowed_sessions": os.environ.get("FAST_TRADER_ALLOWED_SESSIONS", "london,overlap,new_york").split(","),
            },
            "message": "Fast Desk not active. Config saved in process env — restart required to persist to .env.",
        }

    # Validate spread_tolerance
    if req.spread_tolerance is not None and req.spread_tolerance not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="spread_tolerance must be 'low', 'medium', or 'high'")
    
    # Validate allowed_sessions
    _VALID_SESSIONS = {"tokyo", "london", "overlap", "new_york", "all_markets", "global"}
    if req.allowed_sessions is not None:
        invalid = [s for s in req.allowed_sessions if s not in _VALID_SESSIONS]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Invalid sessions: {invalid}. Valid: {sorted(_VALID_SESSIONS)}")

    # Validate spread_thresholds structure
    if req.spread_thresholds is not None:
        _VALID_LEVELS = {"low", "medium", "high"}
        _VALID_CLASSES = {"forex_major", "forex_minor", "metals", "indices", "crypto", "other"}
        for level, classes in req.spread_thresholds.items():
            if level not in _VALID_LEVELS:
                raise HTTPException(status_code=422, detail=f"Invalid threshold level: {level}")
            if not isinstance(classes, dict):
                raise HTTPException(status_code=422, detail=f"Threshold values for '{level}' must be a dict")
            for cls_name, val in classes.items():
                if cls_name not in _VALID_CLASSES:
                    raise HTTPException(status_code=422, detail=f"Invalid asset class: {cls_name}")
                if not isinstance(val, (int, float)) or val <= 0:
                    raise HTTPException(status_code=422, detail=f"Threshold for {level}.{cls_name} must be > 0")

    # Update config fields that are provided
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    
    for key, value in update_data.items():
        if key == "allowed_sessions":
            svc.fast_desk_config.allowed_sessions = tuple(value)
        elif hasattr(svc.fast_desk_config, key):
            setattr(svc.fast_desk_config, key, value)
    
    # Propagate context_config changes to workers if available
    if hasattr(svc, "fast_desk_service") and svc.fast_desk_service:
        fast_svc = svc.fast_desk_service
        if hasattr(fast_svc, "update_context_config"):
            fast_svc.update_context_config(svc.fast_desk_config)

    return {
        "status": "success",
        "config": svc.fast_desk_config.to_dict() if hasattr(svc.fast_desk_config, "to_dict") else update_data,
        "message": "Fast Desk configuration updated (runtime only)",
    }


@app.get("/api/v1/fast/diag/{symbol}")
async def fast_diag(symbol: str) -> dict[str, Any]:
    """Diagnostic endpoint: show lot-size calculation and recent signals for a symbol.

    Does NOT execute anything. Useful for debugging why fast_desk_signals == 0.
    """
    svc = _require_service()
    symbol = symbol.upper()

    # --- spec ---
    spec = svc.spec_registry.get(symbol) or {}
    pip_size = svc.spec_registry.pip_size(symbol) or 0.0
    point_size = float(spec.get("point", pip_size) or pip_size)
    tick_value = float(spec.get("tick_value", pip_size) or pip_size)
    volume_min = float(spec.get("volume_min", 0.01) or 0.01)
    volume_max = float(spec.get("volume_max", 500.0) or 500.0)
    volume_step = float(spec.get("volume_step", 0.01) or 0.01)

    # --- account ---
    account_state: dict[str, Any] = {}
    if isinstance(svc.account_payload, dict):
        account_state = svc.account_payload.get("account_state") or {}
    balance = float(account_state.get("balance", 0.0) or 0.0)

    # --- risk config ---
    fd_cfg = svc.fast_desk_config
    risk_pct = float(getattr(fd_cfg, "risk_per_trade_percent", 1.0)) if fd_cfg else 1.0

    # --- lot size simulation (same formula as trader/service.py) ---
    pip_per_point = float(pip_size) / float(point_size) if point_size > 0 else 1.0
    pip_value = tick_value * pip_per_point

    def _calc_lots(sl_pips: float) -> dict[str, Any]:
        if balance <= 0 or sl_pips <= 0 or pip_value <= 0:
            return {"lots": 0.01, "blocked": "degenerate inputs"}
        rp = min(risk_pct, 2.0)
        risk_amount = balance * rp / 100.0
        raw = risk_amount / (sl_pips * pip_value)
        capped_engine = max(0.01, min(50.0, raw))
        capped_final = min(capped_engine, volume_max)
        return {
            "risk_amount_usd": round(risk_amount, 2),
            "raw_lots": round(raw, 4),
            "after_engine_cap_50": round(capped_engine, 2),
            "after_volume_max_cap": round(capped_final, 2),
            "volume_max": volume_max,
        }

    lot_sim_10pip = _calc_lots(10.0)
    lot_sim_50pip = _calc_lots(50.0)
    lot_sim_100pip = _calc_lots(100.0)

    # --- recent signals from DB ---
    recent_signals: list[dict[str, Any]] = []
    db_path = svc.config.runtime_db_path
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            """
            SELECT signal_id, side, trigger, outcome, confidence,
                   stop_loss_pips, generated_at, evidence_json
            FROM fast_desk_signals
            WHERE symbol = ?
            ORDER BY generated_at DESC
            LIMIT 10
            """,
            (symbol,),
        )
        for row in cur.fetchall():
            d = dict(row)
            if d.get("evidence_json"):
                try:
                    d["evidence_json"] = json.loads(d["evidence_json"])
                except Exception:
                    pass
            recent_signals.append(d)
        con.close()
    except Exception as db_err:
        recent_signals = [{"error": str(db_err)}]

    return {
        "symbol": symbol,
        "spec": {
            "pip_size": pip_size,
            "point_size": point_size,
            "tick_value": tick_value,
            "pip_value_per_lot": round(pip_value, 6),
            "pip_per_point_multiplier": pip_per_point,
            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,
        },
        "account": {
            "balance": balance,
            "risk_pct": risk_pct,
        },
        "lot_size_simulation": {
            "sl_10_pips": lot_sim_10pip,
            "sl_50_pips": lot_sim_50pip,
            "sl_100_pips": lot_sim_100pip,
        },
        "recent_signals_last10": recent_signals,
    }


@app.get("/api/v1/config/ownership")
async def get_ownership_config() -> dict[str, Any]:
    """Get current Ownership Registry configuration."""
    svc = _require_service()
    if not hasattr(svc, "ownership_registry") or not svc.ownership_registry:
        return {
            "status": "not_configured",
            "config": {},
        }
    
    if hasattr(svc.ownership_registry, "to_dict"):
        config_dict = svc.ownership_registry.to_dict()
    else:
        config_dict = {
            "auto_adopt_foreign": svc.ownership_registry.auto_adopt_foreign,
            "history_retention_days": svc.ownership_registry.history_retention_days,
        }
    
    return {
        "status": "success",
        "config": config_dict,
    }


@app.put("/api/v1/config/ownership")
async def update_ownership_config(req: OwnershipConfigUpdateRequest) -> dict[str, Any]:
    """Update Ownership Registry configuration at runtime."""
    svc = _require_service()
    if not hasattr(svc, "ownership_registry") or not svc.ownership_registry:
        raise HTTPException(status_code=503, detail="Ownership registry not initialized")
    
    if hasattr(svc.ownership_registry, "reconfigure"):
        svc.ownership_registry.reconfigure(
            auto_adopt_foreign=req.auto_adopt_foreign,
            history_retention_days=req.history_retention_days,
        )
    else:
        # Direct attribute update
        if req.auto_adopt_foreign is not None:
            svc.ownership_registry.auto_adopt_foreign = req.auto_adopt_foreign
        if req.history_retention_days is not None:
            svc.ownership_registry.history_retention_days = req.history_retention_days
    
    return {
        "status": "success",
        "config": svc.ownership_registry.to_dict() if hasattr(svc.ownership_registry, "to_dict") else {
            "auto_adopt_foreign": svc.ownership_registry.auto_adopt_foreign,
            "history_retention_days": svc.ownership_registry.history_retention_days,
        },
        "message": "Ownership configuration updated",
    }


@app.get("/api/v1/config/risk")
async def get_risk_config() -> dict[str, Any]:
    """Get current RiskKernel configuration."""
    svc = _require_service()
    if not hasattr(svc, "risk_kernel") or not svc.risk_kernel:
        return {
            "status": "not_configured",
            "config": {},
        }
    
    if hasattr(svc.risk_kernel, "to_dict"):
        config_dict = svc.risk_kernel.to_dict()
    else:
        config_dict = {
            "profile_global": svc.risk_kernel.profile_global,
            "profile_fast": svc.risk_kernel.profile_fast,
            "profile_smc": svc.risk_kernel.profile_smc,
        }
    
    return {
        "status": "success",
        "config": config_dict,
    }


@app.put("/api/v1/config/risk")
async def update_risk_config(req: RiskConfigUpdateRequest) -> dict[str, Any]:
    """Update RiskKernel configuration at runtime."""
    svc = _require_service()
    if not hasattr(svc, "risk_kernel") or not svc.risk_kernel:
        raise HTTPException(status_code=503, detail="RiskKernel not initialized")
    
    rk = svc.risk_kernel
    
    # Direct attribute update (RiskKernel is a dataclass)
    if req.profile_global is not None:
        rk.profile_global = max(1, min(4, int(req.profile_global)))
    if req.profile_fast is not None:
        rk.profile_fast = max(1, min(4, int(req.profile_fast)))
    if req.profile_smc is not None:
        rk.profile_smc = max(1, min(4, int(req.profile_smc)))
    if req.fast_budget_weight is not None:
        rk.fast_budget_weight = max(0.01, float(req.fast_budget_weight))
    if req.smc_budget_weight is not None:
        rk.smc_budget_weight = max(0.01, float(req.smc_budget_weight))
    if req.kill_switch_enabled is not None:
        rk.kill_switch_enabled = bool(req.kill_switch_enabled)
    if req.overrides is not None:
        _VALID_OVERRIDE_KEYS = {"max_drawdown_pct", "max_risk_per_trade_pct", "max_positions_total",
                                "max_positions_per_symbol", "max_pending_orders_total", "max_gross_exposure"}
        invalid_keys = [k for k in req.overrides if k not in _VALID_OVERRIDE_KEYS]
        if invalid_keys:
            raise HTTPException(status_code=422, detail=f"Invalid override keys: {invalid_keys}. Valid: {sorted(_VALID_OVERRIDE_KEYS)}")
        rk.overrides.update({k: float(v) for k, v in req.overrides.items() if v is not None})
    
    # Persist changes to DB
    try:
        rk._persist_profile_state()
        rk._append_event("config_updated", reason="api_put_request")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Risk config applied in memory but DB persistence failed: {exc}") from exc
    
    return {
        "status": "success",
        "config": rk.to_dict() if hasattr(rk, "to_dict") else {
            "profile_global": rk.profile_global,
            "profile_fast": rk.profile_fast,
            "profile_smc": rk.profile_smc,
            "fast_budget_weight": rk.fast_budget_weight,
            "smc_budget_weight": rk.smc_budget_weight,
            "kill_switch_enabled": rk.kill_switch_enabled,
        },
        "message": "RiskKernel configuration updated",
    }


# ---------------------------------------------------------------------------
# LLM Configuration Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/llm/models")
async def list_llm_models() -> dict[str, Any]:
    """List available LLM models from LocalAI."""
    try:
        localai_url = os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
        discovery = LLMModelDiscovery(localai_base_url=localai_url)
        models = discovery.list_models()
        return {
            "status": "success",
            "models": [m.to_dict() for m in models],
            "count": len(models),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "models": [],
            "count": 0,
        }


@app.get("/api/v1/llm/status")
async def llm_status() -> dict[str, Any]:
    """Get LLM service status and current configuration."""
    try:
        localai_url = os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
        discovery = LLMModelDiscovery(localai_base_url=localai_url)
        status = discovery.get_status()
        current_model = _current_smc_llm_model()
        
        return {
            "status": "success",
            "localai_url": localai_url,
            "default_model": status.default_model,
            "current_model": current_model,
            "llm_enabled": os.getenv("SMC_LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
            "available": status.available,
            "models_count": status.models_count,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "localai_url": os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080"),
            "default_model": None,
            "current_model": _current_smc_llm_model(),
            "llm_enabled": False,
            "available": False,
            "models_count": 0,
        }


class LLMModelSetRequest(BaseModel):
    model_id: str


@app.put("/api/v1/llm/models/default")
async def set_default_llm_model(req: LLMModelSetRequest) -> dict[str, Any]:
    """Set default LLM model for SMC Desk (runtime only).
    
    This does NOT change LocalAI configuration - it only updates the runtime
    config so the bridge uses a different model for SMC validation.
    LocalAI must already have the model loaded.
    """
    try:
        # Validate model_id is not empty
        if not req.model_id or not req.model_id.strip():
            return {
                "status": "error",
                "error": "model_id is required",
                "model_id": req.model_id,
            }
        model_id = req.model_id.strip()

        if _service and hasattr(_service, "smc_desk_config") and _service.smc_desk_config:
            _service.smc_desk_config.llm_model = model_id
        os.environ["SMC_LLM_MODEL"] = model_id

        # Just return success - the model name will be used by SMC Desk
        # Note: This is runtime-only. To persist, update .env SMC_LLM_MODEL
        print(f"[INFO] LLM model changed to: {model_id} (runtime only)")
        
        return {
            "status": "success",
            "model_id": model_id,
            "message": f"LLM model changed to {model_id}. Note: This is runtime only. LocalAI must have this model loaded.",
        }
    except Exception as e:
        print(f"[WARNING] LLM model change failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "model_id": req.model_id,
            "message": "LLM model change failed. This is non-critical - SMC Desk will continue using current model.",
        }


# ---------------------------------------------------------------------------
# Desk Enable / Disable Endpoints
# ---------------------------------------------------------------------------

class DeskEnabledRequest(BaseModel):
    enabled: bool


@app.put("/api/v1/config/fast/enabled")
async def set_fast_desk_enabled(req: DeskEnabledRequest) -> dict[str, Any]:
    """Enable or disable the Fast Desk. Requires restart to fully apply."""
    os.environ["FAST_DESK_ENABLED"] = "true" if req.enabled else "false"
    return {
        "status": "success",
        "enabled": req.enabled,
        "message": f"Fast Desk {'enabled' if req.enabled else 'disabled'} in process env. Restart required to apply.",
    }


@app.put("/api/v1/config/smc/enabled")
async def set_smc_desk_enabled(req: DeskEnabledRequest) -> dict[str, Any]:
    """Enable or disable the SMC Desk. Requires restart to fully apply."""
    os.environ["SMC_SCANNER_ENABLED"] = "true" if req.enabled else "false"
    return {
        "status": "success",
        "enabled": req.enabled,
        "message": f"SMC Desk {'enabled' if req.enabled else 'disabled'} in process env. Restart required to apply.",
    }


# ---------------------------------------------------------------------------
# Feed Health & Desk Status Endpoints (Phase 2)
# ---------------------------------------------------------------------------

@app.get("/api/v1/feed-health")
async def feed_health() -> dict[str, Any]:
    """Get detailed feed health for all subscribed symbols."""
    try:
        svc = _require_service()
        feed_status = getattr(svc, "feed_status_rows", [])
        return {
            "status": "success",
            "feed_status": feed_status if isinstance(feed_status, list) else [],
            "updated_at": utc_now_iso(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "feed_status": [],
            "updated_at": utc_now_iso(),
        }


@app.get("/api/v1/desk-status")
async def desk_status() -> dict[str, Any]:
    """Get status of both Fast and SMC desks."""
    try:
        svc = _require_service()
        
        # Fast Desk status
        fast_desk_enabled = hasattr(svc, "_fast_desk") and svc._fast_desk is not None
        fast_config = None
        if fast_desk_enabled:
            try:
                fast_config = svc.fast_desk_config.to_dict() if hasattr(svc.fast_desk_config, "to_dict") else {}
            except Exception:
                fast_config = {}

        # SMC Desk status
        smc_desk_enabled = hasattr(svc, "_smc_desk") and svc._smc_desk is not None
        smc_config = None
        if smc_desk_enabled:
            try:
                smc_config = svc.smc_desk_config.to_dict() if hasattr(svc.smc_desk_config, "to_dict") else {}
            except Exception:
                smc_config = {}
        
        return {
            "status": "success",
            "fast_desk": {
                "enabled": fast_desk_enabled,
                "workers": len(getattr(svc, "subscribed_universe", [])) if fast_desk_enabled else 0,
                "config": fast_config,
            },
            "smc_desk": {
                "enabled": smc_desk_enabled,
                "scanner_active": smc_desk_enabled,
                "config": smc_config,
            },
            "updated_at": utc_now_iso(),
        }
    except Exception as e:
        # Log full error for debugging
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] /api/v1/desk-status failed: {error_detail}")
        
        return {
            "status": "error",
            "error": str(e),
            "detail": error_detail,
            "fast_desk": {"enabled": False, "workers": 0, "config": None},
            "smc_desk": {"enabled": False, "scanner_active": False, "config": None},
            "updated_at": utc_now_iso(),
        }


# ---------------------------------------------------------------------------
# Fast Desk — Activity & Signal Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/fast/activity")
async def fast_activity(limit: int = 50) -> dict[str, Any]:
    """Ring-buffer activity feed — shows which gate blocked each scan cycle."""
    from heuristic_mt5_bridge.fast_desk import activity_log
    return {
        "status": "success",
        "events": activity_log.recent(min(limit, 200)),
        "per_symbol_summary": activity_log.per_symbol_summary(),
        "updated_at": utc_now_iso(),
    }


@app.get("/api/v1/fast/activity/{symbol}")
async def fast_activity_symbol(symbol: str, limit: int = 50) -> dict[str, Any]:
    """Ring-buffer activity feed for a specific symbol."""
    from heuristic_mt5_bridge.fast_desk import activity_log
    sym = symbol.upper()
    return {
        "status": "success",
        "symbol": sym,
        "events": activity_log.recent_for_symbol(sym, min(limit, 200)),
        "updated_at": utc_now_iso(),
    }


@app.get("/api/v1/fast/signals")
async def fast_signals(limit: int = 50) -> dict[str, Any]:
    """Recent Fast Desk signals from DB (those that reached execution)."""
    svc = _require_service()
    db_path = svc.config.runtime_db_path
    signals: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM fast_desk_signals ORDER BY generated_at DESC LIMIT ?",
            (min(limit, 200),),
        )
        for row in cur.fetchall():
            d = dict(row)
            if d.get("evidence_json"):
                try:
                    d["evidence_json"] = json.loads(d["evidence_json"])
                except Exception:
                    pass
            signals.append(d)
        con.close()
    except Exception as e:
        signals = [{"error": str(e)}]
    return {"status": "success", "signals": signals, "updated_at": utc_now_iso()}


@app.get("/api/v1/fast/trade-log")
async def fast_trade_log(limit: int = 50) -> dict[str, Any]:
    """Recent Fast Desk trade actions (open, close, reduce, etc.)."""
    svc = _require_service()
    db_path = svc.config.runtime_db_path
    events: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM fast_desk_trade_log ORDER BY logged_at DESC LIMIT ?",
            (min(limit, 200),),
        )
        for row in cur.fetchall():
            d = dict(row)
            if d.get("details_json"):
                try:
                    d["details_json"] = json.loads(d["details_json"])
                except Exception:
                    pass
            events.append(d)
        con.close()
    except Exception as e:
        events = [{"error": str(e)}]
    return {"status": "success", "events": events, "updated_at": utc_now_iso()}


# ---------------------------------------------------------------------------
# Fast Desk — Pipeline Trace SSE (stage-by-stage visualisation)
# ---------------------------------------------------------------------------

@app.get("/api/v1/fast/pipeline")
async def fast_pipeline(limit: int = 60) -> dict[str, Any]:
    """Initial snapshot of recent pipeline traces (REST, for first render)."""
    from heuristic_mt5_bridge.fast_desk import activity_log
    return {
        "status": "success",
        "traces": activity_log.pipeline_recent(min(limit, 200)),
        "cursor": activity_log.pipeline_cursor(),
        "updated_at": utc_now_iso(),
    }


async def _pipeline_sse_generator(interval: float = 1.0):
    """Yield incremental pipeline traces as SSE events."""
    from heuristic_mt5_bridge.fast_desk import activity_log
    cursor = activity_log.pipeline_cursor()
    try:
        while True:
            traces, cursor = activity_log.pipeline_traces_since(cursor, limit=50)
            payload = json.dumps({"traces": traces, "cursor": cursor})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


@app.get("/events/fast/pipeline")
async def events_fast_pipeline(interval: float = 1.0) -> StreamingResponse:
    """SSE stream of incremental pipeline traces (1 Hz default)."""
    return StreamingResponse(
        _pipeline_sse_generator(interval=max(0.5, interval)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# SMC Desk — Thesis, Zone & Event Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/smc/theses")
async def smc_theses() -> dict[str, Any]:
    """Active + watching SMC theses from DB."""
    svc = _require_service()
    db_path = svc.config.runtime_db_path
    bi = svc.broker_identity
    broker_server = str(bi.get("broker_server", "")).strip()
    account_login = int(bi.get("account_login", 0) or 0)
    from heuristic_mt5_bridge.infra.storage.runtime_db import load_active_smc_thesis
    theses = load_active_smc_thesis(
        db_path, broker_server=broker_server, account_login=account_login,
    )
    # Decode nested JSON fields for frontend convenience
    for t in theses:
        for jf in ("operation_candidates_json", "watch_conditions_json",
                    "invalidations_json", "prepared_zones_json",
                    "alternate_scenarios_json", "watch_levels_json",
                    "validation_summary_json", "validator_result_json",
                    "elliott_count_json", "fibo_levels_json", "multi_tf_alignment_json"):
            raw = t.get(jf)
            if isinstance(raw, str):
                try:
                    t[jf] = json.loads(raw)
                except Exception:
                    pass
    return {"status": "success", "theses": theses, "updated_at": utc_now_iso()}


@app.get("/api/v1/smc/zones")
async def smc_zones(symbol: str | None = None) -> dict[str, Any]:
    """Active + approaching SMC zones from DB."""
    svc = _require_service()
    db_path = svc.config.runtime_db_path
    bi = svc.broker_identity
    broker_server = str(bi.get("broker_server", "")).strip()
    account_login = int(bi.get("account_login", 0) or 0)
    from heuristic_mt5_bridge.infra.storage.runtime_db import load_active_smc_zones
    zones = load_active_smc_zones(
        db_path, broker_server=broker_server, account_login=account_login,
        symbol=symbol.upper() if symbol else None,
    )
    for z in zones:
        raw = z.get("confluences_json")
        if isinstance(raw, str):
            try:
                z["confluences_json"] = json.loads(raw)
            except Exception:
                pass
    return {"status": "success", "zones": zones, "updated_at": utc_now_iso()}


@app.get("/api/v1/smc/events")
async def smc_events(limit: int = 100) -> dict[str, Any]:
    """Recent SMC scanner events (zone_approaching, sweep_detected, etc.)."""
    svc = _require_service()
    db_path = svc.config.runtime_db_path
    events: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM smc_events_log ORDER BY created_at DESC LIMIT ?",
            (min(limit, 500),),
        )
        for row in cur.fetchall():
            d = dict(row)
            if d.get("payload_json"):
                try:
                    d["payload_json"] = json.loads(d["payload_json"])
                except Exception:
                    pass
            events.append(d)
        con.close()
    except Exception as e:
        events = [{"error": str(e)}]
    return {"status": "success", "events": events, "updated_at": utc_now_iso()}


# ---------------------------------------------------------------------------
# SSE Generator
# ---------------------------------------------------------------------------

async def _sse_generator(interval: float) -> AsyncGenerator[str, None]:
    svc = _require_service()
    try:
        while True:
            state = svc.build_live_state()
            yield f"data: {json.dumps(state)}\n\n"
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


async def _ticks_sse_generator(symbol: str, timeframe: str, interval: float) -> AsyncGenerator[str, None]:
    svc = _require_service()
    normalized_symbol = str(symbol).upper().strip()
    normalized_timeframe = str(timeframe).upper().strip()
    try:
        while True:
            if normalized_symbol not in set(svc.subscribed_universe):
                payload = {
                    "status": "error",
                    "error": f"symbol_not_subscribed:{normalized_symbol}",
                    "symbol": normalized_symbol,
                    "timeframe": normalized_timeframe,
                    "updated_at": utc_now_iso(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                return

            live_tick: dict[str, Any] | None = None
            try:
                live_tick_result = await svc._mt5_call(svc.connector.symbol_tick, normalized_symbol)
                if isinstance(live_tick_result, dict):
                    live_tick = live_tick_result
            except Exception:
                live_tick = None

            payload = _build_tick_stream_payload(
                svc,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                live_tick=live_tick,
            )
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


@app.get("/events")
async def events(interval: float = 1.0) -> StreamingResponse:
    _require_service()
    return StreamingResponse(
        _sse_generator(interval=max(0.2, interval)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/events/ticks/{symbol}")
async def events_ticks(symbol: str, timeframe: str = "H1", interval: float = 1.0) -> StreamingResponse:
    svc = _require_service()
    normalized_symbol = str(symbol).upper().strip()
    normalized_timeframe = str(timeframe).upper().strip()

    if normalized_timeframe not in set(svc.config.watch_timeframes):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe '{normalized_timeframe}'. Allowed: {', '.join(svc.config.watch_timeframes)}",
        )
    if normalized_symbol not in set(svc.subscribed_universe):
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{normalized_symbol}' is not subscribed.",
        )

    return StreamingResponse(
        _ticks_sse_generator(
            normalized_symbol,
            normalized_timeframe,
            interval=max(0.2, interval),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    repo_root = Path(repo_root_from(__file__))
    env_values = load_env_file(repo_root / ".env") or {}
    host = getenv("CONTROL_PLANE_HOST", env_values, "0.0.0.0").strip() or "0.0.0.0"
    port = int(getenv("CONTROL_PLANE_PORT", env_values, "8765"))
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] starting uvicorn on {host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
