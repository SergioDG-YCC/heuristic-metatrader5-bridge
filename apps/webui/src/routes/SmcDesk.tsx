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
import { fetchChart, getChartEntry } from "../stores/chartsStore";
import { api } from "../api/client";
import type { SmcThesis, SmcZone, SmcEventRow, Candle } from "../types/api";

function zoneColor(zt: string): string {
  if (zt.includes("bullish")) return "var(--green)";
  if (zt.includes("bearish")) return "var(--red)";
  if (zt.includes("fvg")) return "var(--amber)";
  if (zt.includes("liquidity") || zt.includes("equal")) return "var(--cyan-live)";
  return "var(--text-muted)";
}

function zoneLineColor(zoneType: string): string {
  const zt = (zoneType || "").toLowerCase();
  if (zt.includes("bullish")) return "#22c55e77";
  if (zt.includes("bearish")) return "#ef44446e";
  if (zt.includes("fvg")) return "#f5a5235e";
  if (zt.includes("liquidity") || zt.includes("equal")) return "#22d3ee5e";
  return "#64748b";
}

function biasColor(b: string): string {
  if (b === "bullish") return "var(--green)";
  if (b === "bearish") return "var(--red)";
  return "var(--text-muted)";
}

function validatorBadge(v: string | null | undefined): { bg: string; fg: string; label: string } {
  if (v === "accept") return { bg: "rgba(34,197,94,0.15)", fg: "var(--green)", label: "ACCEPT" };
  if (v === "reject") return { bg: "rgba(239,68,68,0.15)", fg: "var(--red)", label: "REJECT" };
  return { bg: "rgba(100,116,139,0.15)", fg: "var(--slate)", label: v ? v.toUpperCase() : "PENDING" };
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

function parseRangeText(value: unknown): [number | null, number | null] {
  if (typeof value !== "string") return [null, null];
  const matches = value.match(/-?\d+(?:\.\d+)?/g);
  if (!matches || matches.length === 0) return [null, null];
  const nums = matches.map((m) => Number(m)).filter((n) => Number.isFinite(n));
  if (nums.length === 0) return [null, null];
  if (nums.length === 1) return [nums[0], nums[0]];
  const sorted = [...nums].sort((a, b) => a - b);
  return [sorted[0], sorted[sorted.length - 1]];
}

type CandidateLike = Record<string, unknown>;

function pickNumber(candidate: CandidateLike, keys: string[]): number | null {
  for (const key of keys) {
    const n = toNumber(candidate[key]);
    if (n != null) return n;
  }
  return null;
}

function candidateLevels(candidate: CandidateLike | null): {
  entryLow: number | null;
  entryHigh: number | null;
  stopLoss: number | null;
  takeProfit1: number | null;
  takeProfit2: number | null;
} {
  if (!candidate) {
    return {
      entryLow: null,
      entryHigh: null,
      stopLoss: null,
      takeProfit1: null,
      takeProfit2: null,
    };
  }

  const [rangeLow, rangeHigh] = parseRangeText(candidate.entry_zone);
  const entryLow = pickNumber(candidate, ["entry_zone_low", "entry_low"]) ?? rangeLow;
  const entryHigh = pickNumber(candidate, ["entry_zone_high", "entry_high"]) ?? rangeHigh;
  const singleEntry = pickNumber(candidate, ["entry", "entry_price"]);

  return {
    entryLow: entryLow ?? singleEntry,
    entryHigh: entryHigh ?? singleEntry,
    stopLoss: pickNumber(candidate, ["stop_loss", "sl"]),
    takeProfit1: pickNumber(candidate, ["take_profit_1", "take_profit", "tp1", "tp"]),
    takeProfit2: pickNumber(candidate, ["take_profit_2", "tp2"]),
  };
}

function thesisIdentity(t: SmcThesis): string {
  return String(t.thesis_id || `${t.symbol}:${String((t as any).strategy_type || "smc_prepared")}:${t.created_at || ""}`);
}

function isAccepted(t: SmcThesis): boolean {
  return String(t.validator_decision || "").toLowerCase() === "accept";
}

function formatPrice(value: unknown, digits = 5): string {
  const n = toNumber(value);
  return n == null ? "-" : n.toFixed(digits);
}

const chartTimeframes = ["H1", "H4", "D1"] as const;
type ChartTf = (typeof chartTimeframes)[number];

type TickStreamPayload = {
  status?: string;
  symbol?: string;
  timeframe?: string;
  bid?: number | string;
  ask?: number | string;
  spread?: number | string;
  last_bar_time?: string;
  bar?: Candle | null;
  feed_status?: string;
  updated_at?: string;
  error?: string;
};

type PriceLinePresetKey =
  | "entryLow"
  | "entryHigh"
  | "stopLoss"
  | "takeProfit1"
  | "takeProfit2"
  | "zoneLow"
  | "zoneHigh"
  | "bid"
  | "ask";

const PRICE_LINE_PRESETS: Record<
  PriceLinePresetKey,
  { color: string; lineWidth: LineWidth; lineStyle: LineStyle }
> = {
  entryLow: { color: "rgba(34, 211, 238, 0.4)", lineWidth: 4, lineStyle: LineStyle.Solid },
  entryHigh: { color: "rgba(34, 211, 238, 0.4)", lineWidth: 4, lineStyle: LineStyle.Solid },
  stopLoss: { color: "rgba(239, 68, 68, 0.65)", lineWidth: 2, lineStyle: LineStyle.Solid },
  takeProfit1: { color: "rgba(34, 197, 94, 0.27)", lineWidth: 3, lineStyle: LineStyle.Solid },
  takeProfit2: { color: "rgba(34, 197, 94, 0.27)", lineWidth: 3, lineStyle: LineStyle.Solid },
  zoneLow: { color: "rgba(100, 116, 139, 0.42)", lineWidth: 2, lineStyle: LineStyle.Solid },
  zoneHigh: { color: "rgba(100, 116, 139, 0.42)", lineWidth: 2, lineStyle: LineStyle.Solid },
  bid: { color: "rgba(245, 158, 11, 0.7)", lineWidth: 1, lineStyle: LineStyle.Solid },
  ask: { color: "rgba(34, 211, 238, 0.7)", lineWidth: 1, lineStyle: LineStyle.Solid },
};

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

const SmcDesk: Component = () => {
  const [smcConfig, setSmcConfig] = createSignal<any>(null);
  const [deskStatus, setDeskStatus] = createSignal<any>(null);
  const [loading, setLoading] = createSignal(true);
  const [theses, setTheses] = createSignal<SmcThesis[]>([]);
  const [zones, setZones] = createSignal<SmcZone[]>([]);
  const [smcEvents, setSmcEvents] = createSignal<SmcEventRow[]>([]);
  const [onlyAccepted, setOnlyAccepted] = createSignal(false);
  const [selectedThesisId, setSelectedThesisId] = createSignal("");
  const [selectedTimeframe, setSelectedTimeframe] = createSignal<ChartTf>("H1");
  const [chartPrecision, setChartPrecision] = createSignal(5);
  const [liveTick, setLiveTick] = createSignal<{ bid: number | null; ask: number | null; spread: number | null; updatedAt: string | null }>({
    bid: null,
    ask: null,
    spread: null,
    updatedAt: null,
  });
  const [liveBar, setLiveBar] = createSignal<CandlestickData | null>(null);

  const visibleTheses = createMemo(() => (onlyAccepted() ? theses().filter(isAccepted) : theses()));
  const acceptedCount = createMemo(() => theses().filter(isAccepted).length);
  const selectedThesis = createMemo<SmcThesis | null>(() => {
    const list = visibleTheses();
    if (list.length === 0) return null;
    const picked = list.find((t) => thesisIdentity(t) === selectedThesisId());
    return picked ?? list[0];
  });
  const selectedSymbol = createMemo(() => selectedThesis()?.symbol || "");
  const selectedSymbolZones = createMemo(() => zones().filter((z) => z.symbol === selectedSymbol()));
  const selectedPrimaryCandidate = createMemo<CandidateLike | null>(() => {
    const list = (selectedThesis()?.operation_candidates || []) as CandidateLike[];
    return list.length > 0 ? list[0] : null;
  });

  const chartEntry = createMemo(() => {
    const symbol = selectedSymbol();
    if (!symbol) return undefined;
    return getChartEntry(symbol, selectedTimeframe());
  });

  const allCandidates = () => {
    const out: CandidateLike[] = [];
    for (const t of theses()) {
      for (const c of (t.operation_candidates || []) as CandidateLike[]) {
        out.push({ ...c, _symbol: t.symbol });
      }
    }
    return out;
  };

  const thesisCountBySymbol = createMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of theses()) {
      const symbol = String(t.symbol || "");
      counts[symbol] = (counts[symbol] ?? 0) + 1;
    }
    return counts;
  });

  const chartLegendItems = createMemo(() => [
    { label: "Entry", color: PRICE_LINE_PRESETS.entryLow.color },
    { label: "SL", color: PRICE_LINE_PRESETS.stopLoss.color },
    { label: "TP", color: PRICE_LINE_PRESETS.takeProfit1.color },
    { label: "Bid", color: PRICE_LINE_PRESETS.bid.color },
    { label: "Ask", color: PRICE_LINE_PRESETS.ask.color },
    { label: "Zone Bull", color: zoneLineColor("bullish") },
    { label: "Zone Bear", color: zoneLineColor("bearish") },
    { label: "Zone FVG", color: zoneLineColor("fvg") },
    { label: "Zone Liq", color: zoneLineColor("liquidity") },
  ]);

  let dataTimer: ReturnType<typeof setInterval> | undefined;
  let chartHost: HTMLDivElement | undefined;
  let chartApi: IChartApi | undefined;
  let candleSeries: ReturnType<IChartApi["addSeries"]> | undefined;
  let strategyLines: IPriceLine[] = [];
  let livePriceLines: IPriceLine[] = [];
  let resizeObserver: ResizeObserver | undefined;
  let tickSource: EventSource | undefined;

  function clearStrategyLines() {
    if (!candleSeries) return;
    for (const line of strategyLines) {
      candleSeries.removePriceLine(line);
    }
    strategyLines = [];
  }

  function createPriceLine(
    price: number,
    title: string,
    presetKey: PriceLinePresetKey,
    colorOverride?: string,
  ): IPriceLine | null {
    if (!candleSeries) return null;
    const preset = PRICE_LINE_PRESETS[presetKey];
    const color = colorOverride || preset.color;
    const hideLabel = presetKey === "zoneLow" || presetKey === "zoneHigh";
    const line = candleSeries.createPriceLine({
      price,
      color,
      lineWidth: preset.lineWidth,
      lineStyle: preset.lineStyle,
      axisLabelVisible: !hideLabel,
      lineVisible: true,
      title: hideLabel ? "" : title,
    });
    return line;
  }

  function addStrategyLine(
    price: number,
    title: string,
    presetKey: Exclude<PriceLinePresetKey, "bid" | "ask">,
    colorOverride?: string,
  ) {
    const line = createPriceLine(price, title, presetKey, colorOverride);
    if (!line) return;
    strategyLines.push(line);
  }

  function clearLivePriceLines() {
    if (!candleSeries) return;
    for (const line of livePriceLines) {
      candleSeries.removePriceLine(line);
    }
    livePriceLines = [];
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
        vertLine: { color: "rgba(34,211,238,0.25)", width: 1 },
        horzLine: { color: "rgba(34,211,238,0.25)", width: 1 },
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

      const bid = toNumber(payload.bid);
      const ask = toNumber(payload.ask);
      const spread = toNumber(payload.spread);
      setLiveTick({
        bid,
        ask,
        spread,
        updatedAt: payload.updated_at || null,
      });

      const bar = payload.bar ? candleToSeries(payload.bar) : null;
      if (!bar) return;
      setLiveBar(bar);
      if (!candleSeries) return;
      candleSeries.update(bar);
    };

    source.onerror = () => {
      // EventSource reconnects automatically.
    };
  }

  onMount(() => {
    initOperationsStore();
    loadSmcDeskData();
    pollSmcData();
    dataTimer = setInterval(pollSmcData, 10_000);
    setupChart();
  });

  onCleanup(() => {
    if (dataTimer) clearInterval(dataTimer);
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
    const list = visibleTheses();
    const current = selectedThesisId();
    if (list.length === 0) {
      if (current) setSelectedThesisId("");
      return;
    }
    if (!current || !list.some((t) => thesisIdentity(t) === current)) {
      setSelectedThesisId(thesisIdentity(list[0]));
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

    const levels = candidateLevels(selectedPrimaryCandidate());
    if (levels.entryLow != null) addStrategyLine(levels.entryLow, "Entry L", "entryLow");
    if (levels.entryHigh != null && levels.entryHigh !== levels.entryLow) addStrategyLine(levels.entryHigh, "Entry H", "entryHigh");
    if (levels.stopLoss != null) addStrategyLine(levels.stopLoss, "SL", "stopLoss");
    if (levels.takeProfit1 != null) addStrategyLine(levels.takeProfit1, "TP1", "takeProfit1");
    if (levels.takeProfit2 != null) addStrategyLine(levels.takeProfit2, "TP2", "takeProfit2");

    for (const z of selectedSymbolZones().slice(0, 4)) {
      const low = toNumber(z.price_low);
      const high = toNumber(z.price_high);
      const color = zoneLineColor(String(z.zone_type || ""));
      const label = String(z.zone_type || "zone").toUpperCase().slice(0, 10);
      if (low != null) addStrategyLine(low, `${label} L`, "zoneLow", color);
      if (high != null && high !== low) addStrategyLine(high, `${label} H`, "zoneHigh", color);
    }

    if (candles.length > 0) {
      chartApi.timeScale().fitContent();
    }
  });

  createEffect(() => {
    if (!candleSeries) return;
    updateLivePriceLines();
  });

  async function pollSmcData() {
    try {
      const [tR, zR, eR] = await Promise.all([api.smcTheses(), api.smcZones(), api.smcEvents(60)]);
      if (tR.status === "success") setTheses(tR.theses);
      if (zR.status === "success") setZones(zR.zones);
      if (eR.status === "success") setSmcEvents(eR.events);
    } catch {
      // Keep stale data visible when polling fails.
    }
  }
  
  async function loadSmcDeskData() {
    try {
      const [config, status] = await Promise.all([
        api.getSmcConfig(),
        api.deskStatus(),
      ]);
      setSmcConfig(config.status === "success" ? config.config : null);
      setDeskStatus(status.status === "success" ? status : null);
    } catch (e) {
      console.error("Failed to fetch SMC Desk data", e);
    } finally {
      setLoading(false);
    }
  }

  const snap = () => runtimeStore.snapshot;
  const positions = () => operationsStore.positions;

  return (
    <>
      {/* Desk accent */}
      <div class="desk-accent-blue" />

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
        {/* Header overview */}
        <div class="panel" style={{ "grid-column": "1 / 4", "grid-row": "1 / 2" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
              SMC Desk Status
            </div>
            <Show when={deskStatus()?.smc_desk?.enabled} fallback={<span class="cap-badge preview">Disabled</span>}>
              <span class="cap-badge live">Live</span>
            </Show>
          </div>
          <div class="panel-body">
            <Show when={!loading() && deskStatus()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading SMC desk data...</div>}>
              <div style={{ display: "grid", "grid-template-columns": "repeat(4, 1fr)", gap: "6px" }}>
                {(
                  [
                    ["Status", deskStatus()?.smc_desk?.enabled ? "Active" : "Disabled", deskStatus()?.smc_desk?.enabled ? "var(--green)" : "var(--slate)"],
                    ["Scanner", deskStatus()?.smc_desk?.scanner_active ? "Running" : "Stopped", deskStatus()?.smc_desk?.scanner_active ? "var(--green)" : "var(--slate)"],
                    ["Open Positions", String(positions().length), "var(--text-primary)"],
                    ["Subscribed Symbols", String(snap()?.universes?.subscribed_universe?.length ?? 0), "var(--text-primary)"],
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

        {/* Thesis Rail */}
        <div class="panel" style={{ "grid-column": "1 / 2", "grid-row": "2 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
              Thesis Rail
            </div>
            <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
              <span class="cap-badge live">{visibleTheses().length}</span>
              <span class="cap-badge derived">Accept {acceptedCount()}</span>
              <button
                type="button"
                onClick={() => setOnlyAccepted((v) => !v)}
                style={{
                  border: "1px solid var(--border-subtle)",
                  background: onlyAccepted() ? "var(--blue-dim)" : "transparent",
                  color: onlyAccepted() ? "var(--blue)" : "var(--text-muted)",
                  "font-family": "var(--font-mono)",
                  "font-size": "8px",
                  padding: "2px 6px",
                  "border-radius": "3px",
                  cursor: "pointer",
                }}
              >
                {onlyAccepted() ? "ACCEPT only" : "All active"}
              </button>
            </div>
          </div>
          <Show when={smcConfig()}>
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
              <span>MaxC: {String(smcConfig()?.max_candidates ?? "-")}</span>
              <span>MinRR: {String(smcConfig()?.min_rr ?? "-")}</span>
              <span>LLM: {smcConfig()?.llm_enabled ? "ON" : "OFF"}</span>
            </div>
          </Show>
          <div style={{ flex: "1", "overflow-y": "auto", padding: "6px" }}>
            <Show when={visibleTheses().length > 0} fallback={
              <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>
                No theses for current filter.
              </div>
            }>
              <For each={visibleTheses()}>
                {(t) => {
                  const vb = validatorBadge(t.validator_decision);
                  const key = thesisIdentity(t);
                  const isSelected = () => key === selectedThesisId();
                  const symbolCount = thesisCountBySymbol()[String(t.symbol || "")] ?? 1;
                  const candidateCount = (t.operation_candidates || []).length;
                  const color = biasColor(t.bias);
                  return (
                    <div
                      role="button"
                      tabindex="0"
                      onClick={() => setSelectedThesisId(key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedThesisId(key);
                        }
                      }}
                      style={{
                        border: isSelected() ? "1px solid var(--blue)" : "1px solid var(--border-subtle)",
                        background: isSelected() ? "var(--blue-dim)" : "var(--bg-elevated)",
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
                          background: color,
                          opacity: "0.85",
                          "border-radius": "4px 0 0 4px",
                        }}
                      />
                      <div style={{ display: "flex", "justify-content": "space-between", "align-items": "center", "margin-bottom": "4px" }}>
                        <span style={{ "font-family": "var(--font-mono)", "font-size": "11px", "font-weight": "700" }}>{t.symbol}</span>
                        <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
                          <span
                            style={{
                              "font-size": "8px",
                              "font-weight": "600",
                              padding: "1px 5px",
                              "border-radius": "3px",
                              background:
                                color === "var(--green)"
                                  ? "rgba(34,197,94,0.15)"
                                  : color === "var(--red)"
                                  ? "rgba(239,68,68,0.15)"
                                  : "rgba(100,116,139,0.15)",
                              color,
                            }}
                          >
                            {(t.bias || "unclear").toUpperCase()}
                          </span>
                          <span style={{ "font-size": "8px", "font-weight": "600", padding: "1px 5px", "border-radius": "3px", background: vb.bg, color: vb.fg }}>
                            {vb.label}
                          </span>
                        </div>
                      </div>
                      <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                        status: {t.status || "-"} | strategy: {String((t as any).strategy_type || "smc_prepared")}
                      </div>
                      <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                        theses/symbol: {symbolCount} | candidates: {candidateCount}
                      </div>
                      <Show when={t.base_scenario}>
                        <div style={{ "font-size": "8px", color: "var(--text-secondary)", "line-height": "1.35", "margin-top": "4px" }}>
                          {String(t.base_scenario).slice(0, 130)}
                        </div>
                      </Show>
                    </div>
                  );
                }}
              </For>
            </Show>
          </div>
        </div>

        <div class="panel" style={{ "grid-column": "2 / 3", "grid-row": "2 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
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
                      background: selectedTimeframe() === tf ? "var(--blue-dim)" : "transparent",
                      color: selectedTimeframe() === tf ? "var(--blue)" : "var(--text-muted)",
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
          <div style={{ flex: "1", padding: "8px", display: "flex", "flex-direction": "column", gap: "6px" }}>
            <div style={{ display: "flex", "justify-content": "space-between", "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
              <span>
                Thesis: {selectedThesis()?.thesis_id ? String(selectedThesis()?.thesis_id).slice(0, 18) : "-"} | Bias: {(selectedThesis()?.bias || "-").toUpperCase()}
              </span>
              <span>
                Bars: {chartEntry()?.data?.chart_context?.candle_count ?? chartEntry()?.data?.candles?.length ?? 0} | TF: {selectedTimeframe()}
              </span>
              <span>
                Bid: {formatPrice(liveTick().bid, chartPrecision())} | Ask: {formatPrice(liveTick().ask, chartPrecision())} | Spr: {formatPrice(liveTick().spread, chartPrecision())}
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
                    "pointer-events": "none",
                  }}
                >
                  No candle data for this symbol/timeframe.
                </div>
              </Show>
            </div>
          </div>
        </div>

        {/* Zone Board */}
        <div class="panel" style={{ "grid-column": "1 / 3", "grid-row": "3 / 4", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
              Zone Board
            </div>
            <div style={{ display: "flex", gap: "4px", "align-items": "center" }}>
              <span class="cap-badge preview">Secondary</span>
              <Show when={zones().length > 0} fallback={<span class="cap-badge preview">No Zones</span>}>
                <span class="cap-badge live">Live {zones().length}</span>
              </Show>
            </div>
          </div>
          <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
            <Show when={zones().length > 0} fallback={
              <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>
                No zones currently tracked.
              </div>
            }>
              <table style={{ width: "100%", "font-size": "8.5px", "border-collapse": "collapse" }}>
                <thead>
                  <tr style={{ "text-align": "left", color: "var(--text-muted)", "border-bottom": "1px solid var(--border-subtle)" }}>
                    <th style={{ padding: "4px 6px" }}>Symbol</th>
                    <th style={{ padding: "4px 6px" }}>TF</th>
                    <th style={{ padding: "4px 6px" }}>Type</th>
                    <th style={{ padding: "4px 6px" }}>Price Range</th>
                    <th style={{ padding: "4px 6px" }}>Quality</th>
                    <th style={{ padding: "4px 6px" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={zones()}>
                    {(z) => (
                      <tr
                        style={{
                          "border-bottom": "1px solid var(--border-subtle)",
                          background: z.symbol === selectedSymbol() ? "rgba(91,141,239,0.08)" : "transparent",
                        }}
                      >
                        <td style={{ padding: "3px 6px", "font-weight": "600" }}>{z.symbol}</td>
                        <td style={{ padding: "3px 6px" }}>{z.timeframe || "-"}</td>
                        <td style={{ padding: "3px 6px", color: zoneColor(z.zone_type) }}>{z.zone_type || "-"}</td>
                        <td style={{ padding: "3px 6px", "font-family": "var(--font-mono)" }}>
                          {z.price_low != null && z.price_high != null ? `${Number(z.price_low).toFixed(5)} - ${Number(z.price_high).toFixed(5)}` : "-"}
                        </td>
                        <td style={{ padding: "3px 6px" }}>{z.quality_score ?? "-"}</td>
                        <td style={{ padding: "3px 6px" }}>
                          <span
                            style={{
                              "font-size": "7.5px",
                              padding: "1px 4px",
                              "border-radius": "3px",
                              background: z.status === "active" ? "rgba(34,197,94,0.15)" : "rgba(100,116,139,0.1)",
                              color: z.status === "active" ? "var(--green)" : "var(--text-muted)",
                            }}
                          >
                            {z.status || "unknown"}
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


        {/* Candidate Stack + Events Feed */}
        <div style={{ "grid-column": "3 / 4", "grid-row": "2 / 4", display: "flex", "flex-direction": "column", gap: "6px" }}>
          {/* Candidate Stack from theses */}
          <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--orange, #f59e0b)" }} />
                Candidate Stack
              </div>
              <Show when={allCandidates().length > 0} fallback={<span class="cap-badge preview">None</span>}>
                <span class="cap-badge live">{allCandidates().length}</span>
              </Show>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
              <Show when={allCandidates().length > 0} fallback={
                <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>
                  No operation candidates. Theses will generate candidates when confluences align.
                </div>
              }>
                <For each={allCandidates()}>
                  {(c) => (
                    <div style={{ "border-bottom": "1px solid var(--border-subtle)", padding: "6px 8px", display: "flex", "justify-content": "space-between", "align-items": "center" }}>
                      <div>
                        <span style={{ "font-weight": "700", "font-size": "10px", "margin-right": "6px" }}>{String(c._symbol ?? "-")}</span>
                        <span style={{
                          "font-size": "8px", "font-weight": "600", padding: "1px 4px", "border-radius": "3px",
                          background: String(c.side || "").toLowerCase() === "buy" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                          color: String(c.side || "").toLowerCase() === "buy" ? "var(--green)" : "var(--red)",
                        }}>
                          {String(c.side || "-").toUpperCase()}
                        </span>
                      </div>
                      <div style={{ "font-size": "8px", color: "var(--text-secondary)", "font-family": "var(--font-mono)", display: "flex", gap: "8px" }}>
                        <span>Entry: {String(c.entry_zone ?? "-")}</span>
                        <span>SL: {String(c.sl ?? "-")}</span>
                        <span>TP: {String(c.tp ?? "-")}</span>
                        <span style={{ "font-weight": "600" }}>RR: {toNumber(c.rr_ratio) != null ? Number(c.rr_ratio).toFixed(1) : "-"}</span>
                      </div>
                    </div>
                  )}
                </For>
              </Show>
            </div>
          </div>

          {/* SMC Events Feed */}
          <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column", "max-height": "220px" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--slate)" }} />
                Events Feed
              </div>
              <Show when={smcEvents().length > 0}>
                <span class="cap-badge live">Last {smcEvents().length}</span>
              </Show>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
              <Show when={smcEvents().length > 0} fallback={
                <div style={{ padding: "12px 8px", "font-size": "9px", color: "var(--text-muted)" }}>
                  No events recorded yet.
                </div>
              }>
                <For each={smcEvents()}>
                  {(ev) => (
                    <div style={{ "border-bottom": "1px solid var(--border-subtle)", padding: "4px 8px", display: "flex", "justify-content": "space-between", "font-size": "8px" }}>
                      <div style={{ display: "flex", gap: "6px", "align-items": "center" }}>
                        <span style={{ color: "var(--text-muted)", "font-family": "var(--font-mono)", "min-width": "50px" }}>
                          {(ev.created_at || "").slice(11, 19)}
                        </span>
                        <span style={{ "font-weight": "600" }}>{ev.symbol}</span>
                        <span style={{
                          padding: "1px 4px", "border-radius": "3px", "font-size": "7.5px",
                          background: (ev.event_type || "").includes("sweep") ? "rgba(239,68,68,0.15)"
                            : (ev.event_type || "").includes("approaching") ? "rgba(34,197,94,0.15)"
                            : "rgba(100,116,139,0.1)",
                          color: (ev.event_type || "").includes("sweep") ? "var(--red)"
                            : (ev.event_type || "").includes("approaching") ? "var(--green)"
                            : "var(--text-muted)",
                        }}>
                          {ev.event_type}
                        </span>
                      </div>
                      <span style={{ color: "var(--text-muted)", "max-width": "200px", overflow: "hidden", "text-overflow": "ellipsis", "white-space": "nowrap" }}>
                        {ev.payload_json ? JSON.stringify(ev.payload_json).slice(0, 80) : ""}
                      </span>
                    </div>
                  )}
                </For>
              </Show>
            </div>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · SMC Desk</span>
        <span>Source: /api/v1/smc/theses · /api/v1/smc/zones · /api/v1/smc/events · /chart/{'{'}symbol{'}'}/{'{'}timeframe{'}'}</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default SmcDesk;
