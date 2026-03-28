from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from heuristic_mt5_bridge.smc_desk.detection.liquidity import detect_liquidity_pools, detect_sweeps
from heuristic_mt5_bridge.smc_desk.detection.order_blocks import detect_order_blocks
from heuristic_mt5_bridge.smc_desk.detection.structure import detect_market_structure


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
        candles_h1: list[dict[str, Any]],
        pip_size: float,
        h1_bias: str,
        spread_pips: float = 0.0,
    ) -> list[FastSetup]:
        if len(candles_m5) < 40 or len(candles_h1) < 20 or pip_size <= 0:
            return []

        cfg = self.config
        atr = max(self._atr(candles_m5, 14), pip_size * 8)
        latest_close = float(candles_m5[-1].get("close", 0.0) or 0.0)
        if latest_close <= 0:
            return []

        structure_m5 = detect_market_structure(candles_m5[-180:], window=3)
        structure_h1 = detect_market_structure(candles_h1[-200:], window=3)

        # Premium/Discount zone boundary from H1 impulse
        impulse_high = float(structure_h1.get("last_impulse_high") or 0.0)
        impulse_low = float(structure_h1.get("last_impulse_low") or 0.0)
        pd_mid = float(structure_h1.get("premium_discount_level") or 0.0)
        if pd_mid <= 0 and impulse_high > 0 and impulse_low > 0:
            pd_mid = (impulse_high + impulse_low) / 2.0

        setups: list[FastSetup] = []
        setups.extend(
            self._order_block_retest(
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
            self._liquidity_sweep_reclaim(
                symbol=symbol,
                candles_m5=candles_m5,
                candles_h1=candles_h1,
                structure_h1=structure_h1,
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
                h1_bias=h1_bias,
            )
        )

        filtered = [setup for setup in setups if setup.confidence >= cfg.min_confidence and setup.risk_pips > 0]

        # Premium/Discount zone filter: buy in discount, sell in premium
        if pd_mid > 0:
            pd_filtered: list[FastSetup] = []
            for s in filtered:
                if s.side == "buy" and s.entry_price > pd_mid:
                    continue  # buying in premium zone — skip
                if s.side == "sell" and s.entry_price < pd_mid:
                    continue  # selling in discount zone — skip
                pd_filtered.append(s)
            filtered = pd_filtered

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
        return filtered

    def _order_block_retest(
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
        zones = detect_order_blocks(candles_m5[-180:], structure_m5, min_impulse_candles=3, max_zones=6)
        setups: list[FastSetup] = []
        tolerance = atr * 0.35
        candle_slice = candles_m5[-180:]
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
                for c in candle_slice[origin_idx + 2:]:
                    c_close = float(c.get("close", 0.0) or 0.0)
                    if bottom <= c_close <= top:
                        mitigated = True
                        break
                if mitigated:
                    continue

            zone_type = str(zone.get("zone_type", ""))
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
                        confidence=0.82,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=mid,
                        metadata={"zone_type": zone_type, "zone_origin": zone.get("origin_candle_time", "")},
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
                        confidence=0.82,
                        requires_pending=True,
                        pending_entry_type="limit",
                        retest_level=mid,
                        metadata={"zone_type": zone_type, "zone_origin": zone.get("origin_candle_time", "")},
                    )
                )
            if setups:
                break
        return setups

    def _liquidity_sweep_reclaim(
        self,
        *,
        symbol: str,
        candles_m5: list[dict[str, Any]],
        candles_h1: list[dict[str, Any]],
        structure_h1: dict[str, Any],
        latest_close: float,
        atr: float,
        pip_size: float,
        rr: float,
    ) -> list[FastSetup]:
        liquidity = detect_liquidity_pools(candles_h1[-140:], candles_m5[-180:], structure=structure_h1, max_zones=10)
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
                    metadata={"sweep_candle_time": sweep.get("sweep_candle_time", "")},
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
                    metadata={"sweep_candle_time": sweep.get("sweep_candle_time", "")},
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
        h1_bias: str,
    ) -> list[FastSetup]:
        setups: list[FastSetup] = []
        setup = self._wedge_retest(symbol, candles_m5, latest_close, atr, pip_size, rr)
        if setup:
            setups.append(setup)
        setup = self._flag_retest(symbol, candles_m5, latest_close, atr, pip_size, rr)
        if setup:
            setups.append(setup)
        setup = self._triangle_retest(symbol, candles_m5, latest_close, atr, pip_size, rr, h1_bias)
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
        h1_bias: str,
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
        side = h1_bias if h1_bias in {"buy", "sell"} else ("buy" if latest_close >= (sum(highs[-4:]) / 4.0) else "sell")
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
