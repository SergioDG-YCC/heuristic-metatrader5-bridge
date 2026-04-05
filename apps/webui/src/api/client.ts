import type {
  LiveStateSnapshot,
  AccountPayload,
  PositionRow,
  OrderRow,
  ExposureState,
  ChartResponse,
  SymbolSpec,
  CatalogResponse,
  OwnershipPayload,
  RiskStatusPayload,
  RiskLimitsPayload,
  RiskProfilePayload,
  FeedRow,
  FastActivityResponse,
  FastSignalRow,
  FastTradeLogRow,
  FastZoneRow,
  SmcThesis,
  SmcZone,
  SmcEventRow,
  PipelineSnapshotResponse,
  CorrelationMatrixResponse,
} from "../types/api";

const BACKEND = ""; // proxied through Vite dev server

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${path}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${path}`);
  }
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => get<LiveStateSnapshot>("/status"),
  account: () => get<AccountPayload>("/account"),
  positions: () =>
    get<{ positions: PositionRow[]; orders: OrderRow[] }>("/positions"),
  exposure: () => get<ExposureState>("/exposure"),
  catalog: () => get<CatalogResponse>("/catalog"),
  specs: () => get<Record<string, SymbolSpec>>("/specs"),
  spec: (symbol: string) => get<SymbolSpec>(`/specs/${symbol}`),
  chart: (symbol: string, timeframe: string, bars = 200) =>
    get<ChartResponse>(`/chart/${symbol}/${timeframe}?bars=${bars}`),
  subscribe: (symbol: string) =>
    post<{ symbol: string; changed: boolean; subscribed_universe: string[] }>(
      "/subscribe",
      { symbol }
    ),
  unsubscribe: (symbol: string) =>
    post<{ symbol: string; changed: boolean; subscribed_universe: string[] }>(
      "/unsubscribe",
      { symbol }
    ),
  // Ownership
  ownership: () => get<OwnershipPayload>("/ownership"),
  ownershipOpen: () => get<OwnershipPayload>("/ownership/open"),
  ownershipHistory: () => get<OwnershipPayload>("/ownership/history"),
  ownershipReassign: (req: { position_id?: number; order_id?: number; target_owner: string; reevaluation_required?: boolean; reason?: string }) =>
    post<unknown>("/ownership/reassign", req),
  // Risk
  riskStatus: () => get<RiskStatusPayload>("/risk/status"),
  riskLimits: () => get<RiskLimitsPayload>("/risk/limits"),
  riskProfile: () => get<RiskProfilePayload>("/risk/profile"),
  riskProfileUpdate: (req: { profile_global?: number; profile_fast?: number; profile_smc?: number; overrides?: Record<string, unknown>; reason?: string }) =>
    put<unknown>("/risk/profile", req),
  riskTripKillSwitch: (req?: { reason?: string; manual_override?: boolean }) =>
    post<unknown>("/risk/kill-switch/trip", req ?? {}),
  riskResetKillSwitch: (req?: { reason?: string; manual_override?: boolean }) =>
    post<unknown>("/risk/kill-switch/reset", req ?? {}),
  // Phase 2: Feed Health & Desk Status
  feedHealth: () => get<{ status: string; feed_status: FeedRow[]; updated_at: string }>("/api/v1/feed-health"),
  deskStatus: () => get<{ status: string; fast_desk: any; smc_desk: any; updated_at: string }>("/api/v1/desk-status"),
  // Phase 1-2: Configuration endpoints
  getLlmModels: () => get<{ status: string; models: any[]; count: number }>("/api/v1/llm/models"),
  getLlmStatus: () => get<{ status: string; localai_url: string; default_model: string | null; current_model: string; llm_enabled: boolean; available: boolean; models_count: number }>("/api/v1/llm/status"),
  setLlmDefaultModel: (model_id: string) => put<{ status: string; model_id: string; message: string }>("/api/v1/llm/models/default", { model_id }),
  getSmcConfig: () => get<{ status: string; config: any }>("/api/v1/config/smc"),
  updateSmcConfig: (config: any) => put<{ status: string; config: any; message: string }>("/api/v1/config/smc", config),
  getSmcTraderConfig: () => get<{ status: string; config: any }>("/api/v1/config/smc/trader"),
  updateSmcTraderConfig: (config: any) => put<{ status: string; config: any; message: string }>("/api/v1/config/smc/trader", config),
  getFastConfig: () => get<{ status: string; config: any }>("/api/v1/config/fast"),
  updateFastConfig: (config: any) => put<{ status: string; config: any; message: string }>("/api/v1/config/fast", config),
  setFastDeskEnabled: (enabled: boolean) => put<{ status: string; enabled: boolean; message: string }>("/api/v1/config/fast/enabled", { enabled }),
  setSmcDeskEnabled: (enabled: boolean) => put<{ status: string; enabled: boolean; message: string }>("/api/v1/config/smc/enabled", { enabled }),
  getOwnershipConfig: () => get<{ status: string; config: any }>("/api/v1/config/ownership"),
  updateOwnershipConfig: (config: any) => put<{ status: string; config: any; message: string }>("/api/v1/config/ownership", config),
  getRiskConfig: () => get<{ status: string; config: any }>("/api/v1/config/risk"),
  updateRiskConfig: (config: any) => put<{ status: string; config: any; message: string }>("/api/v1/config/risk", config),
  // Fast Desk — Activity & Signals
  fastActivity: (limit = 50) => get<FastActivityResponse>(`/api/v1/fast/activity?limit=${limit}`),
  fastActivitySymbol: (symbol: string, limit = 50) => get<{ status: string; symbol: string; events: FastActivityResponse["events"]; updated_at: string }>(`/api/v1/fast/activity/${symbol}?limit=${limit}`),
  fastZones: (symbol?: string) => get<{ status: string; zones: FastZoneRow[]; updated_at: string }>(symbol ? `/api/v1/fast/zones?symbol=${symbol}` : "/api/v1/fast/zones"),
  fastSignals: (limit = 50) => get<{ status: string; signals: FastSignalRow[]; updated_at: string }>(`/api/v1/fast/signals?limit=${limit}`),
  fastTradeLog: (limit = 50) => get<{ status: string; events: FastTradeLogRow[]; updated_at: string }>(`/api/v1/fast/trade-log?limit=${limit}`),
  fastPipeline: (limit = 60) => get<PipelineSnapshotResponse>(`/api/v1/fast/pipeline?limit=${limit}`),
  // SMC Desk — Theses, Zones & Events
  smcTheses: () => get<{ status: string; theses: SmcThesis[]; updated_at: string }>("/api/v1/smc/theses"),
  smcZones: (symbol?: string) => get<{ status: string; zones: SmcZone[]; updated_at: string }>(symbol ? `/api/v1/smc/zones?symbol=${symbol}` : "/api/v1/smc/zones"),
  smcEvents: (limit = 100) => get<{ status: string; events: SmcEventRow[]; updated_at: string }>(`/api/v1/smc/events?limit=${limit}`),
  // Desk Assignments
  getDeskAssignments: () => get<{ assignments: Record<string, string[]> }>("/api/v1/symbols/desk-assignments"),
  setSymbolDesks: (symbol: string, desks: string[]) =>
    put<{ symbol: string; desks: string[] }>(`/api/v1/symbols/${symbol}/desks`, { desks }),
  // Correlation Engine
  correlationMatrix: (timeframe: string) =>
    get<CorrelationMatrixResponse>(`/api/v1/correlation/${timeframe}`),
};
