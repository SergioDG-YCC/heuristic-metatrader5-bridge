from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.shared.time.utc import iso_to_datetime, utc_now, utc_now_iso


def default_common_files_root() -> Path:
    appdata = os.getenv("APPDATA", "")
    if appdata:
        return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "llm_mt5_bridge"
    return Path("storage") / "mt5_common_fallback"


def resolve_common_files_root(configured_path: str | None = None) -> Path:
    raw = str(configured_path or os.getenv("MT5_COMMON_FILES_ROOT", "")).strip()
    if raw:
        return Path(raw)
    return default_common_files_root()


def _normalize_snapshot(payload: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(payload.get("symbol", "")).strip().upper()
    timeframe = str(payload.get("timeframe", "")).strip().upper()
    if not symbol or not timeframe:
        return None
    request_id = str(payload.get("request_id", "")).strip() or f"ind_{uuid.uuid4().hex}"
    computed_at = str(payload.get("computed_at", "")).strip() or utc_now_iso()
    indicator_values = payload.get("indicator_values") if isinstance(payload.get("indicator_values"), dict) else {}
    return {
        "request_id": request_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "computed_at": computed_at,
        "source": str(payload.get("source", "indicator_ea")).strip() or "indicator_ea",
        "indicator_values": indicator_values,
        "raw": payload,
    }


def _build_indicator_request(
    symbol: str,
    timeframe: str,
    requested_indicators: list[str],
    lookback: int = 100,
    reason: str = "market_state_enrichment",
) -> dict[str, Any]:
    """Build indicator request payload."""
    return {
        "request_id": f"indreq_{uuid.uuid4().hex}",
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe).upper(),
        "requested_indicators": [item.strip() for item in requested_indicators if item.strip()],
        "lookback": int(lookback),
        "reason": reason,
        "requested_by_role": "system",
        "created_at": utc_now_iso(),
    }


class IndicatorBridge:
    def __init__(
        self,
        *,
        storage_root: Path,
        enabled: bool,
        common_files_root: str | None = None,
        stale_after_seconds: int = 180,
    ) -> None:
        self.storage_root = storage_root
        self.enabled = bool(enabled)
        self.common_root = resolve_common_files_root(common_files_root)
        self.responses_dir = self.common_root / "indicator_snapshots"
        self.requests_dir = self.common_root / "indicator_requests"
        self.stale_after_seconds = max(int(stale_after_seconds), 30)
        self.last_imported_at = ""
        self.last_snapshot_at = ""
        self.last_error = ""
        self.total_imported = 0
        self.total_requested = 0

        # Ensure directories exist
        if self.enabled:
            self.responses_dir.mkdir(parents=True, exist_ok=True)
            self.requests_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_status(self) -> str:
        if not self.enabled:
            return "inactive"
        if not self.last_snapshot_at:
            return "waiting_first_snapshot"
        computed_at = iso_to_datetime(self.last_snapshot_at)
        if computed_at is None:
            return "stale"
        if utc_now() - computed_at <= timedelta(seconds=self.stale_after_seconds):
            return "healthy"
        return "stale"

    def write_request(
        self,
        symbol: str,
        timeframe: str,
        requested_indicators: list[str],
        lookback: int = 100,
        reason: str = "market_state_enrichment",
    ) -> dict[str, Any] | None:
        """Write indicator request file for EA to process.
        
        Returns the request payload if successful, None if disabled.
        """
        if not self.enabled:
            return None
        
        request = _build_indicator_request(symbol, timeframe, requested_indicators, lookback, reason)
        
        # Write to Common Files directory (where EA reads from)
        request_path = self.requests_dir / f"{request['request_id']}.json"
        try:
            request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
            self.total_requested += 1
            return request
        except Exception as e:
            self.last_error = f"Failed to write request: {e}"
            return None

    def import_snapshots(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        imported: list[dict[str, Any]] = []
        if not self.responses_dir.exists():
            return imported
        for path in sorted(self.responses_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            snapshot = _normalize_snapshot(payload)
            if snapshot is None:
                continue
            imported.append(snapshot)
            self.total_imported += 1
            self.last_imported_at = utc_now_iso()
            self.last_snapshot_at = snapshot["computed_at"]
            try:
                path.unlink()
            except OSError:
                continue
        return imported

    def apply_to_market_state(
        self,
        market_state: MarketStateService,
        snapshots: list[dict[str, Any]],
        subscribed_symbols: set[str] | None = None,
        subscribed_timeframes: set[str] | None = None,
    ) -> int:
        applied = 0
        allowed_symbols = {symbol.upper() for symbol in (subscribed_symbols or set())}
        allowed_timeframes = {timeframe.upper() for timeframe in (subscribed_timeframes or set())}
        for snapshot in snapshots:
            symbol = str(snapshot.get("symbol", "")).upper()
            timeframe = str(snapshot.get("timeframe", "")).upper()
            if allowed_symbols and symbol not in allowed_symbols:
                continue
            if allowed_timeframes and timeframe not in allowed_timeframes:
                continue
            result = market_state.ingest_indicator_snapshot(snapshot)
            if result is not None:
                applied += 1
        return applied

    def poll(
        self,
        market_state: MarketStateService,
        subscribed_symbols: set[str] | None = None,
        subscribed_timeframes: set[str] | None = None,
        requested_indicators: list[str] | None = None,
    ) -> dict[str, Any]:
        """Poll for snapshots and create requests if needed.
        
        If no snapshot is available for a symbol/timeframe, creates a request file.
        """
        if requested_indicators is None:
            requested_indicators = ["ema_20", "ema_50", "rsi_14", "atr_14", "macd_main"]
        
        imported = self.import_snapshots()
        applied = (
            self.apply_to_market_state(
                market_state,
                imported,
                subscribed_symbols=subscribed_symbols,
                subscribed_timeframes=subscribed_timeframes,
            )
            if imported
            else 0
        )
        
        # Create requests for symbols/timeframes without recent snapshots
        allowed_symbols = {symbol.upper() for symbol in (subscribed_symbols or set())}
        allowed_timeframes = {timeframe.upper() for timeframe in (subscribed_timeframes or set())}
        
        requests_created = 0
        if allowed_symbols and allowed_timeframes:
            for symbol in allowed_symbols:
                for timeframe in allowed_timeframes:
                    key = MarketStateService.key(symbol, timeframe).value
                    state = market_state._states.get(key, {})
                    enrichment = state.get("indicator_enrichment", {})
                    
                    # Check if enrichment is stale or missing
                    computed_at = enrichment.get("computed_at") if isinstance(enrichment, dict) else None
                    if computed_at:
                        computed_dt = iso_to_datetime(str(computed_at))
                        if computed_dt and utc_now() - computed_dt <= timedelta(seconds=self.stale_after_seconds):
                            continue  # Still fresh
                    
                    # Create request
                    request = self.write_request(symbol, timeframe, requested_indicators)
                    if request:
                        requests_created += 1
        
        return {
            "enabled": self.enabled,
            "status": self._snapshot_status(),
            "responses_dir": str(self.responses_dir),
            "requests_dir": str(self.requests_dir),
            "last_imported_at": self.last_imported_at,
            "last_snapshot_at": self.last_snapshot_at,
            "last_error": self.last_error,
            "imported_in_cycle": len(imported),
            "applied_in_cycle": applied,
            "requests_created_in_cycle": requests_created,
            "total_imported": self.total_imported,
            "total_requested": self.total_requested,
            "updated_at": utc_now_iso(),
        }
