"""
SMC LLM Validator — exactly one HTTP call per analyst run.

Sends a JSON payload to LocalAI (Gemma 3 12B) with:
  - system.md  → role + output contract
  - user.md    → case data (compact JSON)

Returns a normalized validator_result dict:
  {
    "used_llm": bool,
    "validator_result": {"decision", "confidence", "issues", "adjustments", "summary"},
    "validated_thesis": dict,
  }

No disk writes. No module-level config. All params explicit.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_ALLOWED_DECISIONS = frozenset({"accept", "reject", "adjust"})
_ALLOWED_CONFIDENCE = frozenset({"high", "medium", "low"})


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def _load_prompt(name: str, *, compact_json: str = "") -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    if compact_json:
        text = text.replace("{{compact_json}}", compact_json)
    return text


# ---------------------------------------------------------------------------
# JSON extraction + normalisation
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty validator response")
    # Fast path — well-formed JSON
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    # Try to find the first JSON object via brace scanning
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            payload = json.loads(text[start : end + 1])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    raise ValueError(f"validator response is not a valid JSON object: {text[:200]!r}")


def _normalize_validator_output(payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision", "accept")).strip().lower()
    if decision not in _ALLOWED_DECISIONS:
        decision = "accept"

    confidence = str(payload.get("confidence", "low")).strip().lower()
    if confidence not in _ALLOWED_CONFIDENCE:
        confidence = "low"

    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    issues = [str(item).strip()[:220] for item in issues if str(item).strip()][:12]

    adjustments = payload.get("adjustments")
    if not isinstance(adjustments, list):
        adjustments = []
    # Semantic-only adjustments; prices/levels are ignored downstream.
    adjustments = [str(item).strip()[:220] for item in adjustments if str(item).strip()][:12]

    summary = str(payload.get("summary", "")).strip()[:400]

    return {
        "decision": decision,
        "confidence": confidence,
        "issues": issues,
        "adjustments": adjustments,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Thesis application
# ---------------------------------------------------------------------------

def _apply_validator_result(heuristic_thesis: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    out = dict(heuristic_thesis)
    decision = str(normalized.get("decision", "accept")).lower()

    notes = str(out.get("analyst_notes", "") or "").strip()
    summary = str(normalized.get("summary", "")).strip()
    if summary:
        notes = (notes + " | " if notes else "") + f"LLM validator: {summary}"
    out["analyst_notes"] = notes[:1000] if notes else None

    if decision == "reject":
        out["operation_candidates"] = []
        out["status"] = "watching"
        reject_note = "Validator decision=reject. Candidates cleared."
        if isinstance(out.get("watch_conditions"), list):
            out["watch_conditions"] = out["watch_conditions"][:14] + [reject_note]
        else:
            out["watch_conditions"] = [reject_note]
    elif decision == "adjust":
        semantic = [
            str(item).strip()
            for item in normalized.get("adjustments", [])
            if str(item).strip()
        ]
        if semantic:
            if isinstance(out.get("watch_conditions"), list):
                out["watch_conditions"] = out["watch_conditions"][:12] + semantic[:3]
            else:
                out["watch_conditions"] = semantic[:3]

    out["validator_decision"] = decision
    out["validator_result"] = normalized
    return out


# ---------------------------------------------------------------------------
# HTTP call
# ---------------------------------------------------------------------------

def _call_localai_sync(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    localai_base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{localai_base_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LocalAI HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LocalAI connection failed: {exc.reason}") from exc

    result = json.loads(body)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices missing in LocalAI response")

    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty validator content from LocalAI")

    return _extract_json(content)


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------


async def call_smc_validator(
    *,
    symbol: str,
    current_price: float,
    trigger_reason: str,
    heuristic_thesis: dict[str, Any],
    validation_summary: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Make exactly one LLM call to validate a heuristic thesis.

    Parameters
    ----------
    symbol           : broker symbol
    current_price    : float — last known close
    trigger_reason   : why the analyst was triggered
    heuristic_thesis : output of build_heuristic_output (after hard validation)
    validation_summary: output of validate_heuristic_thesis
    config           : {
        "llm_model": str,
        "llm_timeout_seconds": int,
        "localai_base_url": str (optional),
        "max_tokens": int (optional),
    }

    Returns
    -------
    {
        "used_llm": bool,
        "validator_result": dict,
        "validated_thesis": dict,
    }
    """
    import asyncio

    model = str(config.get("llm_model", "gemma-3-4b-it-qat"))
    timeout = float(config.get("llm_timeout_seconds", 60))
    max_tokens = int(config.get("max_tokens", 500))
    localai_base_url = str(
        config.get("localai_base_url", os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080"))
    ).rstrip("/")

    validator_input = {
        "symbol": str(symbol).upper(),
        "current_price": float(current_price),
        "trigger_reason": str(trigger_reason),
        "heuristic_thesis": heuristic_thesis,
        "validation_summary": validation_summary,
    }
    compact_json = json.dumps(validator_input, ensure_ascii=True, separators=(",", ":"))

    messages = [
        {"role": "system", "content": _load_prompt("system")},
        {"role": "user", "content": _load_prompt("user", compact_json=compact_json)},
    ]

    fallback = {
        "decision": "accept",
        "confidence": "low",
        "issues": [],
        "adjustments": [],
        "summary": "Validator unavailable; heuristic thesis preserved.",
    }

    try:
        raw = await asyncio.to_thread(
            _call_localai_sync,
            messages,
            model=model,
            max_tokens=max_tokens,
            localai_base_url=localai_base_url,
            timeout_seconds=timeout,
        )
        normalized = _normalize_validator_output(raw)
        validated = _apply_validator_result(dict(heuristic_thesis), normalized)
        return {
            "used_llm": True,
            "validator_result": normalized,
            "validated_thesis": validated,
        }
    except Exception as exc:
        print(f"[smc-validator] LLM call failed ({type(exc).__name__}: {exc}); falling back to accept")
        fallback["issues"] = [f"validator_fallback:{type(exc).__name__}"]
        validated = _apply_validator_result(dict(heuristic_thesis), fallback)
        return {
            "used_llm": False,
            "validator_result": fallback,
            "validated_thesis": validated,
        }
