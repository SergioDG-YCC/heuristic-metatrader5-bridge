"""Quick diagnostic: test LocalAI from Python with different payload sizes."""
import json
import time
import urllib.request

BASE_URL = "http://127.0.0.1:8080"
MODEL = "gemma-3-12b-it-qat"

def call(label: str, messages: list, max_tokens: int = 50, use_json_format: bool = False):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if use_json_format:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url=f"{BASE_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"\n[{label}] payload_bytes={len(data)} max_tokens={max_tokens} json_format={use_json_format}")
    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
        elapsed = time.monotonic() - t0
        result = json.loads(body)
        usage = result.get("usage", {})
        content = result["choices"][0]["message"]["content"][:300]
        print(f"  OK elapsed={elapsed:.1f}s prompt_tok={usage.get('prompt_tokens')} compl_tok={usage.get('completion_tokens')}")
        print(f"  content: {content}")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"  FAILED after {elapsed:.1f}s: {type(exc).__name__}: {exc}")


# Test 1: tiny payload, no json_format
call("tiny-free", [{"role": "user", "content": "Say hello"}], max_tokens=20)

# Test 2: tiny payload, WITH json_format
call("tiny-json", [{"role": "user", "content": 'Reply with {"ok":true}'}], max_tokens=50, use_json_format=True)

# Test 3: medium payload (~2KB) simulating validator, WITH json_format
fake_thesis = json.dumps({
    "symbol": "EURUSD", "bias": "bullish", "status": "active",
    "operation_candidates": [{"side": "buy", "rr_ratio": 3.5, "entry_model": "ob_retest", "confluences": ["bos", "fvg"]}],
    "multi_timeframe_alignment": {"d1_structure": "bullish", "h4_structure": "bullish", "aligned": True},
    "prepared_zones": ["ob_1.0800_1.0820"],
}, ensure_ascii=True, separators=(",", ":"))

system_msg = "You are the SMC thesis validator. Reply ONLY with JSON: {decision, confidence, issues, adjustments, summary}."
user_msg = f"Validate this thesis:\n{fake_thesis}"

call("medium-json", [
    {"role": "system", "content": system_msg},
    {"role": "user", "content": user_msg},
], max_tokens=500, use_json_format=True)

print("\nDone.")
