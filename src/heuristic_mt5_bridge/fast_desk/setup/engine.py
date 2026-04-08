from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from heuristic_mt5_bridge.smc_desk.detection.fair_value_gaps import detect_fair_value_gaps
from heuristic_mt5_bridge.smc_desk.detection.liquidity import detect_liquidity_pools, detect_sweeps
from heuristic_mt5_bridge.smc_desk.detection.order_blocks import detect_order_blocks
from heuristic_mt5_bridge.smc_desk.detection.structure import detect_market_structure


logger = logging.getLogger("fast_desk.setup")

DEFAULT_EFFECTIVE_MIN_RR = 3.0


@dataclass
class FastSetupConfig:
    rr_ratio: float = 3.0
    min_confidence: float = 0.55
    min_rr: float | None = None  # internal tolerance, not operator-facing

    def __post_init__(self) -> None:
        rr = float(self.rr_ratio or 0.0)
        if rr <= 0:
            rr = 3.0
        self.rr_ratio = rr
        raw_min_rr = float(self.min_rr or 0.0)
        if raw_min_rr <= 0:
            raw_min_rr = min(rr, DEFAULT_EFFECTIVE_MIN_RR)
        # Keep a single user-facing RR while preserving a permissive internal
        # acceptance floor so spread adjustment does not silently zero the desk.
        self.min_rr = max(0.0, min(rr, raw_min_rr))


@dataclass
class FastSetup:
    setup_id: str
    setup_type: str
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pips: float
    confidence: float
    requires_pending: bool
    pending_entry_type: str
    retest_level: float | None
    metadata: dict[str, Any] = field(default_factory=dict)


class FastSetupEngine:
    """Detect deterministic M5 setups contextualized by H1."""

    def __init__(self, config: FastSetupConfig | None = None) -> None:
        self.config = config or FastSetupConfig()

    def detect_setups(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]] | None = None,
        pip_size: float,
        m30_bias: str,
        spread_pips: float = 0.0,
        htf_zones: list[dict[str, Any]] | None = None,
        # Backward compat alias
        candles_h1: list[dict[str, Any]] | None = None,
    ) -> list[FastSetup]:
        htf = candles_htf if candles_htf is not None else (candles_h1 or [])
        if len(candles_m5) < 40 or len(htf) < 40 or pip_size <= 0:
            logger.debug(
                "detect_setups early exit: m5=%d htf=%d pip_size=%s",
                len(candles_m5), len(htf), pip_size,
            )
            return []

        cfg = self.config
        atr = self._atr(candles_m5, 14)
        if atr <= 0:
            logger.debug("detect_setups: ATR <= 0 for %s, skipping", symbol)
            return []
        latest_close = float(candles_m5[-1].get("close", 0.0) or 0.0)
        if latest_close <= 0:
            return []

        structure_m5 = detect_market_structure(candles_m5[-180:], window=3)
        structure_htf = detect_market_structure(htf[-200:], window=3)

        # Premium/Discount zone boundary from HTF impulse
        impulse_high = float(structure_htf.get("last_impulse_high") or 0.0)
        impulse_low = float(structure_htf.get("last_impulse_low") or 0.0)
        pd_mid = float(structure_htf.get("premium_discount_level") or 0.0)
        if pd_mid <= 0 and impulse_high > 0 and impulse_low > 0:
            pd_mid = (impulse_high + impulse_low) / 2.0

        setups: list[FastSetup] = []
        setups.extend(
            self._order_block_retest(
                symbol=symbol,
                candles_m5=candles_m5,
                candles_htf=htf,
                structure_m5=structure_m5,
                structure_htf=structure_htf,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=cfg.rr_ratio,
            )
        )
        setups.extend(
            self._fvg_reaction(
                symbol=symbol,
                candles_m5=candles_m5,
                candles_htf=htf,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=cfg.rr_ratio,
            )
        )
        setups.extend(
            self._liquidity_sweep_reclaim(
                symbol=symbol,
                candles_m5=candles_m5,
                candles_htf=htf,
                structure_htf=structure_htf,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=cfg.rr_ratio,
            )
        )
        setups.extend(
            self._breakout_retest(
                symbol=symbol,
                candles_m5=candles_m5,
                structure_m5=structure_m5,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=cfg.rr_ratio,
            )
        )
        setups.extend(
            self._pattern_setups(
                symbol=symbol,
                candles_m5=candles_m5,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=cfg.rr_ratio,
                m30_bias=m30_bias,
            )
        )

        filtered = [setup for setup in setups if setup.confidence >= cfg.min_confidence and setup.risk_pips > 0]

        logger.debug(
            "detect_setups %s: raw=%d after_conf_filter=%d pd_mid=%.5f",
            symbol, len(setups), len(filtered), pd_mid,
        )

        # Phase 4: Premium/Discount zone filter is SOFT — penalize confidence instead of discarding
        if pd_mid > 0:
            for s in filtered:
                if s.side == "buy" and s.entry_price > pd_mid:
                    s.confidence = round(s.confidence * 0.7, 4)
                if s.side == "sell" and s.entry_price < pd_mid:
                    s.confidence = round(s.confidence * 0.7, 4)

        # Phase 4: Bias alignment penalty (soft, not blocking)
        for s in filtered:
            if m30_bias in {"buy", "sell"} and s.side != m30_bias:
                penalty = 0.88 if bool(s.metadata.get("zone_reaction")) else 0.75
                s.confidence = round(s.confidence * penalty, 4)

        for s in filtered:
            self._apply_htf_zone_context(s, htf_zones or [], latest_close)

        # Re-apply min_confidence after all penalties
        filtered = [s for s in filtered if s.confidence >= cfg.min_confidence]

        # Apply spread buffer to SL and recalculate effective RR
        if spread_pips > 0 and pip_size > 0:
            spread_dist = spread_pips * pip_size
            adjusted: list[FastSetup] = []
            for s in filtered:
                if s.side == "buy":
                    adj_sl = s.stop_loss - spread_dist
                else:
                    adj_sl = s.stop_loss + spread_dist
                adj_risk = abs(s.entry_price - adj_sl)
                adj_risk_pips = adj_risk / pip_size if pip_size > 0 else 0.0
                reward = abs(s.take_profit - s.entry_price)
                eff_rr = reward / adj_risk if adj_risk > 0 else 0.0
                if eff_rr < cfg.min_rr:
                    continue
                adjusted.append(FastSetup(
                    setup_id=s.setup_id,
                    setup_type=s.setup_type,
                    symbol=s.symbol,
                    side=s.side,
                    entry_price=s.entry_price,
                    stop_loss=round(adj_sl, 10),
                    take_profit=s.take_profit,
                    risk_pips=round(adj_risk_pips, 4),
                    confidence=s.confidence,
                    requires_pending=s.requires_pending,
                    pending_entry_type=s.pending_entry_type,
                    retest_level=s.retest_level,
                    metadata=s.metadata,
                ))
            filtered = adjusted
        else:
            # No live spread — still enforce min_rr from raw values
            filtered = [
                s for s in filtered
                if (abs(s.take_profit - s.entry_price) / abs(s.entry_price - s.stop_loss) if abs(s.entry_price - s.stop_loss) > 0 else 0.0) >= cfg.min_rr
            ]
        filtered.sort(key=lambda item: item.confidence, reverse=True)
        logger.debug(
            "detect_setups %s: final_count=%d types=%s",
            symbol, len(filtered), [s.setup_type for s in filtered],
        )
        return filtered

    def enumerate_zones(
        self,
        *,
        symbol: str,
        candles_m1: list[dict[str, Any]],
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        zones: list[dict[str, Any]] = []

        series_m1 = candles_m1[-220:]
        series_m5 = candles_m5[-220:]
        series_m30 = candles_htf[-220:]
        if len(series_m1) < 30 or len(series_m5) < 40 or len(series_m30) < 40:
            return []

        structure_m1 = detect_market_structure(series_m1[-180:], window=3)
        structure_m5 = detect_market_structure(series_m5[-180:], window=3)
        structure_m30 = detect_market_structure(series_m30[-180:], window=3)

        zones.extend(self._enumerate_zones_for_series(
            symbol=symbol,
            timeframe_origin="M1",
            candles=series_m1,
            structure=structure_m1,
            liquidity_higher=series_m5,
            liquidity_structure=structure_m5,
        ))
        zones.extend(self._enumerate_zones_for_series(
            symbol=symbol,
            timeframe_origin="M5",
            candles=series_m5,
            structure=structure_m5,
            liquidity_higher=series_m30,
            liquidity_structure=structure_m30,
        ))
        zones.extend(self._enumerate_zones_for_series(
            symbol=symbol,
            timeframe_origin="M30",
            candles=series_m30,
            structure=structure_m30,
            liquidity_higher=series_m30,
            liquidity_structure=structure_m30,
        ))

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, float, float]] = set()
        for zone in zones:
            key = (
                str(zone.get("timeframe_origin", "")),
                str(zone.get("zone_type", "")),
                round(float(zone.get("price_low", 0.0) or 0.0), 6),
                round(float(zone.get("price_high", 0.0) or 0.0), 6),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(zone)

        return deduped

    @staticmethod
    def _display_timeframes_for_origin(timeframe_origin: str) -> list[str]:
        tf = str(timeframe_origin or "").upper()
        if tf == "M1":
            return ["M1"]
        if tf == "M5":
            return ["M1", "M5"]
        return ["M1", "M5", "M30"]

    def _enumerate_zones_for_series(
        self,
        *,
        symbol: str,
        timeframe_origin: str,
        candles: list[dict[str, Any]],
        structure: dict[str, Any],
        liquidity_higher: list[dict[str, Any]],
        liquidity_structure: dict[str, Any],
    ) -> list[dict[str, Any]]:
        zones: list[dict[str, Any]] = []

        for zone in detect_order_blocks(candles, structure, min_impulse_candles=3, max_zones=8):
            if bool(zone.get("mitigated", False)):
                continue
            item = self._zone_snapshot_from_detection(
                symbol=symbol,
                timeframe_origin=timeframe_origin,
                zone=zone,
                status="active",
            )
            if item is not None:
                zones.append(item)

        for zone in detect_fair_value_gaps(candles, max_zones=10):
            if bool(zone.get("mitigated", False)):
                continue
            item = self._zone_snapshot_from_detection(
                symbol=symbol,
                timeframe_origin=timeframe_origin,
                zone=zone,
                status="active",
            )
            if item is not None:
                zones.append(item)

        liquidity = detect_liquidity_pools(
            liquidity_higher[-180:],
            candles[-200:],
            structure=liquidity_structure,
            max_zones=10,
        )
        sweeps = detect_sweeps(candles[-200:], liquidity, lookback=80)

        for zone in liquidity:
            if bool(zone.get("taken", False)):
                continue
            item = self._zone_snapshot_from_detection(
                symbol=symbol,
                timeframe_origin=timeframe_origin,
                zone=zone,
                status="active",
            )
            if item is not None:
                zones.append(item)

        for zone in sweeps[:6]:
            item = self._zone_snapshot_from_detection(
                symbol=symbol,
                timeframe_origin=timeframe_origin,
                zone=zone,
                status="swept",
            )
            if item is not None:
                zones.append(item)

        return zones

    def _zone_snapshot_from_detection(
        self,
        *,
        symbol: str,
        timeframe_origin: str,
        zone: dict[str, Any],
        status: str,
    ) -> dict[str, Any] | None:
        top = float(zone.get("price_high", 0.0) or 0.0)
        bottom = float(zone.get("price_low", 0.0) or 0.0)
        if top <= 0 or bottom <= 0:
            return None
        zone_type = str(zone.get("zone_type", "") or "zone")
        return {
            "symbol": symbol.upper(),
            "source": "fast",
            "zone_type": zone_type,
            "side": self._zone_side(zone_type),
            "timeframe_origin": str(timeframe_origin).upper(),
            "display_timeframes": self._display_timeframes_for_origin(timeframe_origin),
            "price_low": round(min(bottom, top), 10),
            "price_high": round(max(bottom, top), 10),
            "status": status,
            "origin_time": str(zone.get("origin_candle_time") or zone.get("sweep_candle_time") or ""),
            "origin_index": int(zone.get("origin_index", zone.get("sweep_index", 0)) or 0),
            "kind": "zone",
        }

    @staticmethod
    def _zone_side(zone_type: str) -> str:
        z = str(zone_type or "").lower()
        if any(token in z for token in ("bull", "ssl", "equal_lows")):
            return "buy"
        if any(token in z for token in ("bear", "bsl", "equal_highs")):
            return "sell"
        return "neutral"

    def _apply_htf_zone_context(
        self,
        setup: FastSetup,
        htf_zones: list[dict[str, Any]],
        current_price: float,
    ) -> None:
        if not htf_zones:
            setup.metadata["htf_zone_state"] = "neutral"
            return
        nearest: tuple[float, dict[str, Any]] | None = None
        for zone in htf_zones:
            if not isinstance(zone, dict):
                continue
            top = float(zone.get("price_high", 0.0) or zone.get("high", 0.0) or 0.0)
            bottom = float(zone.get("price_low", 0.0) or zone.get("low", 0.0) or 0.0)
            if top <= 0 or bottom <= 0:
                continue
            mid = (top + bottom) / 2.0
            dist = abs(mid - current_price)
            if nearest is None or dist < nearest[0]:
                nearest = (dist, zone)
        if nearest is None:
            setup.metadata["htf_zone_state"] = "neutral"
            return
        zone = nearest[1]
        zone_side = str(zone.get("side") or self._zone_side(str(zone.get("zone_type", ""))))
        state = "neutral"
        if zone_side in {"buy", "sell"}:
            state = "confluence" if zone_side == setup.side else "conflict"
        setup.metadata["htf_zone_state"] = state
        setup.metadata["htf_zone_side"] = zone_side
        setup.metadata["htf_zone_type"] = str(zone.get("zone_type", ""))
        if state == "confluence":
            setup.confidence = round(min(0.99, setup.confidence * 1.08), 4)
        elif state == "conflict":
            setup.confidence = round(setup.confidence * 0.90, 4)

    def _order_block_retest(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]],
        structure_m5: dict[str, Any],
        structure_htf: dict[str, Any],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> list[FastSetup]:
        setups: list[FastSetup] = []
        setups.extend(
            self._order_block_retest_for_series(
                symbol=symbol,
                candles=candles_m5[-180:],
                structure=structure_m5,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=rr,
                timeframe_origin="M5",
                confidence=0.82,
            )
        )
        setups.extend(
            self._order_block_retest_for_series(
                symbol=symbol,
                candles=candles_htf[-180:],
                structure=structure_htf,
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=rr,
                timeframe_origin="M30",
                confidence=0.85,
            )
        )
        return setups

    def _order_block_retest_for_series(
        self,
        *,
        symbol: str,
        candles: list[dict[str, Any]],
        structure: dict[str, Any],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
        timeframe_origin: str,
        confidence: float,
    ) -> list[FastSetup]:
        zones = detect_order_blocks(candles, structure, min_impulse_candles=3, max_zones=6)
        setups: list[FastSetup] = []
        tolerance = atr * 0.35
        for zone in zones:
            top = float(zone.get("price_high", 0.0) or 0.0)
            bottom = float(zone.get("price_low", 0.0) or 0.0)
            if top <= 0 or bottom <= 0:
                continue
            mid = (top + bottom) / 2.0
            in_zone = (latest_close >= (bottom - tolerance)) and (latest_close <= (top + tolerance))
            if not in_zone:
                continue

            # Mitigation filter: if any candle body closed inside the OB zone
            # after its creation, the zone is consumed (single-use)
            origin_idx = zone.get("origin_index")
            if origin_idx is not None:
                origin_idx = int(origin_idx)
                mitigated = False
                for c in candles[origin_idx + 2:]:
                    c_close = float(c.get("close", 0.0) or 0.0)
                    if bottom <= c_close <= top:
                        mitigated = True
                        break
                if mitigated:
                    continue

            zone_type = str(zone.get("zone_type", ""))
            metadata = {
                "zone_type": zone_type,
                "zone_origin": zone.get("origin_candle_time", ""),
                "zone_reaction": True,
                "zone_top": top,
                "zone_bottom": bottom,
                "timeframe_origin": timeframe_origin,
            }
            if zone_type == "ob_bullish":
                stop_loss = float(zone.get("wick_low", bottom) or bottom) - (atr * 0.2)
                setups.append(
                    self._make_setup(
                        symbol=symbol,
                        setup_type="order_block_retest",
                        side="buy",
                        entry=mid,
                        stop_loss=stop_loss,
                        pip_size=pip_size,
                        rr=rr,
                        confidence=confidence,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=mid,
                        metadata=metadata,
                    )
                )
            elif zone_type == "ob_bearish":
                stop_loss = float(zone.get("wick_high", top) or top) + (atr * 0.2)
                setups.append(
                    self._make_setup(
                        symbol=symbol,
                        setup_type="order_block_retest",
                        side="sell",
                        entry=mid,
                        stop_loss=stop_loss,
                        pip_size=pip_size,
                        rr=rr,
                        confidence=confidence,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=mid,
                        metadata=metadata,
                    )
                )
            if setups:
                break
        return setups

    def _fvg_reaction(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> list[FastSetup]:
        setups: list[FastSetup] = []
        setups.extend(
            self._fvg_reaction_for_series(
                symbol=symbol,
                candles=candles_m5[-180:],
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=rr,
                timeframe_origin="M5",
                confidence=0.80,
            )
        )
        setups.extend(
            self._fvg_reaction_for_series(
                symbol=symbol,
                candles=candles_htf[-180:],
                latest_close=latest_close,
                atr=atr,
                pip_size=pip_size,
                rr=rr,
                timeframe_origin="M30",
                confidence=0.83,
            )
        )
        return setups

    def _fvg_reaction_for_series(
        self,
        *,
        symbol: str,
        candles: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
        timeframe_origin: str,
        confidence: float,
    ) -> list[FastSetup]:
        fvgs = detect_fair_value_gaps(candles, max_zones=8)
        tolerance = atr * 0.25
        for zone in fvgs:
            if bool(zone.get("mitigated", False)):
                continue
            top = float(zone.get("price_high", 0.0) or 0.0)
            bottom = float(zone.get("price_low", 0.0) or 0.0)
            if top <= 0 or bottom <= 0:
                continue
            if not ((bottom - tolerance) <= latest_close <= (top + tolerance)):
                continue
            zone_type = str(zone.get("zone_type", ""))
            mid = (top + bottom) / 2.0
            metadata = {
                "zone_type": zone_type,
                "zone_reaction": True,
                "zone_top": top,
                "zone_bottom": bottom,
                "timeframe_origin": timeframe_origin,
            }
            if zone_type == "fvg_bullish":
                return [
                    self._make_setup(
                        symbol=symbol,
                        setup_type="fvg_reaction",
                        side="buy",
                        entry=mid,
                        stop_loss=bottom - atr * 0.2,
                        pip_size=pip_size,
                        rr=rr,
                        confidence=confidence,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=top,
                        metadata=metadata,
                    )
                ]
            if zone_type == "fvg_bearish":
                return [
                    self._make_setup(
                        symbol=symbol,
                        setup_type="fvg_reaction",
                        side="sell",
                        entry=mid,
                        stop_loss=top + atr * 0.2,
                        pip_size=pip_size,
                        rr=rr,
                        confidence=confidence,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=bottom,
                        metadata=metadata,
                    )
                ]
        return []

    def _liquidity_sweep_reclaim(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]],
        structure_htf: dict[str, Any],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> list[FastSetup]:
        liquidity = detect_liquidity_pools(candles_htf[-140:], candles_m5[-180:], structure=structure_htf, max_zones=10)
        sweeps = detect_sweeps(candles_m5[-180:], liquidity, lookback=60)
        if not sweeps:
            return []
        sweep = sweeps[0]
        zone_type = str(sweep.get("zone_type", ""))
        swept_level = float(sweep.get("swept_level", 0.0) or 0.0)
        if zone_type == "sweep_ssl" and latest_close > swept_level > 0:
            return [
                self._make_setup(
                    symbol=symbol,
                    setup_type="liquidity_sweep_reclaim",
                    side="buy",
                    entry=latest_close,
                    stop_loss=min(float(sweep.get("price_low", latest_close - atr) or (latest_close - atr)), latest_close - atr * 0.5),
                    pip_size=pip_size,
                    rr=rr,
                    confidence=0.84,
                    requires_pending=False,
                    pending_entry_type="market",
                    retest_level=swept_level,
                    metadata={
                        "sweep_candle_time": sweep.get("sweep_candle_time", ""),
                        "zone_reaction": True,
                        "zone_type": zone_type,
                        "zone_top": latest_close,
                        "zone_bottom": float(sweep.get("price_low", latest_close - atr) or (latest_close - atr)),
                        "timeframe_origin": "M5",
                    },
                )
            ]
        if zone_type == "sweep_bsl" and latest_close < swept_level and swept_level > 0:
            return [
                self._make_setup(
                    symbol=symbol,
                    setup_type="liquidity_sweep_reclaim",
                    side="sell",
                    entry=latest_close,
                    stop_loss=max(float(sweep.get("price_high", latest_close + atr) or (latest_close + atr)), latest_close + atr * 0.5),
                    pip_size=pip_size,
                    rr=rr,
                    confidence=0.84,
                    requires_pending=False,
                    pending_entry_type="market",
                    retest_level=swept_level,
                    metadata={
                        "sweep_candle_time": sweep.get("sweep_candle_time", ""),
                        "zone_reaction": True,
                        "zone_type": zone_type,
                        "zone_top": float(sweep.get("price_high", latest_close + atr) or (latest_close + atr)),
                        "zone_bottom": latest_close,
                        "timeframe_origin": "M5",
                    },
                )
            ]
        return []

    def _breakout_retest(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        structure_m5: dict[str, Any],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> list[FastSetup]:
        bos = structure_m5.get("last_bos") if isinstance(structure_m5.get("last_bos"), dict) else None
        if not bos:
            return []
        direction = str(bos.get("direction", ""))
        level = float(bos.get("price", 0.0) or 0.0)
        if level <= 0:
            return []

        # BOS age filter — reject stale breakouts (>20 candles old)
        bos_idx = int(bos.get("index", 0) or 0)
        candle_count = len(candles_m5[-180:])
        if candle_count > 0 and (candle_count - 1 - bos_idx) > 20:
            return []

        near_retest = abs(latest_close - level) <= atr * 0.5
        if not near_retest:
            return []

        # Impulse validation: BOS candle (and neighbors) must have above-average bodies
        bos_idx = int(bos.get("index", 0) or 0)
        slice_m5 = candles_m5[-180:]
        if slice_m5:
            all_bodies = [abs(float(c.get("close", 0) or 0) - float(c.get("open", 0) or 0)) for c in slice_m5]
            avg_body = sum(all_bodies) / len(all_bodies) if all_bodies else 0.0
            # Check BOS candle ±1 neighborhood
            bos_range = slice_m5[max(0, bos_idx - 1): bos_idx + 2]
            bos_bodies = [abs(float(c.get("close", 0) or 0) - float(c.get("open", 0) or 0)) for c in bos_range]
            max_bos_body = max(bos_bodies) if bos_bodies else 0.0
            if avg_body > 0 and max_bos_body < avg_body * 1.2:
                return []  # BOS without impulse — weak breakout

        if direction == "bullish":
            return [
                self._make_setup(
                    symbol=symbol,
                    setup_type="breakout_retest",
                    side="buy",
                    entry=level,
                    stop_loss=level - atr * 0.9,
                    pip_size=pip_size,
                    rr=rr,
                    confidence=0.79,
                    requires_pending=True,
                    pending_entry_type="stop",
                    retest_level=level,
                    metadata={"bos_index": bos.get("index", -1)},
                )
            ]
        if direction == "bearish":
            return [
                self._make_setup(
                    symbol=symbol,
                    setup_type="breakout_retest",
                    side="sell",
                    entry=level,
                    stop_loss=level + atr * 0.9,
                    pip_size=pip_size,
                    rr=rr,
                    confidence=0.79,
                    requires_pending=True,
                    pending_entry_type="stop",
                    retest_level=level,
                    metadata={"bos_index": bos.get("index", -1)},
                )
            ]
        return []

    def _pattern_setups(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
        m30_bias: str,
    ) -> list[FastSetup]:
        setups: list[FastSetup] = []
        setup = self._wedge_retest(symbol, candles_m5, latest_close, atr, pip_size, rr)
        if setup:
            setups.append(setup)
        setup = self._flag_retest(symbol, candles_m5, latest_close, atr, pip_size, rr)
        if setup:
            setups.append(setup)
        setup = self._triangle_retest(symbol, candles_m5, latest_close, atr, pip_size, rr, m30_bias)
        if setup:
            setups.append(setup)
        setup = self._sr_polarity_retest(symbol, candles_m5, latest_close, atr, pip_size, rr)
        if setup:
            setups.append(setup)
        return setups

    def _wedge_retest(
        self,
        symbol: str,
        candles: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> FastSetup | None:
        sample = candles[-18:]
        if len(sample) < 18:
            return None
        first = sample[0]
        last = sample[-1]
        high1 = float(first.get("high", 0.0) or 0.0)
        low1 = float(first.get("low", 0.0) or 0.0)
        high2 = float(last.get("high", 0.0) or 0.0)
        low2 = float(last.get("low", 0.0) or 0.0)
        if min(high1, low1, high2, low2) <= 0:
            return None
        range1 = max(0.0, high1 - low1)
        range2 = max(0.0, high2 - low2)
        if range2 <= 0 or range1 < range2 * 1.2:
            return None
        # Rising wedge -> bearish retest. Falling wedge -> bullish retest.
        if high2 > high1 and low2 > low1:
            level = low2
            return self._make_setup(
                symbol=symbol,
                setup_type="wedge_retest",
                side="sell",
                entry=level,
                stop_loss=level + atr,
                pip_size=pip_size,
                rr=rr,
                confidence=0.69,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"pattern": "rising_wedge"},
            )
        if high2 < high1 and low2 < low1:
            level = high2
            return self._make_setup(
                symbol=symbol,
                setup_type="wedge_retest",
                side="buy",
                entry=level,
                stop_loss=level - atr,
                pip_size=pip_size,
                rr=rr,
                confidence=0.69,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"pattern": "falling_wedge"},
            )
        return None

    def _flag_retest(
        self,
        symbol: str,
        candles: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> FastSetup | None:
        if len(candles) < 26:
            return None
        impulse = candles[-24:-10]
        flag = candles[-10:]
        impulse_open = float(impulse[0].get("open", 0.0) or 0.0)
        impulse_close = float(impulse[-1].get("close", 0.0) or 0.0)
        if impulse_open <= 0 or impulse_close <= 0:
            return None
        move = impulse_close - impulse_open
        flag_high = max(float(c.get("high", 0.0) or 0.0) for c in flag)
        flag_low = min(float(c.get("low", 0.0) or 0.0) for c in flag)
        flag_range = max(0.0, flag_high - flag_low)
        if flag_range <= 0:
            return None
        flag_open = float(flag[0].get("open", 0.0) or 0.0)
        flag_close = float(flag[-1].get("close", 0.0) or 0.0)
        if abs(move) < flag_range * 2.2:
            return None
        if move > 0 and flag_close <= flag_open:
            level = (flag_high + flag_low) / 2.0
            return self._make_setup(
                symbol=symbol,
                setup_type="flag_retest",
                side="buy",
                entry=level,
                stop_loss=flag_low - atr * 0.2,
                pip_size=pip_size,
                rr=rr,
                confidence=0.66,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"pattern": "bull_flag"},
            )
        if move < 0 and flag_close >= flag_open:
            level = (flag_high + flag_low) / 2.0
            return self._make_setup(
                symbol=symbol,
                setup_type="flag_retest",
                side="sell",
                entry=level,
                stop_loss=flag_high + atr * 0.2,
                pip_size=pip_size,
                rr=rr,
                confidence=0.66,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"pattern": "bear_flag"},
            )
        return None

    def _triangle_retest(
        self,
        symbol: str,
        candles: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
        m30_bias: str,
    ) -> FastSetup | None:
        sample = candles[-16:]
        if len(sample) < 16:
            return None
        highs = [float(c.get("high", 0.0) or 0.0) for c in sample]
        lows = [float(c.get("low", 0.0) or 0.0) for c in sample]
        if min(highs + lows) <= 0:
            return None
        descending_highs = highs[-1] < highs[0]
        ascending_lows = lows[-1] > lows[0]
        contraction = (highs[0] - lows[0]) > (highs[-1] - lows[-1]) * 1.25
        if not (descending_highs and ascending_lows and contraction):
            return None
        side = m30_bias if m30_bias in {"buy", "sell"} else ("buy" if latest_close >= (sum(highs[-4:]) / 4.0) else "sell")
        level = latest_close
        stop_loss = (min(lows[-6:]) - atr * 0.15) if side == "buy" else (max(highs[-6:]) + atr * 0.15)
        return self._make_setup(
            symbol=symbol,
            setup_type="triangle_retest",
            side=side,
            entry=level,
            stop_loss=stop_loss,
            pip_size=pip_size,
            rr=rr,
            confidence=0.64,
            requires_pending=True,
            pending_entry_type="stop",
            retest_level=level,
            metadata={"pattern": "triangle"},
        )

    def _sr_polarity_retest(
        self,
        symbol: str,
        candles: list[dict[str, Any]],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> FastSetup | None:
        structure = detect_market_structure(candles[-180:], window=3)
        bos = structure.get("last_bos") if isinstance(structure.get("last_bos"), dict) else None
        if not bos:
            return None
        level = float(bos.get("price", 0.0) or 0.0)
        direction = str(bos.get("direction", ""))
        if level <= 0:
            return None
        near = abs(latest_close - level) <= atr * 0.45
        if not near:
            return None
        if direction == "bullish":
            return self._make_setup(
                symbol=symbol,
                setup_type="sr_polarity_retest",
                side="buy",
                entry=level,
                stop_loss=level - atr * 0.8,
                pip_size=pip_size,
                rr=rr,
                confidence=0.68,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"polarity": "resistance_to_support"},
            )
        if direction == "bearish":
            return self._make_setup(
                symbol=symbol,
                setup_type="sr_polarity_retest",
                side="sell",
                entry=level,
                stop_loss=level + atr * 0.8,
                pip_size=pip_size,
                rr=rr,
                confidence=0.68,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=level,
                metadata={"polarity": "support_to_resistance"},
            )
        return None

    @staticmethod
    def _atr(candles: list[dict[str, Any]], period: int) -> float:
        trs: list[float] = []
        for idx in range(1, len(candles)):
            high = float(candles[idx].get("high", 0.0) or 0.0)
            low = float(candles[idx].get("low", 0.0) or 0.0)
            prev_close = float(candles[idx - 1].get("close", 0.0) or 0.0)
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        if not trs:
            return 0.0
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window)

    @staticmethod
    def _make_setup(
        *,
        symbol: str,
        setup_type: str,
        side: str,
        entry: float,
        stop_loss: float,
        pip_size: float,
        rr: float,
        confidence: float,
        requires_pending: bool,
        pending_entry_type: str,
        retest_level: float | None,
        metadata: dict[str, Any],
    ) -> FastSetup:
        safe_entry = float(entry)
        safe_stop = float(stop_loss)
        risk = abs(safe_entry - safe_stop)
        if side == "buy":
            tp = safe_entry + (risk * rr)
        else:
            tp = safe_entry - (risk * rr)
        risk_pips = risk / pip_size if pip_size > 0 else 0.0
        setup_id = f"{symbol}_{setup_type}_{side}"
        return FastSetup(
            setup_id=setup_id,
            setup_type=setup_type,
            symbol=symbol,
            side=side,
            entry_price=round(safe_entry, 10),
            stop_loss=round(safe_stop, 10),
            take_profit=round(tp, 10),
            risk_pips=round(risk_pips, 4),
            confidence=round(confidence, 4),
            requires_pending=requires_pending,
            pending_entry_type=pending_entry_type,
            retest_level=retest_level,
            metadata=metadata,
        )
