from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Iterable

from heuristic_mt5_bridge.shared.symbols.universe import is_operable_symbol, normalize_symbol


def _normalize_unique_symbols(symbols: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = normalize_symbol(raw)
        if not symbol or symbol in seen or not is_operable_symbol(symbol):
            continue
        ordered.append(symbol)
        seen.add(symbol)
    return ordered


@dataclass(frozen=True)
class UniverseBootstrapResult:
    bootstrap_universe: list[str]
    subscribed_universe: list[str]
    rejected_symbols: list[str]


class SubscriptionManager:
    """Owns catalog, bootstrap, and subscribed universes."""

    def __init__(self, *, bootstrap_symbols: Iterable[str] | None = None) -> None:
        bootstrap_universe = _normalize_unique_symbols(bootstrap_symbols or [])
        self._lock = Lock()
        self._catalog_universe: list[str] = []
        self._catalog_lookup: set[str] = set()
        self._bootstrap_universe: list[str] = list(bootstrap_universe)
        self._subscribed_universe: list[str] = list(bootstrap_universe)

    def set_catalog_universe(self, symbols: Iterable[str]) -> list[str]:
        catalog_universe = _normalize_unique_symbols(symbols)
        with self._lock:
            self._catalog_universe = list(catalog_universe)
            self._catalog_lookup = set(catalog_universe)
        return catalog_universe

    def bootstrap_from_env(self, symbols: Iterable[str]) -> UniverseBootstrapResult:
        requested = _normalize_unique_symbols(symbols)
        with self._lock:
            if self._catalog_lookup:
                accepted = [symbol for symbol in requested if symbol in self._catalog_lookup]
                rejected = [symbol for symbol in requested if symbol not in self._catalog_lookup]
            else:
                accepted = list(requested)
                rejected = []
            self._bootstrap_universe = list(accepted)
            self._subscribed_universe = list(accepted)
            return UniverseBootstrapResult(
                bootstrap_universe=list(self._bootstrap_universe),
                subscribed_universe=list(self._subscribed_universe),
                rejected_symbols=rejected,
            )

    def reconcile_subscriptions_with_catalog(self) -> list[str]:
        with self._lock:
            if not self._catalog_lookup:
                return []
            kept_subscribed = [symbol for symbol in self._subscribed_universe if symbol in self._catalog_lookup]
            removed = [symbol for symbol in self._subscribed_universe if symbol not in self._catalog_lookup]
            self._subscribed_universe = kept_subscribed
            self._bootstrap_universe = [
                symbol for symbol in self._bootstrap_universe if symbol in self._catalog_lookup
            ]
            return removed

    def subscribe(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        if not normalized or not is_operable_symbol(normalized):
            return False
        with self._lock:
            if self._catalog_lookup and normalized not in self._catalog_lookup:
                return False
            if normalized in self._subscribed_universe:
                return False
            self._subscribed_universe.append(normalized)
            return True

    def force_subscribe(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        if not normalized or not is_operable_symbol(normalized):
            return False
        with self._lock:
            if normalized in self._subscribed_universe:
                return False
            self._subscribed_universe.append(normalized)
            return True

    def unsubscribe(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        if not normalized:
            return False
        with self._lock:
            if normalized not in self._subscribed_universe:
                return False
            self._subscribed_universe = [item for item in self._subscribed_universe if item != normalized]
            return True

    def replace_subscribed_universe(self, symbols: Iterable[str]) -> list[str]:
        requested = _normalize_unique_symbols(symbols)
        with self._lock:
            if self._catalog_lookup:
                requested = [symbol for symbol in requested if symbol in self._catalog_lookup]
            self._subscribed_universe = list(requested)
            return list(self._subscribed_universe)

    def catalog_universe(self) -> list[str]:
        with self._lock:
            return list(self._catalog_universe)

    def bootstrap_universe(self) -> list[str]:
        with self._lock:
            return list(self._bootstrap_universe)

    def subscribed_universe(self) -> list[str]:
        with self._lock:
            return list(self._subscribed_universe)

    def snapshot(self) -> dict[str, list[str]]:
        with self._lock:
            return {
                "catalog_universe": list(self._catalog_universe),
                "bootstrap_universe": list(self._bootstrap_universe),
                "subscribed_universe": list(self._subscribed_universe),
            }
