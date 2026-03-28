"""
Elliott Wave counting — lightweight heuristic implementation.

Maps labeled swing sequence to 5-wave impulse or 3-wave ABC correction.
Confidence is scored based on how many rules are satisfied.
"""
from __future__ import annotations

from typing import Any


_WAVE_LABELS_UP = ["W0", "W1", "W2", "W3", "W4", "W5"]
_WAVE_LABELS_DOWN = ["W0", "W1", "W2", "W3", "W4", "W5"]


def _wave_length(a: float, b: float) -> float:
    return abs(b - a)


def _fibo_retrace_pct(start: float, end: float, retrace: float) -> float:
    """Return the Fibonacci retracement % from *end* back toward *start*.

    E.g. for an up-move (start < end), if retrace == start → 100 %,
    if retrace == end → 0 %.
    """
    span = abs(end - start)
    if span == 0:
        return 0.0
    return abs(end - retrace) / span


def _validate_wave_fibo(points: list[float], direction: str) -> list[str]:
    """Cross-validate impulse wave points against Fibonacci retracement rules.

    Returns a list of warnings (not hard violations) — the caller decides
    how to penalise the score.  The tolerances are generous per user
    requirement ("brindar espacio de riesgo").

    Expected direction: "up" or "down".
    """
    if len(points) < 6:
        return []
    w0, w1, w2, w3, w4, w5 = points[:6]
    warnings: list[str] = []

    # Wave 2 retracement of Wave 1 — ideal 38.2-78.6%, acceptable up to 99%
    w2_retrace = _fibo_retrace_pct(w0, w1, w2)
    if w2_retrace > 0.99:
        warnings.append("w2_retrace_exceeds_100pct")
    elif w2_retrace > 0.786:
        warnings.append("w2_retrace_deep_but_valid")

    # Wave 4 retracement of Wave 3 — ideal 23.6-50%, acceptable up to 78.6%
    w4_retrace = _fibo_retrace_pct(w2, w3, w4)
    if w4_retrace > 0.786:
        warnings.append("w4_retrace_exceeds_786")
    elif w4_retrace > 0.618:
        warnings.append("w4_retrace_deep_but_valid")

    # Wave 3 extension — typically ≥ 1.0 × Wave 1, ideally 1.618
    len_w1 = _wave_length(w0, w1)
    len_w3 = _wave_length(w2, w3)
    if len_w1 > 0:
        w3_ext = len_w3 / len_w1
        if w3_ext < 0.9:
            warnings.append("w3_extension_below_1x")
        elif w3_ext >= 1.618:
            pass  # ideal
        elif w3_ext >= 1.0:
            pass  # acceptable

    return warnings


def _score_impulse_up(points: list[float]) -> tuple[float, list[str]]:
    if len(points) < 6:
        return 0.0, ["insufficient_points"]

    w0, w1, w2, w3, w4, w5 = points[:6]
    violations: list[str] = []
    checks = 0

    if not (w1 > w0): violations.append("w1_not_up")
    if not (w2 < w1): violations.append("w2_not_down")
    if not (w3 > w1): violations.append("w3_not_above_w1")
    if not (w4 < w3): violations.append("w4_not_down")
    if not (w5 > w4): violations.append("w5_not_up")
    checks += 5

    if w2 < w0:
        violations.append("w2_below_w0")
    checks += 1

    if w4 < w1:
        violations.append("w4_overlaps_w1")
    checks += 1

    len_w1 = _wave_length(w0, w1)
    len_w3 = _wave_length(w2, w3)
    len_w5 = _wave_length(w4, w5)
    if len_w3 < len_w1 and len_w3 < len_w5:
        violations.append("w3_is_shortest")
    checks += 1

    score = max(0.0, (checks - len(violations)) / checks)

    # Fibonacci cross-validation (penalise softly — warnings, not hard fails)
    fibo_warnings = _validate_wave_fibo(points, "up")
    hard_fibo = [w for w in fibo_warnings if "exceeds" in w]
    score -= len(hard_fibo) * 0.05     # small penalty per hard fibo issue
    score = max(0.0, score)
    violations.extend(fibo_warnings)

    return round(score, 3), violations


def _score_impulse_down(points: list[float]) -> tuple[float, list[str]]:
    if len(points) < 6:
        return 0.0, ["insufficient_points"]

    w0, w1, w2, w3, w4, w5 = points[:6]
    violations: list[str] = []
    checks = 0

    if not (w1 < w0): violations.append("w1_not_down")
    if not (w2 > w1): violations.append("w2_not_up")
    if not (w3 < w1): violations.append("w3_not_below_w1")
    if not (w4 > w3): violations.append("w4_not_up")
    if not (w5 < w4): violations.append("w5_not_down")
    checks += 5

    if w2 > w0:
        violations.append("w2_above_w0")
    checks += 1

    if w4 > w1:
        violations.append("w4_overlaps_w1")
    checks += 1

    len_w1 = _wave_length(w0, w1)
    len_w3 = _wave_length(w2, w3)
    len_w5 = _wave_length(w4, w5)
    if len_w3 < len_w1 and len_w3 < len_w5:
        violations.append("w3_is_shortest")
    checks += 1

    score = max(0.0, (checks - len(violations)) / checks)

    # Fibonacci cross-validation for down impulse
    fibo_warnings = _validate_wave_fibo(points, "down")
    hard_fibo = [w for w in fibo_warnings if "exceeds" in w]
    score -= len(hard_fibo) * 0.05
    score = max(0.0, score)
    violations.extend(fibo_warnings)

    return round(score, 3), violations


def _score_abc_up(points: list[float]) -> tuple[float, list[str]]:
    if len(points) < 4:
        return 0.0, ["insufficient_points"]
    w0, wa, wb, wc = points[:4]
    violations: list[str] = []
    checks = 3

    if not (wa > w0): violations.append("a_not_up")
    if not (wb < wa): violations.append("b_not_down")
    if not (wb > w0): violations.append("b_below_start")
    if not (wc > wa): violations.append("c_not_above_a")
    checks += 1

    score = max(0.0, (checks - len(violations)) / checks)
    return round(score, 3), violations


def count_waves(
    structure: dict[str, Any],
) -> dict[str, Any]:
    """Attempt to count Elliott Waves from the swing sequence in structure."""
    labeled = structure.get("swing_labels", [])
    empty = {
        "pattern_type": "unclear",
        "current_wave": None,
        "wave_points": [],
        "confidence": 0.0,
        "completed": False,
        "violations": ["insufficient_swings"],
    }

    if len(labeled) < 4:
        return empty

    prices: list[float] = [float(s.get("price", 0.0) or 0.0) for s in labeled]
    timestamps: list[str] = [str(s.get("timestamp", "")) for s in labeled]

    best_result = empty.copy()
    best_score = 0.0

    # Try 5-wave impulse up
    for start in range(len(prices) - 5):
        chunk = prices[start: start + 6]
        score, violations = _score_impulse_up(chunk)
        if score > best_score:
            best_score = score
            current_wave = 5 if score > 0.7 else (4 if chunk[3] > chunk[1] else 3)
            best_result = {
                "pattern_type": "impulse_up",
                "current_wave": current_wave,
                "wave_points": [
                    {"wave": _WAVE_LABELS_UP[k], "price": chunk[k],
                     "timestamp": timestamps[start + k]}
                    for k in range(len(chunk))
                ],
                "confidence": score,
                "completed": score > 0.7,
                "violations": violations,
            }

    # Try 5-wave impulse down
    for start in range(len(prices) - 5):
        chunk = prices[start: start + 6]
        score, violations = _score_impulse_down(chunk)
        if score > best_score:
            best_score = score
            best_result = {
                "pattern_type": "impulse_down",
                "current_wave": 5 if score > 0.7 else 3,
                "wave_points": [
                    {"wave": _WAVE_LABELS_DOWN[k], "price": chunk[k],
                     "timestamp": timestamps[start + k]}
                    for k in range(len(chunk))
                ],
                "confidence": score,
                "completed": score > 0.7,
                "violations": violations,
            }

    # Try ABC correction up
    for start in range(len(prices) - 3):
        chunk = prices[start: start + 4]
        score, violations = _score_abc_up(chunk)
        if score > best_score:
            best_score = score
            best_result = {
                "pattern_type": "correction_abc_up",
                "current_wave": 3 if score > 0.7 else 2,
                "wave_points": [
                    {"wave": label, "price": chunk[k],
                     "timestamp": timestamps[start + k]}
                    for k, label in enumerate(["W0", "A", "B", "C"])
                    if k < len(chunk)
                ],
                "confidence": score,
                "completed": score > 0.7,
                "violations": violations,
            }

    # ABC correction down
    for start in range(len(prices) - 3):
        chunk = prices[start: start + 4]
        down_chunk = [-p for p in chunk]
        score, violations = _score_abc_up(down_chunk)
        if score > best_score:
            best_score = score
            best_result = {
                "pattern_type": "correction_abc_down",
                "current_wave": 3 if score > 0.7 else 2,
                "wave_points": [
                    {"wave": label, "price": chunk[k],
                     "timestamp": timestamps[start + k]}
                    for k, label in enumerate(["W0", "A", "B", "C"])
                    if k < len(chunk)
                ],
                "confidence": score,
                "completed": score > 0.7,
                "violations": violations,
            }

    return best_result
