from __future__ import annotations

from typing import Iterable


_RAW_CONTEXT_SYMBOLS: dict[str, str] = {
    "VIX": "VIX",
    "UsDollar": "UsDollar",
}
CONTEXT_SYMBOLS: dict[str, str] = {key.upper(): value for key, value in _RAW_CONTEXT_SYMBOLS.items()}


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def is_context_symbol(symbol: str) -> bool:
    return normalize_symbol(symbol) in CONTEXT_SYMBOLS


def is_operable_symbol(symbol: str) -> bool:
    normalized = normalize_symbol(symbol)
    return bool(normalized) and normalized not in CONTEXT_SYMBOLS


def split_symbols(symbols: Iterable[str]) -> tuple[list[str], list[str]]:
    operable: list[str] = []
    context_only: list[str] = []
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        if not normalized:
            continue
        if is_context_symbol(normalized):
            context_only.append(normalized)
        else:
            operable.append(normalized)
    return operable, context_only

