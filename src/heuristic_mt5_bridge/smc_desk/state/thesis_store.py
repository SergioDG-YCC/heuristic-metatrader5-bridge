"""
SMC Thesis Store — CRUD for SMC prepared-zone theses.

One thesis per (broker_server, account_login, symbol), persisted in SQLite.
No JSON fallback — SQLite is the single source of truth.

strategy_type is always "smc_prepared".
Review cadence: 4h default (not_before), 12h deadline.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.infra.storage.runtime_db import (
    load_active_smc_thesis,
    upsert_smc_thesis,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _review_seconds() -> tuple[int, int]:
    """Return (not_before_seconds, deadline_seconds)."""
    base = int(os.getenv("SMC_PERIODIC_REVIEW_SECONDS", "14400"))
    return base, base * 3


# ---------------------------------------------------------------------------
# Thesis record builder
# ---------------------------------------------------------------------------

def build_smc_thesis_record(
    symbol: str,
    analyst_output: dict[str, Any],
    prepared_zones: list[str],
    multi_tf_alignment: dict[str, Any] | None = None,
    elliott_count: dict[str, Any] | None = None,
    fibo_levels: dict[str, Any] | None = None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a complete smc_thesis_record from analyst output.

    Parameters
    ----------
    symbol           : broker symbol (exact case from broker)
    analyst_output   : JSON output from heuristic_analyst
    prepared_zones   : list of zone_ids supporting this thesis
    multi_tf_alignment: {d1, h4, h1} structure summary
    elliott_count    : output of count_waves()
    fibo_levels      : output of fibo_levels_for_structure()
    prior            : previous thesis for continuity of thesis_id
    """
    now = _utc_now()

    # Preserve thesis_id for continuity; only rotate on major bias change
    thesis_id = (
        str(prior.get("thesis_id", ""))
        if isinstance(prior, dict) and prior.get("thesis_id")
        else f"smc_thesis_{uuid.uuid4().hex}"
    )

    hint_raw = analyst_output.get("next_review_hint_seconds")
    if hint_raw is None:
        hint_raw = (analyst_output.get("review_strategy") or {}).get("next_review_hint_seconds", 0)
    hint = int(hint_raw or 0)

    base_s, deadline_s = _review_seconds()
    if hint > 0:
        not_before_s = max(3600, min(86400 * 7, hint))
    else:
        not_before_s = base_s
    deadline_s = not_before_s * 3

    # Normalise operation candidates
    raw_candidates = analyst_output.get("operation_candidates", [])
    if not isinstance(raw_candidates, list):
        raw_candidates = []
    candidates: list[dict[str, Any]] = []
    for item in raw_candidates[:10]:
        if not isinstance(item, dict):
            continue
        cand: dict[str, Any] = {}
        for price_key in ("entry_zone_high", "entry_zone_low", "stop_loss", "take_profit_1", "take_profit_2"):
            val = item.get(price_key)
            if val is not None:
                try:
                    cand[price_key] = float(val)
                except (ValueError, TypeError):
                    pass
        for str_key in (
            "rr_ratio", "stop_loss_justification", "take_profit_1_justification",
            "take_profit_2_justification", "requires_confirmation", "quality",
            "entry_model", "sl_method", "tp_method", "label", "side", "trigger",
            "source_zone_id", "trigger_type", "setup_label",
        ):
            val = item.get(str_key)
            if val is not None:
                cand[str_key] = str(val).strip()[:300]
        flags = item.get("validation_flags")
        if isinstance(flags, list):
            cand["validation_flags"] = [str(f).strip()[:80] for f in flags if str(f).strip()][:20]
        volumes = item.get("volume_options")
        if isinstance(volumes, list):
            normalized_volumes: list[float] = []
            for vol in volumes:
                try:
                    v = float(vol)
                except (TypeError, ValueError):
                    continue
                if v > 0:
                    normalized_volumes.append(round(v, 8))
            if normalized_volumes:
                cand["volume_options"] = normalized_volumes[:8]
        conf_list = item.get("confluences", [])
        if isinstance(conf_list, list):
            cand["confluences"] = [str(c).strip()[:80] for c in conf_list if str(c).strip()][:14]
        candidates.append(cand)

    bias = str(analyst_output.get("bias", "unclear"))
    status_raw = str(analyst_output.get("status", "watching")).lower()
    status = status_raw if status_raw in {"active", "watching", "prepared"} else "watching"

    validator_decision = str(analyst_output.get("validator_decision", "")).strip().lower()
    if validator_decision == "reject":
        status = "watching"
        candidates = []

    # Alternate scenarios
    raw_alt = analyst_output.get("alternate_scenarios", [])
    if not isinstance(raw_alt, list):
        raw_alt = []
    alternate_scenarios: list[Any] = []
    for s in raw_alt[:5]:
        if isinstance(s, dict):
            alternate_scenarios.append(s)
        elif str(s).strip():
            alternate_scenarios.append(str(s).strip()[:400])

    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "thesis_id": thesis_id,
        "symbol": str(symbol).upper(),
        "strategy_type": "smc_prepared",
        "bias": bias,
        "bias_confidence": str(analyst_output.get("bias_confidence") or "").strip() or None,
        "base_scenario": str(analyst_output.get("base_scenario") or analyst_output.get("summary") or "")[:2000],
        "alternate_scenarios": alternate_scenarios,
        "prepared_zones": prepared_zones,
        "primary_zone_id": str(analyst_output.get("primary_zone_id", "")).strip() or None,
        "elliott_count": elliott_count,
        "fibo_levels": fibo_levels,
        "multi_timeframe_alignment": multi_tf_alignment,
        "validation_summary": analyst_output.get("validation_summary"),
        "validator_result": analyst_output.get("validator_result"),
        "validator_decision": validator_decision or None,
        "watch_conditions": [
            str(w).strip()[:200]
            for w in analyst_output.get("watch_conditions", [])
            if str(w).strip()
        ][:15],
        "invalidations": [
            str(i).strip()[:200]
            for i in analyst_output.get("invalidations", [])
            if str(i).strip()
        ][:10],
        "operation_candidates": candidates,
        "status": status,
        "next_review_hint_seconds": hint,
        "review_strategy": analyst_output.get("review_strategy"),
        "analyst_notes": str(analyst_output.get("analyst_notes") or "")[:1000] or None,
        "watch_levels": [
            {
                "label": str(wl.get("label", "")).strip()[:80],
                "price": float(wl["price"]),
                "relation": str(wl.get("relation", "touch")).strip()[:40],
                "action_hint": str(wl.get("action_hint", "")).strip()[:120],
            }
            for wl in (analyst_output.get("watch_levels") or [])
            if isinstance(wl, dict)
            and isinstance(wl.get("price"), (int, float))
            and float(wl.get("price", 0)) > 0
        ][:20],
        "created_at": (
            str(prior.get("created_at", _utc_now_iso()))
            if isinstance(prior, dict)
            else _utc_now_iso()
        ),
        "last_review_at": _utc_now_iso(),
        "next_review_not_before": (
            (now + timedelta(seconds=not_before_s))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "review_deadline": (
            (now + timedelta(seconds=deadline_s))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "updated_at": _utc_now_iso(),
    }
    return record


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_recent_smc_thesis(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
) -> dict[str, Any] | None:
    """Load the most recent active/watching SMC thesis for a symbol."""
    rows = load_active_smc_thesis(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
    )
    return rows[0] if rows else None


def save_smc_thesis(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
    analyst_output: dict[str, Any],
    prepared_zones: list[str],
    multi_tf_alignment: dict[str, Any] | None = None,
    elliott_count: dict[str, Any] | None = None,
    fibo_levels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build, persist, and return an SMC thesis record."""
    prior = load_recent_smc_thesis(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
    )
    thesis = build_smc_thesis_record(
        symbol=symbol,
        analyst_output=analyst_output,
        prepared_zones=prepared_zones,
        multi_tf_alignment=multi_tf_alignment,
        elliott_count=elliott_count,
        fibo_levels=fibo_levels,
        prior=prior,
    )
    upsert_smc_thesis(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        thesis=thesis,
    )
    return thesis
