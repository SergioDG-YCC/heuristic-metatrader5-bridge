import type { Component } from "solid-js";
import { Show, For, onMount, onCleanup, createSignal, createMemo, createEffect, untrack } from "solid-js";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  LineStyle,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type LineWidth,
  type UTCTimestamp,
} from "lightweight-charts";
import { runtimeStore } from "../stores/runtimeStore";
import { operationsStore, initOperationsStore } from "../stores/operationsStore";
import { fastOperationsStore, initFastOperationsStore } from "../stores/fastOperationsStore";
import { fetchChart, getChartEntry } from "../stores/chartsStore";
import { api } from "../api/client";
import type {
  PositionRow,
  FastScanEvent,
  FastSignalRow,
  FastTradeLogRow,
  FastSymbolSummary,
  FastZoneRow,
  SmcZone,
  Candle,
} from "../types/api";

function numStr(v: unknown, dp = 5): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function decimalPlaces(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const text = value.toString().toLowerCase();
  if (text.includes("e-")) {
    const [base, expRaw] = text.split("e-");
    const exp = Number(expRaw);
    const baseDecimals = base.includes(".") ? base.split(".")[1].length : 0;
    return Number.isFinite(exp) ? baseDecimals + exp : baseDecimals;
  }
  if (!text.includes(".")) return 0;
  return text.split(".")[1].replace(/0+$/, "").length;
}

function inferPricePrecision(candles: CandlestickData[]): number {
  let maxDp = 0;
  for (const candle of candles) {
    maxDp = Math.max(
      maxDp,
      decimalPlaces(candle.open),
      decimalPlaces(candle.high),
      decimalPlaces(candle.low),
      decimalPlaces(candle.close),
    );
  }
  return Math.min(6, Math.max(2, maxDp));
}

function toUtcTimestamp(value: unknown): UTCTimestamp | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    const sec = value > 1_000_000_000_000 ? Math.floor(value / 1000) : Math.floor(value);
    return sec as UTCTimestamp;
  }
  if (typeof value === "string") {
    const asNum = Number(value);
    if (Number.isFinite(asNum)) {
      const sec = asNum > 1_000_000_000_000 ? Math.floor(asNum / 1000) : Math.floor(asNum);
      return sec as UTCTimestamp;
    }
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) {
      return Math.floor(parsed / 1000) as UTCTimestamp;
    }
  }
  return null;
}

function candleToSeries(candle: Candle): CandlestickData | null {
  const time = toUtcTimestamp(candle.time ?? candle.timestamp ?? candle.t);
  const open = toNumber(candle.open);
  const high = toNumber(candle.high);
  const low = toNumber(candle.low);
  const close = toNumber(candle.close);
  if (time == null || open == null || high == null || low == null || close == null) return null;
  return { time, open, high, low, close };
}

function mergeLiveCandle(base: CandlestickData[], live: CandlestickData | null): CandlestickData[] {
  if (!live) return base;
  if (base.length === 0) return [live];
  const out = [...base];
  const last = out[out.length - 1];
  if (Number(last.time) === Number(live.time)) {
    out[out.length - 1] = live;
    return out;
  }
  if (Number(last.time) < Number(live.time)) {
    out.push(live);
    return out;
  }
  const idx = out.findIndex((item) => Number(item.time) === Number(live.time));
  if (idx >= 0) out[idx] = live;
  return out.sort((a, b) => Number(a.time) - Number(b.time));
}

function isBuyType(v: string | undefined): boolean {
  return v === "buy";
}

function typeLabel(v: string | undefined): string {
  return v ? v.toUpperCase() : "—";
}

function zoneLineColor(zoneType: string): string {
  const zt = (zoneType || "").toLowerCase();
  if (zt.includes("bullish")) return "#22c55e77";
  if (zt.includes("bearish")) return "#ef44446e";
  if (zt.includes("fvg")) return "#f5a5235e";
  if (zt.includes("liquidity") || zt.includes("equal")) return "#22d3ee5e";
  return "#64748b";
}

function zoneDisplayLabel(zoneType: string): string {
  const zt = (zoneType || "").toLowerCase();
  if (zt === "ob_bullish") return "OB Bull";
  if (zt === "ob_bearish") return "OB Bear";
  if (zt === "fvg_bullish") return "FVG Bull";
  if (zt === "fvg_bearish") return "FVG Bear";
  if (zt === "liquidity_bsl") return "Liq BSL";
  if (zt === "liquidity_ssl") return "Liq SSL";
  if (zt === "equal_highs") return "Equal Highs";
  if (zt === "equal_lows") return "Equal Lows";
  if (zt === "sweep_bsl") return "Sweep BSL";
  if (zt === "sweep_ssl") return "Sweep SSL";
  return String(zoneType || "Zone").replaceAll("_", " ");
}

function normalizeTimeframe(value: unknown): string {
  const normalized = String(value || "").toUpperCase();
  if (normalized === "D") return "D1";
  return normalized;
}

function posCardAccent(side: string | undefined): string {
  return side === "buy" ? "var(--green)" : "var(--red)";
}

function uniqueSymbols(values: Array<string | null | undefined>): string[] {
  return Array.from(
    new Set(
      values
        .map((value) => String(value || "").trim().toUpperCase())
        .filter((value) => value.length > 0)
    )
  ).sort();
}

type ZoneToggleGroup = {
  key: string;
  source: "FAST" | "SMC";
  timeframe: string;
  zoneType: string;
  label: string;
  color: string;
  count: number;
  enabled: boolean;
};

const chartTimeframes = ["M1", "M5", "M30"] as const;
type ChartTf = (typeof chartTimeframes)[number];

type TickStreamPayload = {
  status?: string;
  symbol?: string;
  timeframe?: string;
  bid?: number | string;
  ask?: number | string;
  spread?: number | string;
  updated_at?: string;
  bar?: Candle | null;
};

type PriceLinePresetKey =
  | "entry"
  | "stopLoss"
  | "takeProfit"
  | "zoneLow"
  | "zoneHigh"
  | "bid"
  | "ask";

const PRICE_LINE_PRESETS: Record<
  PriceLinePresetKey,
  { color: string; lineWidth: LineWidth; lineStyle: LineStyle }
> = {
  entry: { color: "rgba(34, 211, 238, 0.45)", lineWidth: 3, lineStyle: LineStyle.Solid },
  stopLoss: { color: "rgba(239, 68, 68, 0.68)", lineWidth: 2, lineStyle: LineStyle.Solid },
  takeProfit: { color: "rgba(34, 197, 94, 0.30)", lineWidth: 3, lineStyle: LineStyle.Solid },
  zoneLow: { color: "rgba(100, 116, 139, 0.42)", lineWidth: 2, lineStyle: LineStyle.Solid },
  zoneHigh: { color: "rgba(100, 116, 139, 0.42)", lineWidth: 2, lineStyle: LineStyle.Solid },
  bid: { color: "rgba(245, 158, 11, 0.7)", lineWidth: 1, lineStyle: LineStyle.Solid },
  ask: { color: "rgba(34, 211, 238, 0.7)", lineWidth: 1, lineStyle: LineStyle.Solid },
};

const FastDesk: Component = () => {
  const [fastConfig, setFastConfig] = createSignal<any>(null);
  const [deskStatus, setDeskStatus] = createSignal<any>(null);
  const [loading, setLoading] = createSignal(true);
  const [activityEvents, setActivityEvents] = createSignal<FastScanEvent[]>([]);
  const [symbolSummary, setSymbolSummary] = createSignal<Record<string, FastSymbolSummary>>({});
  const [signals, setSignals] = createSignal<FastSignalRow[]>([]);
  const [tradeLog, setTradeLog] = createSignal<FastTradeLogRow[]>([]);
  const [fastZones, setFastZones] = createSignal<FastZoneRow[]>([]);
  const [smcZones, setSmcZones] = createSignal<SmcZone[]>([]);
  const [selectedSymbol, setSelectedSymbol] = createSignal("");
  const [selectedTimeframe, setSelectedTimeframe] = createSignal<ChartTf>("M5");
  const [zoneVisibility, setZoneVisibility] = createSignal<Record<string, boolean>>({});
  const [chartPrecision, setChartPrecision] = createSignal(5);
  const [liveTick, setLiveTick] = createSignal<{ bid: number | null; ask: number | null; spread: number | null; updatedAt: string | null }>({
    bid: null,
    ask: null,
    spread: null,
    updatedAt: null,
  });
  const [liveBar, setLiveBar] = createSignal<CandlestickData | null>(null);

  let activityTimer: ReturnType<typeof setInterval> | undefined;
  let signalsTimer: ReturnType<typeof setInterval> | undefined;
  let zonesTimer: ReturnType<typeof setInterval> | undefined;
  let chartHost: HTMLDivElement | undefined;
  let chartApi: IChartApi | undefined;
  let candleSeries: ReturnType<IChartApi["addSeries"]> | undefined;
  let strategyLines: IPriceLine[] = [];
  let livePriceLines: IPriceLine[] = [];
  let resizeObserver: ResizeObserver | undefined;
  let tickSource: EventSource | undefined;

  const snap = () => runtimeStore.snapshot;
  const exp = () => operationsStore.exposure;
  // Use desk-scoped store for positions and orders — only fast_owned/inherited_fast tickets.
  const positions = () => fastOperationsStore.positions as PositionRow[];
  const acct = () => operationsStore.account?.account_state;

  const availableSymbols = createMemo(() =>
    uniqueSymbols([
      ...positions().map((p) => String(p.symbol || "")),
      ...fastZones().map((z) => z.symbol),
      ...smcZones().map((z) => String(z.symbol || "")),
      ...Object.keys(symbolSummary()),
      ...((snap()?.universes?.subscribed_universe || []) as string[]),
    ])
  );
  const focusSym = () => positions()[0]?.symbol ?? availableSymbols()[0] ?? "";

  /** Last signal per symbol for the rail cards */
  const lastSignalBySymbol = createMemo(() => {
    const map: Record<string, FastSignalRow> = {};
    for (const sig of signals()) {
      const sym = String(sig.symbol || "").toUpperCase();
      if (!sym) continue;
      const existing = map[sym];
      if (!existing || (sig.generated_at || "") > (existing.generated_at || "")) {
        map[sym] = sig;
      }
    }
    return map;
  });

  /** Position count per symbol */
  const positionCountBySymbol = createMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of positions()) {
      const sym = String(p.symbol || "").toUpperCase();
      counts[sym] = (counts[sym] ?? 0) + 1;
    }
    return counts;
  });

  const chartEntry = createMemo(() => {
    const symbol = selectedSymbol();
    if (!symbol) return undefined;
    return getChartEntry(symbol, selectedTimeframe());
  });
  const selectedPositions = createMemo(() => positions().filter((p) => p.symbol === selectedSymbol()));
  const selectedFastZones = createMemo(() =>
    fastZones().filter((z) => {
      if (z.symbol !== selectedSymbol()) return false;
      const display = Array.isArray(z.display_timeframes) && z.display_timeframes.length > 0
        ? z.display_timeframes.map((tf) => normalizeTimeframe(tf))
        : [normalizeTimeframe(z.timeframe_origin)];
      return display.includes(selectedTimeframe());
    })
  );
  const selectedSmcZones = createMemo(() =>
    smcZones()
      .filter((z) => z.symbol === selectedSymbol())
  );
  const selectedFastGroups = createMemo<ZoneToggleGroup[]>(() => {
    const counts = new Map<string, ZoneToggleGroup>();
    for (const z of selectedFastZones()) {
      const timeframe = String(z.timeframe_origin || selectedTimeframe()).toUpperCase();
      const zoneType = String(z.zone_type || "");
      const key = `FAST:${timeframe}:${zoneType}`;
      const enabled = zoneVisibility()[key] ?? true;
      const current = counts.get(key);
      if (current) {
        current.count += 1;
        continue;
      }
      counts.set(key, {
        key,
        source: "FAST",
        timeframe,
        zoneType,
        label: zoneDisplayLabel(zoneType),
        color: zoneLineColor(zoneType),
        count: 1,
        enabled,
      });
    }
    return Array.from(counts.values()).sort((a, b) =>
      a.timeframe.localeCompare(b.timeframe) || a.label.localeCompare(b.label)
    );
  });
  const selectedSmcGroups = createMemo<ZoneToggleGroup[]>(() => {
    const counts = new Map<string, ZoneToggleGroup>();
    for (const z of selectedSmcZones()) {
      const timeframeRaw = normalizeTimeframe((z as any).timeframe || (z as any).tf || "H4");
      const timeframe = timeframeRaw === "D1" ? "D" : timeframeRaw;
      const zoneType = String(z.zone_type || "");
      const key = `SMC:${timeframe}:${zoneType}`;
      const enabled = zoneVisibility()[key] ?? false;
      const current = counts.get(key);
      if (current) {
        current.count += 1;
        continue;
      }
      counts.set(key, {
        key,
        source: "SMC",
        timeframe,
        zoneType,
        label: zoneDisplayLabel(zoneType),
        color: zoneLineColor(zoneType),
        count: 1,
        enabled,
      });
    }
    return Array.from(counts.values()).sort((a, b) =>
      a.timeframe.localeCompare(b.timeframe) || a.label.localeCompare(b.label)
    );
  });
  const visibleFastZones = createMemo(() => {
    const enabled = new Set(selectedFastGroups().filter((g) => g.enabled).map((g) => g.key));
    return selectedFastZones().filter((z) =>
      enabled.has(`FAST:${String(z.timeframe_origin || selectedTimeframe()).toUpperCase()}:${String(z.zone_type || "")}`)
    );
  });
  const visibleSmcZones = createMemo(() => {
    const enabled = new Set(selectedSmcGroups().filter((g) => g.enabled).map((g) => g.key));
    return selectedSmcZones().filter((z) => {
      const timeframeRaw = normalizeTimeframe((z as any).timeframe || (z as any).tf || "H4");
      const timeframe = timeframeRaw === "D1" ? "D" : timeframeRaw;
      return enabled.has(`SMC:${timeframe}:${String(z.zone_type || "")}`);
    });
  });
  const chartLegendItems = createMemo(() => [
    { label: "Entry", color: PRICE_LINE_PRESETS.entry.color },
    { label: "SL", color: PRICE_LINE_PRESETS.stopLoss.color },
    { label: "TP", color: PRICE_LINE_PRESETS.takeProfit.color },
    { label: "Bid", color: PRICE_LINE_PRESETS.bid.color },
    { label: "Ask", color: PRICE_LINE_PRESETS.ask.color },
    { label: "FAST Zone", color: "rgba(45,185,166,0.72)" },
    { label: "SMC Zone", color: "rgba(59,130,246,0.55)" },
  ]);

  function clearStrategyLines() {
    if (!candleSeries) return;
    for (const line of strategyLines) candleSeries.removePriceLine(line);
    strategyLines = [];
  }

  function clearLivePriceLines() {
    if (!candleSeries) return;
    for (const line of livePriceLines) candleSeries.removePriceLine(line);
    livePriceLines = [];
  }

  function createPriceLine(
    price: number,
    title: string,
    presetKey: PriceLinePresetKey,
    colorOverride?: string,
  ): IPriceLine | null {
    if (!candleSeries) return null;
    const preset = PRICE_LINE_PRESETS[presetKey];
    const hideLabel = presetKey === "zoneLow" || presetKey === "zoneHigh";
    return candleSeries.createPriceLine({
      price,
      color: colorOverride || preset.color,
      lineWidth: preset.lineWidth,
      lineStyle: preset.lineStyle,
      axisLabelVisible: !hideLabel,
      lineVisible: true,
      title: hideLabel ? "" : title,
    });
  }

  function addStrategyLine(
    price: number,
    title: string,
    presetKey: Exclude<PriceLinePresetKey, "bid" | "ask">,
    colorOverride?: string,
  ) {
    const line = createPriceLine(price, title, presetKey, colorOverride);
    if (line) strategyLines.push(line);
  }

  function updateLivePriceLines() {
    if (!candleSeries) return;
    clearLivePriceLines();
    const tick = liveTick();
    if (tick.bid != null) {
      const line = createPriceLine(tick.bid, "BID", "bid");
      if (line) livePriceLines.push(line);
    }
    if (tick.ask != null) {
      const line = createPriceLine(tick.ask, "ASK", "ask");
      if (line) livePriceLines.push(line);
    }
  }

  function toggleZoneVisibility(key: string) {
    setZoneVisibility((current) => ({
      ...current,
      [key]: !(current[key] ?? key.startsWith("FAST:")),
    }));
  }

  function setupChart() {
    if (!chartHost || chartApi) return;
    chartApi = createChart(chartHost, {
      width: chartHost.clientWidth,
      height: chartHost.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#14161a" },
        textColor: "#8c95a6",
      },
      grid: {
        vertLines: { color: "rgba(37, 44, 56, 0)" },
        horzLines: { color: "rgba(37, 44, 56, 0)" },
      },
      rightPriceScale: {
        borderColor: "#252c38",
        scaleMargins: { top: 0.02, bottom: 0.03 },
      },
      timeScale: {
        borderColor: "#252c38",
        timeVisible: true,
        rightOffset: 24,
      },
      crosshair: {
        vertLine: { color: "rgba(45,212,191,0.25)", width: 1 },
        horzLine: { color: "rgba(45,212,191,0.25)", width: 1 },
      },
    });

    candleSeries = chartApi.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      priceLineVisible: false,
      lastValueVisible: false,
    });

    resizeObserver = new ResizeObserver((entries) => {
      if (!chartApi) return;
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      chartApi.applyOptions({ width: rect.width, height: rect.height });
    });
    resizeObserver.observe(chartHost);
  }

  function resetChartView() {
    if (!chartApi) return;
    chartApi.priceScale("right").applyOptions({
      autoScale: true,
      scaleMargins: { top: 0.02, bottom: 0.03 },
    });
    chartApi.timeScale().fitContent();
    chartApi.timeScale().scrollToRealTime();
  }

  function closeTickStream() {
    if (!tickSource) return;
    tickSource.close();
    tickSource = undefined;
  }

  function openTickStream(symbol: string, timeframe: ChartTf) {
    closeTickStream();
    const endpoint = `/events/ticks/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&interval=1.0`;
    const source = new EventSource(endpoint);
    tickSource = source;

    source.onmessage = (event) => {
      let payload: TickStreamPayload;
      try {
        payload = JSON.parse(event.data) as TickStreamPayload;
      } catch {
        return;
      }
      if (String(payload.status || "success").toLowerCase() !== "success") return;

      setLiveTick({
        bid: toNumber(payload.bid),
        ask: toNumber(payload.ask),
        spread: toNumber(payload.spread),
        updatedAt: payload.updated_at || null,
      });

      const bar = payload.bar ? candleToSeries(payload.bar) : null;
      if (!bar) return;
      setLiveBar(bar);
      if (candleSeries) candleSeries.update(bar);
    };
  }

  onMount(() => {
    initOperationsStore();
    initFastOperationsStore();
    loadFastDeskData();
    pollActivity();
    pollSignals();
    pollZones();
    activityTimer = setInterval(pollActivity, 3000);
    signalsTimer = setInterval(pollSignals, 5000);
    zonesTimer = setInterval(pollZones, 10000);
    setupChart();
  });

  onCleanup(() => {
    if (activityTimer) clearInterval(activityTimer);
    if (signalsTimer) clearInterval(signalsTimer);
    if (zonesTimer) clearInterval(zonesTimer);
    closeTickStream();
    clearStrategyLines();
    clearLivePriceLines();
    if (resizeObserver) resizeObserver.disconnect();
    if (chartApi) {
      chartApi.remove();
      chartApi = undefined;
      candleSeries = undefined;
    }
  });

  createEffect(() => {
    const current = selectedSymbol();
    const fallback = focusSym();
    if ((!current || !availableSymbols().includes(current)) && fallback) {
      setSelectedSymbol(fallback);
    }
  });

  createEffect(() => {
    const symbol = selectedSymbol();
    const timeframe = selectedTimeframe();
    if (!symbol) return;
    untrack(() => {
      void fetchChart(symbol, timeframe, 350);
    });
  });

  createEffect(() => {
    const symbol = selectedSymbol();
    const timeframe = selectedTimeframe();
    setLiveBar(null);
    setLiveTick({ bid: null, ask: null, spread: null, updatedAt: null });
    clearLivePriceLines();
    if (!symbol) {
      closeTickStream();
      return;
    }
    openTickStream(symbol, timeframe);
  });

  createEffect(() => {
    setupChart();
    if (!chartApi || !candleSeries) return;

    const baseCandles = (chartEntry()?.data?.candles || [])
      .map((c) => candleToSeries(c as Candle))
      .filter((c): c is CandlestickData => c !== null)
      .sort((a, b) => Number(a.time) - Number(b.time));
    const candles = mergeLiveCandle(baseCandles, untrack(() => liveBar()));

    if (candles.length > 0) {
      const precision = inferPricePrecision(candles);
      setChartPrecision(precision);
      candleSeries.applyOptions({
        priceFormat: {
          type: "price",
          precision,
          minMove: 1 / 10 ** precision,
        },
      });
    }

    candleSeries.setData(candles);
    clearStrategyLines();

    // Always reset price scale so the chart adapts to the new symbol's range
    chartApi.priceScale("right").applyOptions({
      autoScale: true,
      scaleMargins: { top: 0.02, bottom: 0.03 },
    });

    for (const p of selectedPositions()) {
      const suffix = p.position_id ? ` #${p.position_id}` : "";
      const entry = toNumber(p.price_open);
      const sl = toNumber(p.stop_loss);
      const tp = toNumber(p.take_profit);
      if (entry != null) addStrategyLine(entry, `Entry${suffix}`, "entry");
      if (sl != null) addStrategyLine(sl, `SL${suffix}`, "stopLoss");
      if (tp != null) addStrategyLine(tp, `TP${suffix}`, "takeProfit");
    }

    for (const z of visibleFastZones()) {
      const low = toNumber(z.price_low);
      const high = toNumber(z.price_high);
      const color = zoneLineColor(String(z.zone_type || ""));
      const label = `${zoneDisplayLabel(String(z.zone_type || z.setup_type || "fast"))} ${String(z.timeframe_origin || "").toUpperCase()}`.trim();
      if (low != null) addStrategyLine(low, `${label} L`, "zoneLow", color);
      if (high != null && high !== low) addStrategyLine(high, `${label} H`, "zoneHigh", color);
    }

    for (const z of visibleSmcZones()) {
      const low = toNumber(z.price_low);
      const high = toNumber(z.price_high);
      const color = "rgba(59,130,246,0.55)";
      const label = String(z.zone_type || "zone").toUpperCase().slice(0, 10);
      if (low != null) addStrategyLine(low, `${label} L`, "zoneLow", color);
      if (high != null && high !== low) addStrategyLine(high, `${label} H`, "zoneHigh", color);
    }

    chartApi.timeScale().fitContent();
  });

  createEffect(() => {
    if (candleSeries) updateLivePriceLines();
  });

  async function pollActivity() {
    try {
      const r = await api.fastActivity(40);
      if (r.status === "success") {
        setActivityEvents(r.events);
        setSymbolSummary(r.per_symbol_summary);
      }
    } catch {
      // ignore
    }
  }

  async function pollSignals() {
    try {
      const [sigR, logR] = await Promise.all([api.fastSignals(30), api.fastTradeLog(30)]);
      if (sigR.status === "success") setSignals(sigR.signals);
      if (logR.status === "success") setTradeLog(logR.events);
    } catch {
      // ignore
    }
  }

  async function pollZones() {
    try {
      const [fastR, smcR] = await Promise.all([api.fastZones(), api.smcZones()]);
      if (fastR.status === "success") setFastZones(fastR.zones);
      if (smcR.status === "success") setSmcZones(smcR.zones);
    } catch {
      // keep stale zones visible
    }
  }

  async function loadFastDeskData() {
    try {
      const [config, status] = await Promise.all([api.getFastConfig(), api.deskStatus()]);
      setFastConfig(config.status === "success" ? config.config : null);
      setDeskStatus(status.status === "success" ? status : null);
    } catch (e) {
      console.error("Failed to fetch Fast Desk data", e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Desk accent */}
      <div class="desk-accent-teal" />

      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "320px minmax(0, 1fr) 260px",
          "grid-template-rows": "auto minmax(320px, 2fr) minmax(180px, 1fr)",
          gap: "6px",
          padding: "8px 10px",
          "overflow-y": "auto",
        }}
      >
        {/* ── Row 1: Header overview (full width) ── */}
        <div class="panel" style={{ "grid-column": "1 / 4", "grid-row": "1 / 2" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--teal)" }} />
              Fast Desk Status
            </div>
            <Show when={deskStatus()?.fast_desk?.enabled} fallback={<span class="cap-badge preview">Disabled</span>}>
              <span class="cap-badge live">Live</span>
            </Show>
          </div>
          <div class="panel-body">
            <Show when={!loading() && deskStatus()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading Fast Desk data…</div>}>
              <div style={{ display: "grid", "grid-template-columns": "repeat(4, 1fr)", gap: "6px" }}>
                {(
                  [
                    ["Status", deskStatus()?.fast_desk?.enabled ? "Active" : "Disabled", deskStatus()?.fast_desk?.enabled ? "var(--green)" : "var(--slate)"],
                    ["Workers", String(deskStatus()?.fast_desk?.workers ?? 0), "var(--cyan-live)"],
                    ["Open Positions", String(positions().length), "var(--text-primary)"],
                    ["Subscribed", String(snap()?.universes?.subscribed_universe?.length ?? 0), "var(--text-primary)"],
                  ] as [string, string, string][]
                ).map(([lbl, val, color]) => (
                  <div class="acct-field">
                    <label>{lbl}</label>
                    <div class="val" style={{ color }}>{val}</div>
                  </div>
                ))}
              </div>
            </Show>
          </div>
        </div>

        {/* ── Row 2, Col 1: Symbol Rail ── */}
        <div class="panel" style={{ "grid-column": "1 / 2", "grid-row": "2 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--teal)" }} />
              Symbol Rail
            </div>
            <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
              <span class="cap-badge live">{availableSymbols().length}</span>
              <span class="cap-badge derived">Pos {positions().length}</span>
            </div>
          </div>
          <Show when={fastConfig()}>
            <div
              style={{
                display: "flex",
                gap: "8px",
                padding: "5px 8px",
                "border-bottom": "1px solid var(--border-subtle)",
                "font-family": "var(--font-mono)",
                "font-size": "8px",
                color: "var(--text-muted)",
              }}
            >
              <span>Risk: {fastConfig()?.risk_per_trade_percent ?? "—"}%</span>
              <span>MaxPos: {fastConfig()?.max_positions_total ?? "—"}</span>
              <span>MinConf: {fastConfig()?.min_signal_confidence ?? "—"}</span>
            </div>
          </Show>
          <div style={{ flex: "1", "overflow-y": "auto", padding: "6px" }}>
            <Show when={availableSymbols().length > 0} fallback={
              <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>
                No symbols in universe.
              </div>
            }>
              <For each={availableSymbols()}>
                {(sym) => {
                  const isSelected = () => sym === selectedSymbol();
                  const posCount = () => positionCountBySymbol()[sym] ?? 0;
                  const lastSig = () => lastSignalBySymbol()[sym];
                  const summary = () => symbolSummary()[sym];
                  const hasPosition = () => posCount() > 0;
                  const accent = () => {
                    const sig = lastSig();
                    if (sig?.outcome === "accepted") return "var(--green)";
                    if (sig?.outcome === "rejected") return "var(--red)";
                    if (hasPosition()) return "var(--teal)";
                    return "var(--text-muted)";
                  };
                  const outcomeBadge = () => {
                    const sig = lastSig();
                    if (!sig) return { bg: "rgba(100,116,139,0.15)", fg: "var(--slate)", label: "NO SIGNAL" };
                    if (sig.outcome === "accepted") return { bg: "rgba(34,197,94,0.15)", fg: "var(--green)", label: "ACCEPT" };
                    if (sig.outcome === "rejected") return { bg: "rgba(239,68,68,0.15)", fg: "var(--red)", label: "REJECT" };
                    return { bg: "rgba(245,158,11,0.15)", fg: "var(--amber)", label: (sig.outcome || "PENDING").toUpperCase() };
                  };
                  return (
                    <div
                      role="button"
                      tabindex="0"
                      onClick={() => setSelectedSymbol(sym)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedSymbol(sym);
                        }
                      }}
                      style={{
                        border: isSelected() ? "1px solid var(--teal)" : "1px solid var(--border-subtle)",
                        background: isSelected() ? "rgba(20,185,166,0.10)" : "var(--bg-elevated)",
                        "border-radius": "4px",
                        padding: "7px",
                        "margin-bottom": "5px",
                        cursor: "pointer",
                        position: "relative",
                      }}
                    >
                      <div
                        style={{
                          position: "absolute",
                          left: "0",
                          top: "0",
                          bottom: "0",
                          width: "2px",
                          background: accent(),
                          opacity: "0.85",
                          "border-radius": "4px 0 0 4px",
                        }}
                      />
                      <div style={{ display: "flex", "justify-content": "space-between", "align-items": "center", "margin-bottom": "4px" }}>
                        <span style={{ "font-family": "var(--font-mono)", "font-size": "11px", "font-weight": "700" }}>{sym}</span>
                        <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
                          <Show when={hasPosition()}>
                            <span
                              style={{
                                "font-size": "8px",
                                "font-weight": "600",
                                padding: "1px 5px",
                                "border-radius": "3px",
                                background: "rgba(20,185,166,0.15)",
                                color: "var(--teal)",
                              }}
                            >
                              POS ×{posCount()}
                            </span>
                          </Show>
                          <span style={{ "font-size": "8px", "font-weight": "600", padding: "1px 5px", "border-radius": "3px", background: outcomeBadge().bg, color: outcomeBadge().fg }}>
                            {outcomeBadge().label}
                          </span>
                        </div>
                      </div>
                      <Show when={lastSig()}>
                        <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                          {(lastSig()!.side || "").toUpperCase()} | {lastSig()!.trigger || "-"} | conf: {(lastSig()!.confidence || 0).toFixed(2)}
                        </div>
                      </Show>
                      <Show when={!lastSig() && summary()}>
                        <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                          gate: {summary()!.last_gate || "-"} | {summary()!.last_passed ? "passed" : "blocked"}
                        </div>
                      </Show>
                      <Show when={hasPosition()}>
                        {(() => {
                          const symPositions = positions().filter((p) => String(p.symbol || "").toUpperCase() === sym);
                          const totalPnl = symPositions.reduce((acc, p) => acc + Number(p.profit ?? 0), 0);
                          return (
                            <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>
                              pnl: {totalPnl >= 0 ? "+" : ""}{numStr(totalPnl, 2)}
                            </div>
                          );
                        })()}
                      </Show>
                    </div>
                  );
                }}
              </For>
            </Show>
          </div>
        </div>

        {/* ── Row 2, Col 2: Structural Chart ── */}
        <div class="panel" style={{ "grid-column": "2 / 3", "grid-row": "2 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--teal)" }} />
              Structural Chart
            </div>
            <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
              <span class="cap-badge live">{selectedSymbol() || "No Symbol"}</span>
              <For each={chartTimeframes}>
                {(tf) => (
                  <button
                    type="button"
                    onClick={() => setSelectedTimeframe(tf)}
                    style={{
                      border: "1px solid var(--border-subtle)",
                      background: selectedTimeframe() === tf ? "rgba(20,185,166,0.14)" : "transparent",
                      color: selectedTimeframe() === tf ? "var(--teal)" : "var(--text-muted)",
                      "font-family": "var(--font-mono)",
                      "font-size": "8px",
                      padding: "2px 6px",
                      "border-radius": "3px",
                      cursor: "pointer",
                    }}
                  >
                    {tf}
                  </button>
                )}
              </For>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              "flex-wrap": "wrap",
              gap: "4px",
              padding: "4px 8px",
              "border-bottom": "1px solid var(--border-subtle)",
            }}
          >
            <For each={chartLegendItems()}>
              {(item) => (
                <span
                  style={{
                    display: "inline-flex",
                    "align-items": "center",
                    gap: "4px",
                    "font-family": "var(--font-mono)",
                    "font-size": "7px",
                    color: "var(--text-muted)",
                    border: "1px solid var(--border-subtle)",
                    padding: "1px 4px",
                    "border-radius": "10px",
                    background: "rgba(20,22,26,0.65)",
                  }}
                >
                  <span
                    style={{
                      width: "7px",
                      height: "7px",
                      "border-radius": "50%",
                      background: item.color,
                      border: "1px solid rgba(255,255,255,0.15)",
                    }}
                  />
                  {item.label}
                </span>
              )}
            </For>
          </div>
          <div
            style={{
              display: "flex",
              "flex-wrap": "wrap",
              gap: "4px",
              padding: "4px 8px",
              "border-bottom": "1px solid var(--border-subtle)",
              "justify-content": "flex-start",
              "min-height": "24px",
            }}
          >
            <Show
              when={selectedFastGroups().length > 0 || selectedSmcGroups().length > 0}
              fallback={
                <span style={{ "font-family": "var(--font-mono)", "font-size": "7px", color: "var(--text-muted)" }}>
                  No zones loaded for this symbol/timeframe.
                </span>
              }
            >
              <div style={{ display: "flex", "flex-wrap": "wrap", gap: "8px", width: "100%" }}>
                <Show when={selectedFastGroups().length > 0}>
                  <div style={{ display: "flex", "flex-wrap": "wrap", gap: "4px", "align-items": "center" }}>
                    <span style={{ "font-family": "var(--font-mono)", "font-size": "7px", color: "var(--teal)", "font-weight": "700" }}>FAST &gt;</span>
                    <For each={selectedFastGroups()}>
                      {(item) => (
                        <button
                          type="button"
                          onClick={() => toggleZoneVisibility(item.key)}
                          style={{
                            display: "inline-flex",
                            "align-items": "center",
                            gap: "4px",
                            "font-family": "var(--font-mono)",
                            "font-size": "7px",
                            color: item.enabled ? "var(--text-primary)" : "var(--text-muted)",
                            border: "1px solid var(--border-subtle)",
                            padding: "1px 4px",
                            "border-radius": "10px",
                            background: item.enabled ? "rgba(20,185,166,0.12)" : "rgba(20,22,26,0.65)",
                            cursor: "pointer",
                          }}
                        >
                          <span style={{ width: "7px", height: "7px", "border-radius": "50%", background: item.color, border: "1px solid rgba(255,255,255,0.15)", opacity: item.enabled ? "1" : "0.45" }} />
                          {item.timeframe} {item.label} x{item.count}
                        </button>
                      )}
                    </For>
                  </div>
                </Show>
                <Show when={selectedSmcGroups().length > 0}>
                  <div style={{ display: "flex", "flex-wrap": "wrap", gap: "4px", "align-items": "center" }}>
                    <span style={{ "font-family": "var(--font-mono)", "font-size": "7px", color: "var(--blue)", "font-weight": "700" }}>SMC &gt;</span>
                    <For each={selectedSmcGroups()}>
                      {(item) => (
                        <button
                          type="button"
                          onClick={() => toggleZoneVisibility(item.key)}
                          style={{
                            display: "inline-flex",
                            "align-items": "center",
                            gap: "4px",
                            "font-family": "var(--font-mono)",
                            "font-size": "7px",
                            color: item.enabled ? "var(--text-primary)" : "var(--text-muted)",
                            border: "1px solid var(--border-subtle)",
                            padding: "1px 4px",
                            "border-radius": "10px",
                            background: item.enabled ? "rgba(59,130,246,0.12)" : "rgba(20,22,26,0.65)",
                            cursor: "pointer",
                          }}
                        >
                          <span style={{ width: "7px", height: "7px", "border-radius": "50%", background: item.color, border: "1px solid rgba(255,255,255,0.15)", opacity: item.enabled ? "1" : "0.45" }} />
                          {item.timeframe} {item.label} x{item.count}
                        </button>
                      )}
                    </For>
                  </div>
                </Show>
              </div>
            </Show>
          </div>
          <div style={{ flex: "1", padding: "8px", display: "flex", "flex-direction": "column", gap: "6px" }}>
            <div style={{ display: "flex", "justify-content": "space-between", "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
              <span>
                Symbol: {selectedSymbol() || "-"} | Positions: {selectedPositions().length}
              </span>
              <span>
                Bars: {chartEntry()?.data?.chart_context?.candle_count ?? chartEntry()?.data?.candles?.length ?? 0} | TF: {selectedTimeframe()}
              </span>
              <span>
                Bid: {numStr(liveTick().bid, chartPrecision())} | Ask: {numStr(liveTick().ask, chartPrecision())} | Spr: {numStr(liveTick().spread, chartPrecision())}
              </span>
            </div>
            <div style={{ position: "relative", flex: "1", "min-height": "250px" }}>
              <div
                ref={(el) => {
                  chartHost = el;
                  setupChart();
                }}
                style={{
                  width: "100%",
                  height: "100%",
                  background: "var(--bg-base)",
                  border: "1px solid var(--border-subtle)",
                  "border-radius": "4px",
                }}
              />
              <button
                type="button"
                onClick={resetChartView}
                style={{
                  position: "absolute",
                  left: "50%",
                  bottom: "12px",
                  transform: "translateX(-50%)",
                  width: "26px",
                  height: "26px",
                  border: "1px solid var(--border-subtle)",
                  "border-radius": "999px",
                  background: "rgba(20,22,26,0.92)",
                  color: "var(--text-secondary)",
                  "font-family": "var(--font-mono)",
                  "font-size": "14px",
                  "line-height": "1",
                  display: "flex",
                  "align-items": "center",
                  "justify-content": "center",
                  cursor: "pointer",
                  "z-index": "3",
                }}
                title="Reset chart view"
                aria-label="Reset chart view"
              >
                ↺
              </button>
              <Show when={chartEntry()?.loading}>
                <div
                  style={{
                    position: "absolute",
                    inset: "0",
                    display: "flex",
                    "align-items": "center",
                    "justify-content": "center",
                    "font-family": "var(--font-mono)",
                    "font-size": "9px",
                    color: "var(--text-muted)",
                    background: "rgba(14,16,20,0.3)",
                    "pointer-events": "none",
                  }}
                >
                  Loading chart...
                </div>
              </Show>
              <Show when={chartEntry()?.error}>
                <div
                  style={{
                    position: "absolute",
                    left: "8px",
                    bottom: "8px",
                    "font-family": "var(--font-mono)",
                    "font-size": "8px",
                    color: "var(--red)",
                    background: "rgba(14,16,20,0.8)",
                    padding: "3px 6px",
                    border: "1px solid rgba(239,68,68,0.2)",
                    "border-radius": "3px",
                  }}
                >
                  {String(chartEntry()?.error)}
                </div>
              </Show>
              <Show when={!chartEntry()?.loading && !chartEntry()?.error && (chartEntry()?.data?.candles?.length ?? 0) === 0}>
                <div
                  style={{
                    position: "absolute",
                    inset: "0",
                    display: "flex",
                    "align-items": "center",
                    "justify-content": "center",
                    "font-family": "var(--font-mono)",
                    "font-size": "9px",
                    color: "var(--text-muted)",
                  }}
                >
                  No chart candles available.
                </div>
              </Show>
            </div>
          </div>
        </div>

        {/* ── Row 2-3, Col 3: Signals + Trade Log (stacked) ── */}
        <div style={{ "grid-column": "3 / 4", "grid-row": "2 / 4", display: "flex", "flex-direction": "column", gap: "6px" }}>
          {/* Signals & Execution */}
          <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--green)" }} />
                Signals
              </div>
              <Show when={signals().length > 0} fallback={<span class="cap-badge preview">0</span>}>
                <span class="cap-badge live">{signals().length}</span>
              </Show>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
              <Show when={signals().length > 0} fallback={
                <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>No signals yet</div>
              }>
                <table style={{ width: "100%", "font-size": "8.5px", "border-collapse": "collapse" }}>
                  <thead>
                    <tr>
                      {["Time", "Sym", "Side", "Outcome"].map((h) => (
                        <th style={{ padding: "4px 6px", "text-align": "left", "border-bottom": "1px solid var(--border-subtle)", "font-weight": "600", color: "var(--text-muted)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <For each={signals().slice(0, 25)}>
                      {(sig) => (
                        <tr style={{ "border-bottom": "1px solid var(--border-subtle)" }}>
                          <td style={{ padding: "3px 6px", "font-size": "7.5px", "white-space": "nowrap" }}>{(sig.generated_at || "").slice(11, 19)}</td>
                          <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)", "font-weight": "600" }}>{sig.symbol}</td>
                          <td style={{ padding: "3px 6px", color: sig.side === "buy" ? "var(--green)" : "var(--red)" }}>{(sig.side || "").toUpperCase()}</td>
                          <td style={{ padding: "3px 6px" }}>
                            <span
                              style={{
                                "font-size": "7.5px",
                                "font-weight": "600",
                                padding: "1px 4px",
                                "border-radius": "3px",
                                background: sig.outcome === "accepted" ? "rgba(34,197,94,0.15)" : sig.outcome === "rejected" ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)",
                                color: sig.outcome === "accepted" ? "var(--green)" : sig.outcome === "rejected" ? "var(--red)" : "var(--amber)",
                              }}
                            >
                              {(sig.outcome || "?").toUpperCase()}
                            </span>
                          </td>
                        </tr>
                      )}
                    </For>
                  </tbody>
                </table>
              </Show>
            </div>
          </div>

          {/* Trade Actions Log */}
          <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column", "max-height": "220px" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
                Trade Log
              </div>
              <Show when={tradeLog().length > 0} fallback={<span class="cap-badge preview">0</span>}>
                <span class="cap-badge live">{tradeLog().length}</span>
              </Show>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
              <Show when={tradeLog().length > 0} fallback={
                <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>No trade actions yet</div>
              }>
                <table style={{ width: "100%", "font-size": "8.5px", "border-collapse": "collapse" }}>
                  <thead>
                    <tr>
                      {["Time", "Sym", "Action", "Details"].map((h) => (
                        <th style={{ padding: "4px 6px", "text-align": "left", "border-bottom": "1px solid var(--border-subtle)", "font-weight": "600", color: "var(--text-muted)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <For each={tradeLog().slice(0, 20)}>
                      {(evt) => (
                        <tr style={{ "border-bottom": "1px solid var(--border-subtle)" }}>
                          <td style={{ padding: "3px 6px", "font-size": "7.5px", "white-space": "nowrap" }}>{(evt.logged_at || "").slice(11, 19)}</td>
                          <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)", "font-weight": "600" }}>{evt.symbol}</td>
                          <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)" }}>{evt.action}</td>
                          <td style={{ padding: "3px 6px", "font-size": "7.5px", color: "var(--text-muted)", "max-width": "120px", overflow: "hidden", "text-overflow": "ellipsis", "white-space": "nowrap" }}>
                            {evt.details_json ? `${(evt.details_json as any)?.setup || ""} ${(evt.details_json as any)?.entry_type || ""}`.trim() || JSON.stringify(evt.details_json).slice(0, 40) : "—"}
                          </td>
                        </tr>
                      )}
                    </For>
                  </tbody>
                </table>
              </Show>
            </div>
          </div>
        </div>

        {/* ── Row 3, Col 1-2: Pipeline Activity ── */}
        <div class="panel" style={{ "grid-column": "1 / 3", "grid-row": "3 / 4", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--amber)" }} />
              Pipeline Activity
            </div>
            <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
              <span class="cap-badge live">Live</span>
              <Show when={activityEvents().length > 0} fallback={<span class="cap-badge preview">0</span>}>
                <span class="cap-badge derived">{activityEvents().length}</span>
              </Show>
            </div>
          </div>
          <Show when={Object.keys(symbolSummary()).length > 0}>
            <div style={{ display: "flex", "flex-wrap": "wrap", gap: "4px", padding: "6px 8px 2px" }}>
              <For each={Object.entries(symbolSummary())}>
                {([sym, s]) => {
                  const topGate = () => {
                    const gates = Object.entries(s.block_by_gate);
                    if (!gates.length) return "";
                    gates.sort((a, b) => b[1] - a[1]);
                    return `${gates[0][0]}×${gates[0][1]}`;
                  };
                  return (
                    <span
                      style={{
                        "font-family": "var(--font-mono)",
                        "font-size": "8px",
                        padding: "2px 6px",
                        "border-radius": "3px",
                        background: s.last_passed ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                        color: s.last_passed ? "var(--green)" : "var(--red)",
                      }}
                    >
                      {sym}: {topGate() || "passed"}
                    </span>
                  );
                }}
              </For>
            </div>
          </Show>
          <div style={{ flex: "1", "overflow-y": "auto" }}>
            <table style={{ width: "100%", "font-size": "8.5px", "border-collapse": "collapse" }}>
              <thead>
                <tr>
                  {["Time", "Symbol", "Gate", "Status", "Details"].map((h) => (
                    <th style={{ padding: "4px 6px", "text-align": "left", "border-bottom": "1px solid var(--border-subtle)", "font-weight": "600", color: "var(--text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <Show when={activityEvents().length > 0} fallback={<tr><td colspan="5" style={{ "text-align": "center", color: "var(--text-muted)", padding: "14px" }}>No activity events yet</td></tr>}>
                  <For each={activityEvents().slice(0, 30)}>
                    {(evt) => (
                      <tr style={{ "border-bottom": "1px solid var(--border-subtle)" }}>
                        <td style={{ padding: "3px 6px", "font-size": "7.5px", "white-space": "nowrap" }}>{evt.timestamp.replace("T", " ").replace("Z", "")}</td>
                        <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)", "font-weight": "600" }}>{evt.symbol}</td>
                        <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)" }}>{evt.gate_reached}</td>
                        <td style={{ padding: "3px 6px" }}>
                          <span
                            style={{
                              "font-size": "7.5px",
                              "font-weight": "600",
                              padding: "1px 4px",
                              "border-radius": "3px",
                              background: evt.gate_passed ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                              color: evt.gate_passed ? "var(--green)" : "var(--red)",
                            }}
                          >
                            {evt.gate_passed ? "PASS" : "BLOCKED"}
                          </span>
                        </td>
                        <td style={{ padding: "3px 6px", "font-size": "7.5px", color: "var(--text-muted)", "max-width": "260px", overflow: "hidden", "text-overflow": "ellipsis", "white-space": "nowrap" }}>
                          {(() => {
                            const d = evt.details;
                            if (d.reasons) return (d.reasons as string[]).join(", ");
                            if (d.message) return String(d.message);
                            if (d.remaining_s != null) return `cooldown ${d.remaining_s}s`;
                            if (d.outcome) return `${d.side} ${d.setup} → ${d.outcome}`;
                            if (d.drawdown_pct != null) return `dd=${d.drawdown_pct}%`;
                            if (d.setups_seen != null) return `setups=${d.setups_seen} h1=${d.h1_bias}`;
                            if (d.reason) return String(d.reason);
                            if (d.decision) return `risk: allowed=${(d.decision as any)?.allowed}`;
                            return JSON.stringify(d).slice(0, 80);
                          })()}
                        </td>
                      </tr>
                    )}
                  </For>
                </Show>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Fast Desk</span>
        <span>Source: /positions · /api/v1/fast/signals · /api/v1/fast/zones · /chart/{'{'}symbol{'}'}/{'{'}timeframe{'}'}</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default FastDesk;
