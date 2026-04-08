from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.fast_desk.context import FastContextConfig, FastContextService
from heuristic_mt5_bridge.fast_desk.correlation.policy import FastCorrelationPolicy
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyEngine, FastCustodyPolicyConfig
from heuristic_mt5_bridge.fast_desk.execution.bridge import FastExecutionBridge
from heuristic_mt5_bridge.fast_desk.pending import FastPendingManager, FastPendingPolicyConfig
from heuristic_mt5_bridge.fast_desk.policies.entry import FastEntryPolicy
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig, FastRiskEngine
from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig, FastSetupEngine
from heuristic_mt5_bridge.fast_desk.state.desk_state import SymbolDeskState
from heuristic_mt5_bridge.fast_desk.trigger import FastTriggerConfig, FastTriggerEngine
from heuristic_mt5_bridge.fast_desk import activity_log
from heuristic_mt5_bridge.fast_desk.activity_log import PipelineStageResult
from heuristic_mt5_bridge.infra.storage import runtime_db


@dataclass
class FastTraderConfig:
    signal_cooldown: float = 60.0
    enable_pending_orders: bool = True
    require_m30_alignment: bool = True
    adoption_grace_seconds: float = 120.0


def _execution_slippage_from_spec(symbol_spec: dict[str, Any]) -> int:
    """Derive max execution slippage (points) from the symbol specification.

    Uses trade_stops_level as reference — the broker already defines the
    minimum distance for stops in points, so execution slippage should be
    a small fraction of that.  Fallback: spread × 3 or 30 points.
    """
    stops_level = int(symbol_spec.get("trade_stops_level", 0) or 0)
    if stops_level > 0:
        # 10% of stops level, clamped to [5, stops_level]
        return max(5, min(stops_level, int(stops_level * 0.10)))

    # Fallback: 3× typical spread (in points)
    spread = float(symbol_spec.get("spread", 0) or 0)
    if spread > 0:
        return max(5, int(spread * 3))

    return 30  # ultimate fallback for unknown specs


logger = logging.getLogger("fast_desk.trader")

_CURRENCY_GROUPS = {
    "EUR": "european",
    "GBP": "european",
    "CHF": "european",
    "AUD": "commodity",
    "NZD": "commodity",
    "CAD": "commodity",
    "USD": "usd_jpy",
    "JPY": "usd_jpy",
}


class FastTraderService:
    """Orchestrates context -> setup -> trigger -> execution -> custody pipeline."""

    def __init__(
        self,
        *,
        trader_config: FastTraderConfig,
        context_config: FastContextConfig,
        setup_config: FastSetupConfig,
        trigger_config: FastTriggerConfig,
        pending_config: FastPendingPolicyConfig,
        custody_config: FastCustodyPolicyConfig,
        correlation_policy: FastCorrelationPolicy | None = None,
    ) -> None:
        self.trader_config = trader_config
        self.context_service = FastContextService(context_config, correlation_policy=correlation_policy)
        self.setup_engine = FastSetupEngine(setup_config)
        self.trigger_engine = FastTriggerEngine(trigger_config)
        self.pending_manager = FastPendingManager(pending_config)
        self.custody_engine = FastCustodyEngine(custody_config)
        self.risk_engine = FastRiskEngine()
        self.entry_policy = FastEntryPolicy()
        self.execution = FastExecutionBridge()

    @staticmethod
    def _phase_is_constrained(market_phase: str) -> bool:
        return market_phase in {"ranging", "pullback_bull", "pullback_bear"}

    @staticmethod
    def _is_zone_reaction_setup(setup: Any) -> bool:
        return bool(getattr(setup, "metadata", {}).get("zone_reaction", False))

    def _setup_allowed_for_phase(self, setup: Any, context: Any) -> bool:
        if not self._phase_is_constrained(str(getattr(context, "market_phase", ""))):
            return True
        allowed_types = {
            "liquidity_sweep_reclaim",
            "order_block_retest",
            "sr_polarity_retest",
            "fvg_reaction",
        }
        if str(getattr(setup, "setup_type", "")) not in allowed_types:
            return False
        min_conf = 0.70 if self._is_zone_reaction_setup(setup) else (0.74 if str(getattr(context, "market_phase", "")) == "ranging" else 0.72)
        return float(getattr(setup, "confidence", 0.0) or 0.0) >= min_conf

    def _trigger_allowed_for_phase(self, *, setup: Any, trigger: Any, context: Any) -> bool:
        if not bool(getattr(trigger, "confirmed", False)):
            return False
        if not self._phase_is_constrained(str(getattr(context, "market_phase", ""))):
            return True
        strong_triggers = {"reclaim", "micro_bos", "displacement", "zone_reclaim", "zone_sweep_reclaim"}
        if str(getattr(trigger, "trigger_type", "")) not in strong_triggers:
            return False
        combined_conf = (
            float(getattr(setup, "confidence", 0.0) or 0.0)
            + float(getattr(trigger, "confidence", 0.0) or 0.0)
        ) / 2.0
        required = 0.72 if self._is_zone_reaction_setup(setup) else (0.76 if str(getattr(context, "market_phase", "")) == "ranging" else 0.74)
        return combined_conf >= required

    @staticmethod
    def _extract_position_side(position: dict[str, Any]) -> str | None:
        side = str(position.get("side", "")).lower().strip()
        if side in {"buy", "sell"}:
            return side
        raw_type = position.get("type")
        if raw_type in (0, "0", "buy", "long"):
            return "buy"
        if raw_type in (1, "1", "sell", "short"):
            return "sell"
        return None

    @staticmethod
    def _symbol_exposures(symbol: str, side: str) -> dict[str, int]:
        sym = str(symbol or "").upper().strip()
        if len(sym) != 6:
            return {}
        base = sym[:3]
        quote = sym[3:]
        if base not in _CURRENCY_GROUPS or quote not in _CURRENCY_GROUPS:
            return {}
        if side == "buy":
            return {base: 1, quote: -1}
        if side == "sell":
            return {base: -1, quote: 1}
        return {}

    def _correlation_conflict(
        self,
        *,
        symbol: str,
        side: str,
        open_positions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidate = self._symbol_exposures(symbol, side)
        if not candidate:
            return None
        candidate_groups = {
            _CURRENCY_GROUPS[cur]: sign
            for cur, sign in candidate.items()
            if cur in _CURRENCY_GROUPS
        }
        for position in open_positions:
            existing_symbol = str(position.get("symbol", "")).upper().strip()
            existing_side = self._extract_position_side(position)
            if not existing_symbol or existing_side is None:
                continue
            existing = self._symbol_exposures(existing_symbol, existing_side)
            if not existing:
                continue
            existing_groups = {
                _CURRENCY_GROUPS[cur]: sign
                for cur, sign in existing.items()
                if cur in _CURRENCY_GROUPS
            }
            conflicts = []
            for group, sign in candidate_groups.items():
                existing_sign = existing_groups.get(group)
                if existing_sign is not None and existing_sign != sign:
                    conflicts.append(group)
            if conflicts:
                return {
                    "reason": "correlation_conflict",
                    "existing_symbol": existing_symbol,
                    "existing_side": existing_side,
                    "conflict_groups": conflicts,
                }
        return None

    @staticmethod
    def _setup_to_zone_snapshot(setup: Any) -> dict[str, Any] | None:
        metadata = getattr(setup, "metadata", {}) if isinstance(getattr(setup, "metadata", {}), dict) else {}
        if not metadata.get("zone_reaction"):
            return None
        low = float(metadata.get("zone_bottom", 0.0) or 0.0)
        high = float(metadata.get("zone_top", 0.0) or 0.0)
        if low <= 0 and high <= 0:
            return None
        if low <= 0:
            low = high
        if high <= 0:
            high = low
        timeframe_origin = str(metadata.get("timeframe_origin", "M5") or "M5").upper()
        display_timeframes = FastSetupEngine._display_timeframes_for_origin(timeframe_origin)
        return {
            "symbol": str(getattr(setup, "symbol", "") or "").upper(),
            "source": "fast",
            "setup_type": str(getattr(setup, "setup_type", "") or ""),
            "zone_type": str(metadata.get("zone_type", "") or ""),
            "side": str(getattr(setup, "side", "") or ""),
            "timeframe_origin": timeframe_origin,
            "display_timeframes": display_timeframes,
            "price_low": round(min(low, high), 10),
            "price_high": round(max(low, high), 10),
            "entry_price": float(getattr(setup, "entry_price", 0.0) or 0.0),
            "retest_level": float(getattr(setup, "retest_level", 0.0) or 0.0),
            "confidence": float(getattr(setup, "confidence", 0.0) or 0.0),
            "htf_zone_state": str(metadata.get("htf_zone_state", "neutral") or "neutral"),
        }

    def scan_and_execute(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        spec_registry: SymbolSpecRegistry,
        account_payload_ref: Callable[[], dict[str, Any]],
        connector: Any,
        db_path: Path,
        broker_server: str,
        account_login: int,
        state: SymbolDeskState,
        risk_config: FastRiskConfig,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable[[dict[str, Any], str, str, str | None], list[dict[str, Any]]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        prefetched_tick: dict[str, Any] | None = None,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any] | None:
        pip_size = spec_registry.pip_size(symbol)
        if not pip_size:
            return None
        symbol_spec = spec_registry.get(symbol) or {}
        point_size = float(symbol_spec.get("point", pip_size) or pip_size)

        # Pipeline trace accumulator — collects every evaluated stage
        _trace: list[PipelineStageResult] = []

        candles_m1 = market_state.get_candles(symbol, "M1", 220)
        candles_m5 = market_state.get_candles(symbol, "M5", 220)
        candles_htf = market_state.get_candles(symbol, "M30", 220)
        if len(candles_m1) < 30 or len(candles_m5) < 40 or len(candles_htf) < 40:
            _ms_details = {
                "message": "insufficient_candles",
                "candle_counts": {"M1": len(candles_m1), "M5": len(candles_m5), "M30": len(candles_htf)},
            }
            logger.debug(
                "[%s] insufficient candles: M1=%d M5=%d M30=%d",
                symbol, len(candles_m1), len(candles_m5), len(candles_htf),
            )
            activity_log.emit(symbol, "context", False, _ms_details)
            _trace.append(PipelineStageResult("context", False, _ms_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "context", False)
            return None

        context = self.context_service.build_context(
            symbol=symbol,
            candles_m1=candles_m1,
            candles_m5=candles_m5,
            candles_htf=candles_htf,
            pip_size=float(pip_size),
            point_size=float(point_size),
            connector=connector if prefetched_tick is None else None,
            prefetched_tick=prefetched_tick,
            symbol_spec=symbol_spec,
            db_path=db_path,
            broker_server=broker_server,
            account_login=account_login,
        )
        if not context.allowed:
            # Transient gate — high-frequency, no value persisting to disk
            _ctx_details = {
                "reasons": context.reasons, "session": context.session_name,
                "m30_bias": context.m30_bias, "spread_pips": context.spread_pips,
                "market_phase": context.market_phase,
                "exhaustion_risk": context.exhaustion_risk,
                "warnings": context.warnings,
                "candle_counts": {"M1": len(candles_m1), "M5": len(candles_m5), "M30": len(candles_htf)},
            }
            logger.info(
                "[%s] context BLOCKED: reasons=%s warnings=%s M1=%d M5=%d M30=%d",
                symbol, context.reasons, context.warnings,
                len(candles_m1), len(candles_m5), len(candles_htf),
            )
            _trace.append(PipelineStageResult("context", False, _ctx_details))
            # Throttle activity_log for high-frequency hard gates (stale_feed,
            # symbol_closed, session_blocked) — emit at most once per 60 s per symbol.
            _NOISY_GATES = {"stale_feed", "symbol_closed", "session_blocked"}
            _reason_tags = {r.split(":")[0] for r in context.reasons}
            _is_noisy = bool(_reason_tags & _NOISY_GATES)
            if _is_noisy:
                _now_mono = time.monotonic()
                _last = getattr(self, "_last_noisy_emit", {})
                if _now_mono - _last.get(symbol, 0.0) >= 60.0:
                    activity_log.emit(symbol, "context", False, _ctx_details)
                    _last[symbol] = _now_mono
                    self._last_noisy_emit = _last  # type: ignore[attr-defined]
            else:
                activity_log.emit(symbol, "context", False, _ctx_details)
                activity_log.emit_pipeline_trace(symbol, _trace, "context", False)
            return None
        _trace.append(PipelineStageResult("context", True, {
            "session": context.session_name, "m30_bias": context.m30_bias,
            "spread_pips": context.spread_pips, "market_phase": context.market_phase,
            "warnings": context.warnings,
            "candle_counts": {"M1": len(candles_m1), "M5": len(candles_m5), "M30": len(candles_htf)},
        }))

        setups = self.setup_engine.detect_setups(
            symbol=symbol,
            candles_m5=candles_m5,
            candles_htf=candles_htf,
            pip_size=float(pip_size),
            m30_bias=context.m30_bias,
            spread_pips=context.spread_pips,
            htf_zones=context.details.get("smc_htf_zones", []),
        )
        activity_log.emit_zone_snapshot(
            symbol,
            self.setup_engine.enumerate_zones(
                symbol=symbol,
                candles_m1=candles_m1,
                candles_m5=candles_m5,
                candles_htf=candles_htf,
            ),
        )
        if not setups:
            _setup_details = {
                "message": "no_local_zone",
                "market_phase": context.market_phase,
                "warnings": context.warnings,
                "candle_counts": {"M1": len(candles_m1), "M5": len(candles_m5), "M30": len(candles_htf)},
                "m30_bias": context.m30_bias,
                "volatility_regime": context.volatility_regime,
                "exhaustion_risk": context.exhaustion_risk,
                "smc_bias": context.details.get("smc_bias", "neutral"),
                "smc_thesis_state": context.details.get("smc_thesis_state", "neutral"),
            }
            logger.info(
                "[%s] no_local_zone: phase=%s bias=%s vol=%s exh=%s M5=%d M30=%d",
                symbol, context.market_phase, context.m30_bias,
                context.volatility_regime, context.exhaustion_risk,
                len(candles_m5), len(candles_htf),
            )
            activity_log.emit(symbol, "setup", False, _setup_details)
            _trace.append(PipelineStageResult("setup", False, _setup_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "setup", False)
            return None
        _trace.append(PipelineStageResult("setup", True, {
            "patterns_found": len(setups),
            "types": [getattr(s, "setup_type", "?") for s in setups],
        }))

        now_mono = time.monotonic()
        if now_mono - state.last_signal_at < self.trader_config.signal_cooldown:
            _cd_details = {
                "remaining_s": round(self.trader_config.signal_cooldown - (now_mono - state.last_signal_at), 1),
            }
            activity_log.emit(symbol, "cooldown", False, _cd_details)
            _trace.append(PipelineStageResult("cooldown", False, _cd_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "cooldown", False)
            return None
        _trace.append(PipelineStageResult("cooldown", True, {}))

        account_payload = account_payload_ref()
        account_state = account_payload.get("account_state", {}) if isinstance(account_payload, dict) else {}
        open_positions = account_payload.get("positions", []) if isinstance(account_payload, dict) else []

        dynamic_risk = risk_config
        risk_decision: dict[str, Any] = {"allowed": True}
        if risk_gate_ref is not None:
            risk_decision = risk_gate_ref(symbol)
            if not bool(risk_decision.get("allowed", False)):
                # Global kill-switch or budget exhausted — transient, no disk write
                _rg_details = {"decision": risk_decision}
                activity_log.emit(symbol, "risk_gate", False, _rg_details)
                _trace.append(PipelineStageResult("risk_gate", False, _rg_details))
                activity_log.emit_pipeline_trace(symbol, _trace, "risk_gate", False)
                return None
            limits = risk_decision.get("limits", {}) if isinstance(risk_decision.get("limits"), dict) else {}
            global_limits = (
                risk_decision.get("global_limits", {})
                if isinstance(risk_decision.get("global_limits"), dict)
                else {}
            )
            dynamic_risk = FastRiskConfig(
                risk_per_trade_percent=float(
                    risk_decision.get("risk_per_trade_pct", risk_config.risk_per_trade_percent)
                    or risk_config.risk_per_trade_percent
                ),
                max_drawdown_percent=float(
                    global_limits.get("max_drawdown_pct", risk_config.max_drawdown_percent)
                    or risk_config.max_drawdown_percent
                ),
                max_positions_per_symbol=int(
                    limits.get("max_positions_per_symbol", risk_config.max_positions_per_symbol)
                    or risk_config.max_positions_per_symbol
                ),
                max_positions_total=int(
                    limits.get("max_positions_total", risk_config.max_positions_total)
                    or risk_config.max_positions_total
                ),
            )

        _trace.append(PipelineStageResult("risk_gate", True, {}))

        if not self.risk_engine.check_account_safe(account_state, dynamic_risk):
            # Account drawdown — transient, no disk write
            _bal = float(account_state.get("balance", 0) or 0)
            _eq = float(account_state.get("equity", 0) or 0)
            _dd = ((_bal - _eq) / _bal * 100) if _bal > 0 else 0.0
            _as_details = {"drawdown_pct": round(_dd, 2)}
            activity_log.emit(symbol, "account_safe", False, _as_details)
            _trace.append(PipelineStageResult("account_safe", False, _as_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "account_safe", False)
            return None
        _trace.append(PipelineStageResult("account_safe", True, {}))

        selected_setup = None
        selected_trigger = None
        phase_filtered = 0
        for setup in setups:
            if (
                self.trader_config.require_m30_alignment
                and context.m30_bias in {"buy", "sell"}
                and setup.side != context.m30_bias
                and not self._is_zone_reaction_setup(setup)
            ):
                continue
            if not self._setup_allowed_for_phase(setup, context):
                phase_filtered += 1
                continue
            # Exhaustion filter: high exhaustion risk requires higher confidence setups
            if context.exhaustion_risk == "high" and setup.confidence < (0.76 if self._is_zone_reaction_setup(setup) else 0.80):
                continue
            trigger = self.trigger_engine.confirm(setup=setup, candles_m1=candles_m1, pip_size=float(pip_size), context=context)
            if self._trigger_allowed_for_phase(setup=setup, trigger=trigger, context=context):
                selected_setup = setup
                selected_trigger = trigger
                break
            if trigger.confirmed:
                phase_filtered += 1

        if selected_setup is None or selected_trigger is None:
            # Either H1 alignment filtered all setups or no trigger confirmed
            setup_sides = [s.side for s in setups]
            zone_setups = [s for s in setups if self._is_zone_reaction_setup(s)]
            _trig_details = {
                "reason": "local_zone_detected_waiting_reaction" if zone_setups else "no_local_zone",
                "setups_seen": len(setups), "setup_sides": setup_sides,
                "m30_bias": context.m30_bias,
                "require_m30_alignment": self.trader_config.require_m30_alignment,
                "market_phase": context.market_phase,
                "warnings": context.warnings,
                "phase_filtered": phase_filtered,
                "zone_setup_count": len(zone_setups),
                "zone_setup_types": [s.setup_type for s in zone_setups[:6]],
            }
            activity_log.emit(symbol, "trigger", False, _trig_details)
            _trace.append(PipelineStageResult("trigger", False, _trig_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "trigger", False)
            return None
        _trace.append(PipelineStageResult("trigger", True, {
            "setup": selected_setup.setup_type,
            "trigger": selected_trigger.trigger_type,
            "side": selected_setup.side,
            "confidence": round((selected_setup.confidence + selected_trigger.confidence) / 2.0, 4),
        }))

        # FASE 4: count only fast-desk-owned positions so entry policy scope matches
        # RiskKernel desk-level limits (not all account positions).
        if ownership_open_ref is not None:
            ownership_rows = ownership_open_ref()
            fast_pos_ids, _ = self._fast_owned_sets(ownership_rows)
            fast_open_positions = [
                p for p in open_positions
                if int(p.get("position_id", 0) or 0) in fast_pos_ids
            ]
        else:
            fast_open_positions = open_positions

        allowed, _policy_reason = self.entry_policy.can_open(symbol, selected_setup.side, fast_open_positions, dynamic_risk)
        if not allowed:
            # Policy ceiling — transient, no disk write
            _ep_details = {
                "reason": _policy_reason, "open_count": len(fast_open_positions),
            }
            activity_log.emit(symbol, "entry_policy", False, _ep_details)
            _trace.append(PipelineStageResult("entry_policy", False, _ep_details))
            activity_log.emit_pipeline_trace(symbol, _trace, "entry_policy", False)
            return None
        _trace.append(PipelineStageResult("entry_policy", True, {}))

        corr_conflict = self._correlation_conflict(
            symbol=symbol,
            side=selected_setup.side,
            open_positions=fast_open_positions,
        )
        if corr_conflict is not None:
            activity_log.emit(symbol, "correlation", False, corr_conflict)
            _trace.append(PipelineStageResult("correlation", False, corr_conflict))
            activity_log.emit_pipeline_trace(symbol, _trace, "correlation", False)
            return None
        _trace.append(PipelineStageResult("correlation", True, {}))

        balance = float(account_state.get("balance", 0.0) or 0.0)
        spec = spec_registry.get(symbol) or {}
        
        # === UNIVERSAL LOT SIZE CALCULATION (MT5 compliant) ===
        # Pass symbol_spec and account_state directly - engine handles all symbol types
        volume = self.risk_engine.calculate_lot_size(
            balance,
            dynamic_risk.risk_per_trade_percent,
            selected_setup.risk_pips,
            spec,  # symbol_spec with tick_value, point, digits, contract_size
            account_state,  # for margin check
        )
        # Cap volume by symbol's volume_max to avoid broker rejections
        volume_max = float(spec.get("volume_max", 500.0) or 500.0)
        volume = min(volume, volume_max)

        entry_type = "market"
        entry_price = None
        if self.trader_config.enable_pending_orders and selected_setup.requires_pending:
            entry_type = selected_setup.pending_entry_type
            entry_price = selected_setup.entry_price

        signal_id = uuid.uuid4().hex

        try:
            result = self.execution.send_entry(
                connector,
                symbol=symbol,
                side=selected_setup.side,
                entry_type=entry_type,
                volume=volume,
                stop_loss=selected_setup.stop_loss,
                take_profit=selected_setup.take_profit,
                entry_price=entry_price,
                comment="",
                max_slippage_points=_execution_slippage_from_spec(spec),
                mt5_execute_sync=mt5_execute_sync,
            )
            outcome = "accepted" if bool(result.get("ok", False)) else "rejected"
        except Exception as exec_err:
            result = {"ok": False, "error": str(exec_err)}
            outcome = "error"
            print(f"[fast-desk] execution error ({symbol}/{selected_setup.setup_type}): {exec_err}")
        # Derive pip_value from symbol spec for the audit trail
        _tick_val = float(spec.get("tick_value", 0) or 0)
        _point = float(spec.get("point", 0) or 0)
        _digits = int(spec.get("digits", 5) or 5)
        _pip_size = _point * 10 if _digits in (3, 5) else _point
        pip_value = _tick_val * (_pip_size / _point) if _point > 0 else 0.0

        signal_payload: dict[str, Any] = {
            "signal_id": signal_id,
            "symbol": symbol,
            "side": selected_setup.side,
            "trigger": f"{selected_setup.setup_type}:{selected_trigger.trigger_type}",
            "confidence": min(1.0, round((selected_setup.confidence + selected_trigger.confidence) / 2.0, 4)),
            "entry_price": selected_setup.entry_price,
            "stop_loss": selected_setup.stop_loss,
            "take_profit": selected_setup.take_profit,
            "stop_loss_pips": selected_setup.risk_pips,
            "evidence_json": {
                "setup": selected_setup.setup_type,
                "trigger": selected_trigger.trigger_type,
                "volume_lots": volume,
                "pip_value_used": round(pip_value, 6),
                "exec_result": result,
                "context": {
                    "session": context.session_name,
                    "m30_bias": context.m30_bias,
                    "spread_pips": context.spread_pips,
                },
                "setup_meta": selected_setup.metadata,
                "trigger_meta": selected_trigger.metadata,
            },
            "generated_at": _utc_now_iso(),
            "processed_at": _utc_now_iso(),
            "outcome": outcome,
        }
        runtime_db.upsert_fast_signal(db_path, broker_server, account_login, signal_payload)

        activity_log.emit(symbol, "execution", outcome == "accepted", {
            "side": selected_setup.side, "setup": selected_setup.setup_type,
            "trigger": selected_trigger.trigger_type, "volume": volume,
            "outcome": outcome, "signal_id": signal_id,
        })

        _exec_details = {
            "side": selected_setup.side, "setup": selected_setup.setup_type,
            "trigger": selected_trigger.trigger_type, "volume": volume,
            "outcome": outcome, "signal_id": signal_id,
            "entry_price": selected_setup.entry_price,
            "stop_loss": selected_setup.stop_loss,
            "take_profit": selected_setup.take_profit,
        }
        _trace.append(PipelineStageResult("execution", outcome == "accepted", _exec_details))
        activity_log.emit_pipeline_trace(symbol, _trace, "execution", outcome == "accepted")

        self._log_event(
            db_path=db_path,
            broker_server=broker_server,
            account_login=account_login,
            symbol=symbol,
            action="open_position" if entry_type == "market" else "open_pending",
            position_id=int(result.get("position", 0) or 0) if result.get("position") else None,
            signal_id=signal_id,
            details={
                "setup": selected_setup.setup_type,
                "trigger": selected_trigger.trigger_type,
                "entry_type": entry_type,
                "volume": volume,
                "result": result,
            },
        )

        if ownership_register_ref is not None and bool(result.get("ok", False)):
            ownership_register_ref(result, symbol, selected_setup.side, signal_id)

        if bool(result.get("ok", False)):
            state.last_signal_at = now_mono
            if int(result.get("position", 0) or 0) > 0:
                state.positions_opened_today += 1
        return {
            "setup": selected_setup.setup_type,
            "trigger": selected_trigger.trigger_type,
            "entry_type": entry_type,
            "result": result,
        }

    def run_custody(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        spec_registry: SymbolSpecRegistry,
        account_payload_ref: Callable[[], dict[str, Any]],
        connector: Any,
        db_path: Path,
        broker_server: str,
        account_login: int,
        state: SymbolDeskState,
        risk_action_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        prefetched_tick: dict[str, Any] | None = None,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, int]:
        pip_size = spec_registry.pip_size(symbol)
        if not pip_size:
            return {"positions": 0, "orders": 0}

        symbol_spec = spec_registry.get(symbol) or {}
        point_size = float(symbol_spec.get("point", pip_size) or pip_size)
        candles_m1 = market_state.get_candles(symbol, "M1", 220)
        candles_m5 = market_state.get_candles(symbol, "M5", 220)
        candles_htf = market_state.get_candles(symbol, "M30", 220)
        if len(candles_m1) < 20 or len(candles_m5) < 20 or len(candles_htf) < 10:
            return {"positions": 0, "orders": 0}

        context = self.context_service.build_context(
            symbol=symbol,
            candles_m1=candles_m1,
            candles_m5=candles_m5,
            candles_htf=candles_htf,
            pip_size=float(pip_size),
            point_size=float(point_size),
            connector=connector if prefetched_tick is None else None,
            prefetched_tick=prefetched_tick,
            symbol_spec=symbol_spec,
        )

        payload = account_payload_ref()
        positions = payload.get("positions", []) if isinstance(payload, dict) else []
        orders = payload.get("orders", []) if isinstance(payload, dict) else []

        # Determine which positions/orders are inherited (need baseline protection)
        # and which are within the adoption grace window.
        # FAST operates only on what the desk-scoped payload already provides:
        # fast_owned and inherited_fast tickets.  SMC tickets are never present
        # in this payload — they are excluded upstream by account_payload_for_desk.
        inherited_pos_ids: set[int] = set()
        grace_pos_ids: set[int] = set()
        grace_order_ids: set[int] = set()
        now_utc = datetime.now(timezone.utc)
        now_ts = time.time()
        if ownership_open_ref is not None:
            for row in ownership_open_ref():
                if not isinstance(row, dict):
                    continue
                owner = str(row.get("desk_owner", "")).lower()
                status = str(row.get("ownership_status", "")).lower()
                pos_id = int(row.get("position_id", 0) or row.get("mt5_position_id", 0) or 0)
                ord_id = int(row.get("order_id", 0) or row.get("mt5_order_id", 0) or 0)
                # Contract defence: ownership_open_ref for FAST should only return
                # rows where desk_owner=="fast".  Any other row indicates a contract
                # violation upstream — ignore and log; do not attempt to manage.
                # NOTE: a legitimate inherited_fast row always has desk_owner="fast";
                # desk_owner="smc" is invalid regardless of ownership_status.
                if owner != "fast":
                    logger.warning(
                        "unexpected non-visible ticket in fast ownership ref: "
                        "owner=%s status=%s pos_id=%s ord_id=%s — skipping",
                        owner, status, pos_id or None, ord_id or None,
                    )
                    continue
                if status == "inherited_fast" and pos_id > 0:
                    inherited_pos_ids.add(pos_id)
                    # Track first-seen inherited timestamp per runtime process so
                    # restarts still get a stabilization window even when DB
                    # adopted_at is from an older session.
                    state.inherited_first_seen_at.setdefault(pos_id, now_ts)
                # Grace period for recently adopted/inherited positions
                if status == "inherited_fast" and self.trader_config.adoption_grace_seconds > 0:
                    grace_active = False
                    adopted_at_raw = str(row.get("adopted_at", "") or "").strip()
                    if adopted_at_raw:
                        try:
                            adopted_dt = datetime.fromisoformat(adopted_at_raw.replace("Z", "+00:00"))
                            grace_active = (
                                (now_utc - adopted_dt).total_seconds() < self.trader_config.adoption_grace_seconds
                            )
                        except (ValueError, TypeError):
                            grace_active = False
                    if not grace_active and pos_id > 0:
                        first_seen = float(state.inherited_first_seen_at.get(pos_id, now_ts) or now_ts)
                        grace_active = (now_ts - first_seen) < self.trader_config.adoption_grace_seconds
                    if grace_active:
                        if pos_id > 0:
                            grace_pos_ids.add(pos_id)
                        if ord_id > 0:
                            grace_order_ids.add(ord_id)

        # Tick price for pending manager — prefer pre-fetched; connector fallback for tests
        current_price = 0.0
        tick: dict[str, Any] | None = prefetched_tick
        if tick is None:
            try:
                tick = connector.symbol_tick(symbol)
            except Exception:
                tick = None
        if tick is not None:
            try:
                bid = float(tick.get("bid", 0.0) or 0.0)
                ask = float(tick.get("ask", 0.0) or 0.0)
                current_price = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
            except Exception:
                pass
        if current_price == 0.0:
            current_price = float(candles_m1[-1].get("close", 0.0) or 0.0)

        managed_positions = 0
        managed_orders = 0
        active_symbol_pos_ids: set[int] = set()

        for position in positions:
            if str(position.get("symbol", "")).upper() != symbol.upper():
                continue
            position_id = int(position.get("position_id", 0) or 0)
            if position_id > 0:
                active_symbol_pos_ids.add(position_id)

            # Inherited operations must receive immediate baseline protection before
            # regular custody decisions (which may otherwise return "hold").
            if position_id in inherited_pos_ids:
                current_sl = float(position.get("stop_loss", position.get("sl", 0.0)) or 0.0)
                current_tp = float(position.get("take_profit", position.get("tp", 0.0)) or 0.0)
                needs_initial_protection = current_sl <= 0 or current_tp <= 0
                if needs_initial_protection and position_id not in state.adopted_protection_attempted:
                    protection = self._build_initial_inherited_protection(
                        position=position,
                        candles_m5=candles_m5,
                        pip_size=float(pip_size),
                        point_size=float(point_size),
                        symbol_spec=symbol_spec,
                    )
                    if protection is not None:
                        if risk_action_ref is not None:
                            risk_action = risk_action_ref("modify_position_levels")
                            if not bool(risk_action.get("allowed", False)):
                                protection = None
                        if protection is not None:
                            result = self.execution.modify_position_levels(
                                connector,
                                symbol=symbol,
                                position_id=position_id,
                                stop_loss=protection["stop_loss"],
                                take_profit=protection["take_profit"],
                                mt5_execute_sync=mt5_execute_sync,
                            )
                            state.adopted_protection_attempted.add(position_id)
                            managed_positions += 1
                            self._log_event(
                                db_path=db_path,
                                broker_server=broker_server,
                                account_login=account_login,
                                symbol=symbol,
                                action="adopted_initial_protection",
                                position_id=position_id,
                                details={
                                    "reason": "inherited_missing_levels",
                                    "requested": protection,
                                    "result": result,
                                },
                            )
                # During grace window, inherited positions are custody-protected
                # but not eligible for aggressive actions (close/reduce/trailing).
                if position_id in grace_pos_ids:
                    continue

            decision = self.custody_engine.evaluate_position(
                position=position,
                candles_m1=candles_m1,
                candles_m5=candles_m5,
                context=context,
                pip_size=float(pip_size),
                scaled_out_position_ids=state.scaled_out_position_ids,
            )
            if decision.action == "hold":
                continue

            if risk_action_ref is not None:
                risk_action = risk_action_ref(decision.action)
                if not bool(risk_action.get("allowed", False)):
                    continue

            result = self.execution.apply_professional_custody(
                connector,
                decision=decision,
                position=position,
                max_slippage_points=_execution_slippage_from_spec(symbol_spec),
                mt5_execute_sync=mt5_execute_sync,
            )
            if decision.action == "reduce":
                state.scaled_out_position_ids.add(position_id)
            if decision.action == "close":
                state.positions_closed_today += 1
            managed_positions += 1
            self._log_event(
                db_path=db_path,
                broker_server=broker_server,
                account_login=account_login,
                symbol=symbol,
                action=decision.action,
                position_id=position_id,
                details={"reason": decision.reason, "result": result},
            )

        if self.trader_config.enable_pending_orders:
            for order in orders:
                if str(order.get("symbol", "")).upper() != symbol.upper():
                    continue
                order_id = int(order.get("order_id", 0) or 0)
                if order_id in grace_order_ids:  # recently adopted — observe before managing
                    continue

                pending_decision = self.pending_manager.evaluate(
                    order=order,
                    context=context,
                    current_price=current_price,
                    pip_size=float(pip_size),
                )
                if pending_decision.action == "hold":
                    continue

                if risk_action_ref is not None:
                    risk_action = risk_action_ref("remove_order" if pending_decision.action == "cancel" else "modify_order_levels")
                    if not bool(risk_action.get("allowed", False)):
                        continue

                if pending_decision.action == "cancel":
                    result = self.execution.cancel_pending_order(
                        connector, order_id=order_id, mt5_execute_sync=mt5_execute_sync
                    )
                elif pending_decision.action == "modify":
                    result = self.execution.modify_pending_order(
                        connector,
                        symbol=symbol,
                        order_id=order_id,
                        price_open=pending_decision.price_open,
                        stop_loss=pending_decision.stop_loss,
                        take_profit=pending_decision.take_profit,
                        mt5_execute_sync=mt5_execute_sync,
                    )
                else:
                    continue

                managed_orders += 1
                self._log_event(
                    db_path=db_path,
                    broker_server=broker_server,
                    account_login=account_login,
                    symbol=symbol,
                    action=f"pending_{pending_decision.action}",
                    details={"order_id": order_id, "reason": pending_decision.reason, "result": result},
                )

        # Cleanup stale per-position runtime memory.
        for stale_pos_id in list(state.inherited_first_seen_at):
            if stale_pos_id not in active_symbol_pos_ids:
                state.inherited_first_seen_at.pop(stale_pos_id, None)
                state.adopted_protection_attempted.discard(stale_pos_id)

        return {"positions": managed_positions, "orders": managed_orders}

    def _build_initial_inherited_protection(
        self,
        *,
        position: dict[str, Any],
        candles_m5: list[dict[str, Any]],
        pip_size: float,
        point_size: float,
        symbol_spec: dict[str, Any],
    ) -> dict[str, float] | None:
        side = str(position.get("side", "")).lower()
        if side not in {"buy", "sell"}:
            return None

        open_price = float(position.get("price_open", 0.0) or 0.0)
        current_price = float(position.get("price_current", open_price) or open_price)
        if open_price <= 0 or current_price <= 0 or pip_size <= 0:
            return None

        atr = max(self.custody_engine._atr(candles_m5, 14), pip_size * 10)
        risk_pips = max((atr / pip_size) * 1.2, 12.0)
        risk_distance = risk_pips * pip_size

        min_points = int(symbol_spec.get("trade_stops_level", symbol_spec.get("stops_level_points", 0)) or 0)
        min_dist = max(min_points * point_size, pip_size * 2)

        if side == "buy":
            sl = open_price - risk_distance
            sl = min(sl, current_price - min_dist)
            tp = open_price + (risk_distance * 2.0)
            tp = max(tp, current_price + min_dist)
        else:
            sl = open_price + risk_distance
            sl = max(sl, current_price + min_dist)
            tp = open_price - (risk_distance * 2.0)
            tp = min(tp, current_price - min_dist)

        if sl <= 0 or tp <= 0:
            return None
        if side == "buy" and sl >= current_price:
            return None
        if side == "sell" and sl <= current_price:
            return None
        return {"stop_loss": float(sl), "take_profit": float(tp)}

    @staticmethod
    def _fast_owned_sets(ownership_rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
        position_ids: set[int] = set()
        order_ids: set[int] = set()
        for row in ownership_rows:
            if not isinstance(row, dict):
                continue
            desk_owner = str(row.get("desk_owner", "")).lower()
            ownership_status = str(row.get("ownership_status", "")).lower()
            if desk_owner != "fast" and ownership_status not in {"inherited_fast", "fast_owned"}:
                continue
            pos_id = int(row.get("position_id", 0) or row.get("mt5_position_id", 0) or 0)
            ord_id = int(row.get("order_id", 0) or row.get("mt5_order_id", 0) or 0)
            if pos_id > 0:
                position_ids.add(pos_id)
            if ord_id > 0:
                order_ids.add(ord_id)
        return position_ids, order_ids

    @staticmethod
    def _log_event(
        *,
        db_path: Path,
        broker_server: str,
        account_login: int,
        symbol: str,
        action: str,
        details: dict[str, Any],
        position_id: int | None = None,
        signal_id: str | None = None,
    ) -> None:
        runtime_db.append_fast_trade_log(
            db_path,
            broker_server,
            account_login,
            {
                "log_id": uuid.uuid4().hex,
                "symbol": str(symbol).upper(),
                "action": str(action),
                "position_id": int(position_id) if position_id is not None else None,
                "signal_id": signal_id,
                "details_json": details,
                "logged_at": _utc_now_iso(),
            },
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
