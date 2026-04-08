from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.infra.storage.runtime_db import (
    append_risk_event,
    list_recent_risk_events,
    load_risk_budget_state,
    load_risk_profile_state,
    upsert_risk_budget_state,
    upsert_risk_profile_state,
)
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso


_PROFILE_FACTORS: dict[int, float] = {1: 0.6, 2: 1.0, 3: 1.5, 4: 2.0}

_PROFILE_BASE_LIMITS: dict[int, dict[str, float]] = {
    1: {
        "max_drawdown_pct": 2.0,
        "max_risk_per_trade_pct": 0.30,
        "max_positions_total": 3,
        "max_positions_per_symbol": 1,
        "max_pending_orders_total": 3,
        "max_gross_exposure": 3.0,
    },
    2: {
        "max_drawdown_pct": 3.5,
        "max_risk_per_trade_pct": 0.50,
        "max_positions_total": 5,
        "max_positions_per_symbol": 2,
        "max_pending_orders_total": 5,
        "max_gross_exposure": 5.0,
    },
    3: {
        "max_drawdown_pct": 5.0,
        "max_risk_per_trade_pct": 0.75,
        "max_positions_total": 10,
        "max_positions_per_symbol": 3,
        "max_pending_orders_total": 10,
        "max_gross_exposure": 10.0,
    },
    4: {
        "max_drawdown_pct": 15.0,
        "max_risk_per_trade_pct": 2.0,
        "max_positions_total": 20,
        "max_positions_per_symbol": 5,
        "max_pending_orders_total": 20,
        "max_gross_exposure": 20.0,
    },
}


def _parse_bool(value: str, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _parse_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip() or default)
    except ValueError:
        return default


def _parse_float(value: str, default: float | None) -> float | None:
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _clamp_profile(value: int) -> int:
    return max(1, min(4, int(value or 2)))


@dataclass
class RiskKernel:
    db_path: Path
    broker_server: str
    account_login: int
    profile_global: int = 2
    profile_fast: int = 2
    profile_smc: int = 2
    fast_budget_weight: float = 1.2
    smc_budget_weight: float = 0.8
    kill_switch_enabled: bool = True
    overrides: dict[str, Any] = field(default_factory=dict)
    kill_switch_state: dict[str, Any] = field(default_factory=dict)
    usage_snapshot: dict[str, Any] = field(default_factory=dict)
    ownership_snapshot: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, *, db_path: Path, broker_server: str, account_login: int) -> "RiskKernel":
        overrides: dict[str, Any] = {
            "max_drawdown_pct": _parse_float(os.getenv("RISK_MAX_DRAWDOWN_PCT", ""), None),
            "max_risk_per_trade_pct": _parse_float(os.getenv("RISK_MAX_RISK_PER_TRADE_PCT", ""), None),
            "max_positions_total": _parse_float(os.getenv("RISK_MAX_POSITIONS_TOTAL", ""), None),
            "max_positions_per_symbol": _parse_float(os.getenv("RISK_MAX_POSITIONS_PER_SYMBOL", ""), None),
            "max_pending_orders_total": _parse_float(os.getenv("RISK_MAX_PENDING_ORDERS_TOTAL", ""), None),
            "max_gross_exposure": _parse_float(os.getenv("RISK_MAX_GROSS_EXPOSURE", ""), None),
        }
        overrides = {key: value for key, value in overrides.items() if value is not None}
        instance = cls(
            db_path=db_path,
            broker_server=str(broker_server).strip(),
            account_login=int(account_login),
            profile_global=_clamp_profile(_parse_int(os.getenv("RISK_PROFILE_GLOBAL", "2"), 2)),
            profile_fast=_clamp_profile(_parse_int(os.getenv("RISK_PROFILE_FAST", "2"), 2)),
            profile_smc=_clamp_profile(_parse_int(os.getenv("RISK_PROFILE_SMC", "2"), 2)),
            fast_budget_weight=max(0.01, float(_parse_float(os.getenv("RISK_FAST_BUDGET_WEIGHT", ""), 1.2) or 1.2)),
            smc_budget_weight=max(0.01, float(_parse_float(os.getenv("RISK_SMC_BUDGET_WEIGHT", ""), 0.8) or 0.8)),
            kill_switch_enabled=_parse_bool(os.getenv("RISK_KILL_SWITCH_ENABLED", "true"), True),
            overrides=overrides,
            kill_switch_state={
                "state": "armed",
                "reason": "",
                "tripped_at": None,
                "manual_override": False,
            },
        )
        instance.load_or_initialize()
        return instance

    def load_or_initialize(self) -> None:
        profile_state = load_risk_profile_state(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
        )
        budget_state = load_risk_budget_state(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
        )

        if profile_state:
            self.profile_global = _clamp_profile(int(profile_state.get("profile_global", self.profile_global) or self.profile_global))
            self.profile_fast = _clamp_profile(int(profile_state.get("profile_fast", self.profile_fast) or self.profile_fast))
            self.profile_smc = _clamp_profile(int(profile_state.get("profile_smc", self.profile_smc) or self.profile_smc))
            self.fast_budget_weight = max(0.01, float(profile_state.get("fast_budget_weight", self.fast_budget_weight) or self.fast_budget_weight))
            self.smc_budget_weight = max(0.01, float(profile_state.get("smc_budget_weight", self.smc_budget_weight) or self.smc_budget_weight))
            self.kill_switch_enabled = bool(profile_state.get("kill_switch_enabled", self.kill_switch_enabled))
            db_overrides = profile_state.get("overrides") if isinstance(profile_state.get("overrides"), dict) else {}
            merged = dict(db_overrides)
            merged.update(self.overrides)
            self.overrides = merged

        if budget_state:
            self.kill_switch_state = (
                budget_state.get("kill_switch_state")
                if isinstance(budget_state.get("kill_switch_state"), dict)
                else self.kill_switch_state
            )
            self.usage_snapshot = budget_state.get("usage") if isinstance(budget_state.get("usage"), dict) else {}

        self._persist_profile_state()
        self._persist_budget_state()

    def _append_event(self, event_type: str, reason: str | None = None, payload: dict[str, Any] | None = None) -> None:
        append_risk_event(
            self.db_path,
            {
                "broker_server": self.broker_server,
                "account_login": self.account_login,
                "event_type": event_type,
                "reason": reason,
                "payload": payload or {},
                "created_at": utc_now_iso(),
            },
        )

    def _persist_profile_state(self) -> None:
        upsert_risk_profile_state(
            self.db_path,
            {
                "broker_server": self.broker_server,
                "account_login": self.account_login,
                "profile_global": self.profile_global,
                "profile_fast": self.profile_fast,
                "profile_smc": self.profile_smc,
                "overrides": self.overrides,
                "fast_budget_weight": self.fast_budget_weight,
                "smc_budget_weight": self.smc_budget_weight,
                "kill_switch_enabled": self.kill_switch_enabled,
                "updated_at": utc_now_iso(),
            },
        )

    def _persist_budget_state(self) -> None:
        upsert_risk_budget_state(
            self.db_path,
            {
                "broker_server": self.broker_server,
                "account_login": self.account_login,
                "limits": self.effective_limits(),
                "allocator": self.allocator_state(),
                "usage": self.usage_snapshot,
                "kill_switch_state": self.kill_switch_state,
                "updated_at": utc_now_iso(),
            },
        )

    def _base_limits(self, profile: int) -> dict[str, float]:
        return dict(_PROFILE_BASE_LIMITS[_clamp_profile(profile)])

    def _global_limits(self) -> dict[str, float]:
        limits = self._base_limits(self.profile_global)
        for key, value in self.overrides.items():
            if value is None:
                continue
            limits[key] = float(value)
        return limits

    def allocator_state(self) -> dict[str, Any]:
        fast_score = max(0.0001, self.fast_budget_weight * _PROFILE_FACTORS[self.profile_fast])
        smc_score = max(0.0001, self.smc_budget_weight * _PROFILE_FACTORS[self.profile_smc])
        total = fast_score + smc_score
        fast_share = fast_score / total
        smc_share = smc_score / total
        return {
            "score_fast": round(fast_score, 6),
            "score_smc": round(smc_score, 6),
            "share_fast": round(fast_share, 6),
            "share_smc": round(smc_share, 6),
            "factor_fast": _PROFILE_FACTORS[self.profile_fast],
            "factor_smc": _PROFILE_FACTORS[self.profile_smc],
            "weight_fast": self.fast_budget_weight,
            "weight_smc": self.smc_budget_weight,
        }

    def _desk_effective_limits(self, desk: str, share: float) -> dict[str, float]:
        global_limits = self._global_limits()
        profile = self.profile_fast if desk == "fast" else self.profile_smc
        desk_profile_limits = self._base_limits(profile)

        allocated_positions_total = max(1, int(round(global_limits["max_positions_total"] * share)))
        allocated_pending_total = max(1, int(round(global_limits["max_pending_orders_total"] * share)))
        allocated_gross_exposure = max(0.01, float(global_limits["max_gross_exposure"] * share))
        allocated_risk_per_trade = max(0.01, float(global_limits["max_risk_per_trade_pct"] * share))

        return {
            "max_drawdown_pct": min(desk_profile_limits["max_drawdown_pct"], global_limits["max_drawdown_pct"]),
            "max_risk_per_trade_pct": min(desk_profile_limits["max_risk_per_trade_pct"], allocated_risk_per_trade),
            "max_positions_total": float(min(desk_profile_limits["max_positions_total"], allocated_positions_total)),
            "max_positions_per_symbol": float(
                min(desk_profile_limits["max_positions_per_symbol"], global_limits["max_positions_per_symbol"])
            ),
            "max_pending_orders_total": float(min(desk_profile_limits["max_pending_orders_total"], allocated_pending_total)),
            "max_gross_exposure": min(desk_profile_limits["max_gross_exposure"], allocated_gross_exposure),
        }

    def effective_limits(self) -> dict[str, Any]:
        allocator = self.allocator_state()
        return {
            "global": self._global_limits(),
            "desks": {
                "fast": self._desk_effective_limits("fast", float(allocator["share_fast"])),
                "smc": self._desk_effective_limits("smc", float(allocator["share_smc"])),
            },
        }

    def update_usage(self, *, account_payload: dict[str, Any], ownership_open: list[dict[str, Any]]) -> dict[str, Any]:
        account_state = account_payload.get("account_state", {}) if isinstance(account_payload, dict) else {}
        exposure_state = account_payload.get("exposure_state", {}) if isinstance(account_payload, dict) else {}
        positions = account_payload.get("positions", []) if isinstance(account_payload, dict) else []
        orders = account_payload.get("orders", []) if isinstance(account_payload, dict) else []

        open_positions_total = int(account_state.get("open_position_count", len(positions)) or len(positions))
        pending_orders_total = int(account_state.get("pending_order_count", len(orders)) or len(orders))
        drawdown_percent = float(account_state.get("drawdown_percent", 0.0) or 0.0)
        gross_exposure = float(exposure_state.get("gross_exposure", 0.0) or 0.0)
        if gross_exposure <= 0:
            gross_exposure = sum(abs(float(item.get("volume", 0.0) or 0.0)) for item in positions if isinstance(item, dict))

        positions_per_symbol: dict[str, int] = {}
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            symbol = str(pos.get("symbol", "")).upper()
            if not symbol:
                continue
            positions_per_symbol[symbol] = positions_per_symbol.get(symbol, 0) + 1

        desk_positions = {"fast": 0, "smc": 0}
        desk_pending = {"fast": 0, "smc": 0}
        for item in ownership_open:
            if not isinstance(item, dict):
                continue
            owner = str(item.get("desk_owner", "unassigned")).strip().lower()
            if owner not in {"fast", "smc"}:
                continue
            operation_type = str(item.get("operation_type", "")).strip().lower()
            if operation_type == "position":
                desk_positions[owner] += 1
            elif operation_type == "order":
                desk_pending[owner] += 1

        self.ownership_snapshot = {
            "open_count": len(ownership_open),
            "desk_positions": desk_positions,
            "desk_pending_orders": desk_pending,
        }
        self.usage_snapshot = {
            "drawdown_percent": drawdown_percent,
            "open_positions_total": open_positions_total,
            "pending_orders_total": pending_orders_total,
            "gross_exposure": gross_exposure,
            "positions_per_symbol": positions_per_symbol,
            "desk_positions": desk_positions,
            "desk_pending_orders": desk_pending,
            "updated_at": utc_now_iso(),
        }
        self._persist_budget_state()
        return self.usage_snapshot

    def evaluate_entry(self, *, desk: str, symbol: str) -> dict[str, Any]:
        desk = str(desk or "").strip().lower()
        if desk not in {"fast", "smc"}:
            return {"allowed": False, "reasons": ["invalid_desk"], "limits": {}, "risk_per_trade_pct": 0.0}
        limits = self.effective_limits()
        global_limits = limits["global"]
        desk_limits = limits["desks"][desk]
        usage = self.usage_snapshot or {}
        symbol_norm = str(symbol).upper()
        symbol_open_count = int((usage.get("positions_per_symbol") or {}).get(symbol_norm, 0) or 0)
        desk_positions = int((usage.get("desk_positions") or {}).get(desk, 0) or 0)
        desk_pending_orders = int((usage.get("desk_pending_orders") or {}).get(desk, 0) or 0)
        reasons: list[str] = []

        if self.kill_switch_enabled and str(self.kill_switch_state.get("state", "armed")) == "tripped":
            reasons.append("kill_switch_tripped")
        if float(usage.get("drawdown_percent", 0.0) or 0.0) > float(global_limits["max_drawdown_pct"]):
            reasons.append("drawdown_limit_breached")
        if int(usage.get("open_positions_total", 0) or 0) >= int(global_limits["max_positions_total"]):
            reasons.append("global_positions_limit")
        if symbol_open_count >= int(global_limits["max_positions_per_symbol"]):
            reasons.append("symbol_positions_limit")
        if int(usage.get("pending_orders_total", 0) or 0) >= int(global_limits["max_pending_orders_total"]):
            reasons.append("global_pending_orders_limit")
        if float(usage.get("gross_exposure", 0.0) or 0.0) >= float(global_limits["max_gross_exposure"]):
            reasons.append("global_gross_exposure_limit")
        if desk_positions >= int(desk_limits["max_positions_total"]):
            reasons.append(f"{desk}_positions_budget_limit")
        if desk_pending_orders >= int(desk_limits["max_pending_orders_total"]):
            reasons.append(f"{desk}_pending_orders_budget_limit")

        allowed = not reasons
        return {
            "allowed": allowed,
            "reasons": reasons,
            "desk": desk,
            "risk_per_trade_pct": float(desk_limits["max_risk_per_trade_pct"]),
            "limits": desk_limits,
            "global_limits": global_limits,
            "kill_switch_state": self.kill_switch_state,
        }

    def evaluate_action(self, *, action_type: str) -> dict[str, Any]:
        defensive_actions = {
            "close_position",
            "reduce_position",
            "remove_order",
            "modify_position_levels",
            "modify_order_levels",
            "trail_stop",
        }
        normalized = str(action_type or "").strip().lower()
        if normalized in defensive_actions:
            return {"allowed": True, "reason": "defensive_action_allowed"}
        if self.kill_switch_enabled and str(self.kill_switch_state.get("state", "armed")) == "tripped":
            return {"allowed": False, "reason": "kill_switch_tripped"}
        return {"allowed": True, "reason": "ok"}

    def set_profiles(
        self,
        *,
        profile_global: int | None = None,
        profile_fast: int | None = None,
        profile_smc: int | None = None,
        overrides: dict[str, Any] | None = None,
        reason: str = "api_profile_update",
    ) -> dict[str, Any]:
        previous = self.profile_state()
        if profile_global is not None:
            self.profile_global = _clamp_profile(profile_global)
        if profile_fast is not None:
            self.profile_fast = _clamp_profile(profile_fast)
        if profile_smc is not None:
            self.profile_smc = _clamp_profile(profile_smc)
        if isinstance(overrides, dict):
            cleaned = {k: v for k, v in overrides.items() if v is not None}
            self.overrides.update(cleaned)
        self._persist_profile_state()
        self._persist_budget_state()
        self._append_event(
            "profile_updated",
            reason=reason,
            payload={"previous": previous, "current": self.profile_state()},
        )
        return self.profile_state()

    def trip_kill_switch(self, *, reason: str, manual_override: bool = False) -> dict[str, Any]:
        self.kill_switch_state = {
            "state": "tripped",
            "reason": str(reason or "manual_trip"),
            "tripped_at": utc_now_iso(),
            "manual_override": bool(manual_override),
        }
        self._persist_budget_state()
        self._append_event("kill_switch_tripped", reason=reason, payload=self.kill_switch_state)
        return dict(self.kill_switch_state)

    def reset_kill_switch(self, *, reason: str | None = None, manual_override: bool = False) -> dict[str, Any]:
        self.kill_switch_state = {
            "state": "armed",
            "reason": str(reason or "manual_reset"),
            "tripped_at": None,
            "manual_override": bool(manual_override),
        }
        self._persist_budget_state()
        self._append_event("kill_switch_reset", reason=reason, payload=self.kill_switch_state)
        return dict(self.kill_switch_state)

    def profile_state(self) -> dict[str, Any]:
        return {
            "global": self.profile_global,
            "fast": self.profile_fast,
            "smc": self.profile_smc,
            "overrides": dict(self.overrides),
            "weights": {
                "fast": self.fast_budget_weight,
                "smc": self.smc_budget_weight,
            },
            "kill_switch_enabled": self.kill_switch_enabled,
        }

    def status(self) -> dict[str, Any]:
        return {
            "profile": self.profile_state(),
            "limits": self.effective_limits(),
            "allocator": self.allocator_state(),
            "usage": self.usage_snapshot,
            "ownership_usage": self.ownership_snapshot,
            "kill_switch": self.kill_switch_state,
            "events": list_recent_risk_events(
                self.db_path,
                broker_server=self.broker_server,
                account_login=self.account_login,
                limit=25,
            ),
        }
