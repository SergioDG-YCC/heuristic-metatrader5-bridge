"""In-memory ring buffer for Fast Desk scan-cycle activity events.

Zero I/O, zero DB writes. Designed for high-frequency append (every scan cycle
per symbol) and low-frequency read (WebUI polling every 3-5 seconds).
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class FastScanEvent:
    timestamp: str
    symbol: str
    gate_reached: str
    gate_passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineStageResult:
    """Result of a single pipeline stage evaluation."""
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineTrace:
    """Full trace of one scan_and_execute cycle — all evaluated stages."""
    trace_id: str
    timestamp: str
    symbol: str
    stages: tuple[PipelineStageResult, ...]
    final_gate: str
    final_passed: bool


_MAX_PER_SYMBOL = 200
_MAX_GLOBAL = 500
_MAX_PIPELINE_TRACES = 300

_lock = threading.Lock()
_global_ring: deque[FastScanEvent] = deque(maxlen=_MAX_GLOBAL)
_symbol_rings: dict[str, deque[FastScanEvent]] = {}
_pipeline_ring: deque[PipelineTrace] = deque(maxlen=_MAX_PIPELINE_TRACES)
_pipeline_cursor: int = 0  # monotonic counter for incremental reads


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(symbol: str, gate: str, passed: bool, details: dict[str, Any] | None = None) -> None:
    """Append a scan-cycle event. Thread-safe, O(1)."""
    evt = FastScanEvent(
        timestamp=_utc_now_iso(),
        symbol=symbol.upper(),
        gate_reached=gate,
        gate_passed=passed,
        details=details or {},
    )
    with _lock:
        _global_ring.append(evt)
        ring = _symbol_rings.get(evt.symbol)
        if ring is None:
            ring = deque(maxlen=_MAX_PER_SYMBOL)
            _symbol_rings[evt.symbol] = ring
        ring.append(evt)


def recent(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent global events (newest first)."""
    with _lock:
        items = list(_global_ring)
    items.reverse()
    return [asdict(e) for e in items[:limit]]


def recent_for_symbol(symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent events for a specific symbol (newest first)."""
    with _lock:
        ring = _symbol_rings.get(symbol.upper())
        if ring is None:
            return []
        items = list(ring)
    items.reverse()
    return [asdict(e) for e in items[:limit]]


def per_symbol_summary() -> dict[str, dict[str, Any]]:
    """Return a summary dict keyed by symbol with last gate + block counts."""
    with _lock:
        symbols = list(_symbol_rings.keys())
        snapshots = {s: list(_symbol_rings[s]) for s in symbols}
    result: dict[str, dict[str, Any]] = {}
    for sym, events in snapshots.items():
        if not events:
            continue
        last = events[-1]
        blocked = sum(1 for e in events if not e.gate_passed)
        passed = sum(1 for e in events if e.gate_passed)
        gate_counts: dict[str, int] = {}
        for e in events:
            if not e.gate_passed:
                gate_counts[e.gate_reached] = gate_counts.get(e.gate_reached, 0) + 1
        result[sym] = {
            "last_gate": last.gate_reached,
            "last_passed": last.gate_passed,
            "last_timestamp": last.timestamp,
            "blocked_count": blocked,
            "passed_count": passed,
            "block_by_gate": gate_counts,
        }
    return result


# ---------------------------------------------------------------------------
# Pipeline Trace API — full scan-cycle traces for stage-by-stage visualisation
# ---------------------------------------------------------------------------

def emit_pipeline_trace(
    symbol: str,
    stages: list[PipelineStageResult],
    final_gate: str,
    final_passed: bool,
) -> None:
    """Append a full pipeline trace for one scan_and_execute cycle. Thread-safe."""
    global _pipeline_cursor
    trace = PipelineTrace(
        trace_id=uuid.uuid4().hex[:12],
        timestamp=_utc_now_iso(),
        symbol=symbol.upper(),
        stages=tuple(stages),
        final_gate=final_gate,
        final_passed=final_passed,
    )
    with _lock:
        _pipeline_ring.append(trace)
        _pipeline_cursor += 1


def pipeline_traces_since(cursor: int, limit: int = 100) -> tuple[list[dict[str, Any]], int]:
    """Return pipeline traces added after *cursor*, plus the new cursor.

    Used by the SSE endpoint for incremental streaming.
    Returns (traces_as_dicts, new_cursor).
    """
    with _lock:
        current_cursor = _pipeline_cursor
        total = len(_pipeline_ring)

    if cursor >= current_cursor:
        return [], current_cursor

    new_count = current_cursor - cursor
    with _lock:
        items = list(_pipeline_ring)

    # Only return the newest `new_count` items (they are at the tail)
    new_items = items[-min(new_count, total):]
    result = []
    for t in new_items[-limit:]:
        result.append({
            "trace_id": t.trace_id,
            "timestamp": t.timestamp,
            "symbol": t.symbol,
            "stages": [asdict(s) for s in t.stages],
            "final_gate": t.final_gate,
            "final_passed": t.final_passed,
        })
    return result, current_cursor


def pipeline_recent(limit: int = 60) -> list[dict[str, Any]]:
    """Return the most recent pipeline traces (newest first)."""
    with _lock:
        items = list(_pipeline_ring)
    items.reverse()
    result = []
    for t in items[:limit]:
        result.append({
            "trace_id": t.trace_id,
            "timestamp": t.timestamp,
            "symbol": t.symbol,
            "stages": [asdict(s) for s in t.stages],
            "final_gate": t.final_gate,
            "final_passed": t.final_passed,
        })
    return result


def pipeline_cursor() -> int:
    """Return the current pipeline cursor (monotonic counter)."""
    with _lock:
        return _pipeline_cursor
