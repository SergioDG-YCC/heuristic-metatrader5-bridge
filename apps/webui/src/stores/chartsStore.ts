import { createStore } from "solid-js/store";
import type { ChartResponse } from "../types/api";
import { api } from "../api/client";

interface ChartsEntry {
  loading: boolean;
  error: string | null;
  data: ChartResponse | null;
  fetchedAt: string | null;
}

interface ChartsStore {
  cache: Record<string, ChartsEntry>;
}

const [state, setState] = createStore<ChartsStore>({ cache: {} });
const inflight = new Map<string, Promise<void>>();
const MIN_FETCH_GAP_MS = 1200;

export { state as chartsStore };

function cacheKey(symbol: string, timeframe: string): string {
  return `${symbol.toUpperCase()}:${timeframe.toUpperCase()}`;
}

export async function fetchChart(
  symbol: string,
  timeframe: string,
  bars = 200
): Promise<void> {
  const key = cacheKey(symbol, timeframe);
  const existing = inflight.get(key);
  if (existing) return existing;

  const lastFetched = state.cache[key]?.fetchedAt ? Date.parse(String(state.cache[key]?.fetchedAt)) : NaN;
  if (Number.isFinite(lastFetched) && Date.now() - lastFetched < MIN_FETCH_GAP_MS) {
    return;
  }

  // Mark loading
  setState("cache", key, {
    loading: true,
    error: null,
    data: state.cache[key]?.data ?? null,
    fetchedAt: state.cache[key]?.fetchedAt ?? null,
  });

  const run = (async () => {
    try {
      const data = await api.chart(symbol, timeframe, bars);
      setState("cache", key, {
        loading: false,
        error: null,
        data,
        fetchedAt: new Date().toISOString(),
      });
    } catch (e) {
      setState("cache", key, {
        loading: false,
        error: e instanceof Error ? e.message : "chart fetch failed",
        data: state.cache[key]?.data ?? null,
        fetchedAt: state.cache[key]?.fetchedAt ?? null,
      });
    } finally {
      inflight.delete(key);
    }
  })();

  inflight.set(key, run);
  return run;
}

export function getChartEntry(symbol: string, timeframe: string): ChartsEntry | undefined {
  return state.cache[cacheKey(symbol, timeframe)];
}
