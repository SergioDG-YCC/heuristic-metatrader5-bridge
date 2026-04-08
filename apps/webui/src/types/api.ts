// ─── Capability State ────────────────────────────────────────────────────────
export type CapabilityState =
  | "Live"
  | "Derived"
  | "Partial"
  | "Preview"
  | "Planned"
  | "Unknown"
  | "Disabled";

// ─── Health ──────────────────────────────────────────────────────────────────
export interface RuntimeHealth {
  status: string;
  mt5_connector?: string;
  market_state?: string;
  broker_sessions?: string;
  indicator_bridge?: string;
  account_state?: string;
  symbol_catalog?: string;
  updated_at?: string;
  [key: string]: unknown;
}

// ─── Live State Snapshot (from /status and /events) ──────────────────────────
export interface LiveStateSnapshot {
  status: string;
  health: RuntimeHealth;
  broker_identity: BrokerIdentity;
  server_time_offset_seconds: number;
  trade_allowed?: boolean;  // NEW: Trade permission status
  universes: {
    catalog_universe_count: number;
    bootstrap_universe: string[];
    subscribed_universe: string[];
    bootstrap_rejected_symbols: string[];
  };
  watched_timeframes: string[];
  chart_workers: {
    count: number;
    symbols: string[];
    workers: ChartWorkerStatus[];
  };
  feed_status: FeedRow[];
  broker_session_registry: unknown;
  account_summary: AccountState | null;
  ownership?: { status: "up" | "inactive"; summary?: OwnershipSummary; last_reconcile?: unknown };
  risk?: { status: "up" | "inactive"; [key: string]: unknown };
  exposure_state: ExposureState | null;
  open_positions: PositionRow[];
  open_orders: OrderRow[];
  indicator_enrichment: IndicatorStatus;
  runtime_metrics: RuntimeMetrics;
  symbol_catalog: SymbolCatalogStatus;
  symbol_specifications_count: number;
  symbol_desk_assignments?: Record<string, string[]>;
  updated_at: string;
}

// ─── Broker Identity ─────────────────────────────────────────────────────────
export interface BrokerIdentity {
  broker_server?: string;
  broker_company?: string;
  account_login?: number | string;
  terminal_name?: string;
  terminal_path?: string;
  [key: string]: unknown;
}

// ─── Account State ───────────────────────────────────────────────────────────
export interface AccountState {
  account_login?: number;
  broker_server?: string;
  broker_company?: string;
  account_mode?: string;
  currency?: string;
  leverage?: number;
  balance?: number;
  equity?: number;
  margin?: number;
  free_margin?: number;
  margin_level?: number;
  profit?: number;
  drawdown_amount?: number;
  drawdown_percent?: number;
  open_position_count?: number;
  pending_order_count?: number;
  [key: string]: unknown;
}

// ─── Exposure State ──────────────────────────────────────────────────────────
export interface ExposureState {
  open_position_count?: number;
  gross_exposure?: number;
  net_exposure?: number;
  floating_profit?: number;
  symbols?: SymbolExposure[];
  [key: string]: unknown;
}

export interface SymbolExposure {
  symbol: string;
  net_volume?: number;
  gross_volume?: number;
  floating_profit?: number;
  open_position_count?: number;
  used_margin_share?: number;
  risk_in_flight?: number;
  [key: string]: unknown;
}

// ─── Position / Order ────────────────────────────────────────────────────────
export interface PositionRow {
  position_id?: number;
  symbol?: string;
  side?: "buy" | "sell";
  volume?: number;
  price_open?: number;
  price_current?: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  profit?: number;
  swap?: number;
  commission?: number;
  magic?: number;
  comment?: string;
  opened_at?: string;
  updated_at?: string;
  status?: string;
  [key: string]: unknown;
}

export interface OrderRow {
  order_id?: number;
  symbol?: string;
  order_type?: string;
  volume_initial?: number;
  volume_current?: number;
  price_open?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  comment?: string;
  status?: string;
  created_at?: string;
  [key: string]: unknown;
}

// ─── Recent Deal / Order ─────────────────────────────────────────────────────
export interface RecentDeal {
  deal_id?: number;
  order_id?: number;
  symbol?: string;
  profit?: number;
  commission?: number;
  swap?: number;
  fee?: number;
  volume?: number;
  price?: number;
  time?: string;
  entry?: number;
  comment?: string;
  [key: string]: unknown;
}

export interface RecentOrder {
  ticket?: number;
  symbol?: string;
  type?: number;
  state?: number;
  volume_initial?: number;
  price_open?: number;
  sl?: number;
  tp?: number;
  comment?: string;
  time_setup?: number | string;
  time_done?: number | string;
  [key: string]: unknown;
}

// ─── Chart Context ────────────────────────────────────────────────────────────
export interface ChartContext {
  symbol?: string;
  timeframe?: string;
  candle_count?: number;
  last_bar_time?: string;
  bar_range_start?: string;
  bar_range_end?: string;
  [key: string]: unknown;
}

export interface Candle {
  time?: number | string;
  timestamp?: number | string;
  t?: number | string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  tick_volume?: number;
  [key: string]: unknown;
}

export interface ChartResponse {
  chart_context: ChartContext;
  candles: Candle[];
}

// ─── Symbol Spec ─────────────────────────────────────────────────────────────
export interface SymbolSpec {
  symbol?: string;
  description?: string;
  contract_size?: number;
  tick_size?: number;
  tick_value?: number;
  spread_points?: number;
  spread_float?: boolean;
  point?: number;
  stops_level_points?: number;
  freeze_level_points?: number;
  volume_min?: number;
  volume_max?: number;
  volume_step?: number;
  volume_limit?: number;
  digits?: number;
  currency_base?: string;
  currency_profit?: string;
  currency_margin?: string;
  swap_long?: number;
  swap_short?: number;
  margin_initial?: number;
  margin_maintenance?: number;
  margin_hedged?: number;
  [key: string]: unknown;
}

// ─── Catalog ─────────────────────────────────────────────────────────────────
export interface CatalogEntry {
  symbol?: string;
  description?: string;
  path?: string;
  asset_class?: string;
  path_group?: string;
  path_subgroup?: string;
  visible?: boolean;
  selected?: boolean;
  custom?: boolean;
  trade_mode?: number;
  digits?: number;
  currency_base?: string;
  currency_profit?: string;
  currency_margin?: string;
  broker_server?: string;
  broker_company?: string;
  account_login?: number;
  account_currency?: string;
  [key: string]: unknown;
}

export interface CatalogResponse {
  symbols: CatalogEntry[];
  status: SymbolCatalogStatus;
}

// ─── Chart Worker / Feed ─────────────────────────────────────────────────────
export interface ChartWorkerStatus {
  symbol?: string;
  timeframe?: string;
  state?: string;
  [key: string]: unknown;
}

export interface FeedRow {
  symbol?: string;
  timeframe?: string;
  last_bar_time?: string;
  bar_count?: number;
  state?: string;
  [key: string]: unknown;
}

// ─── Indicator / Runtime Metrics ─────────────────────────────────────────────
export interface IndicatorStatus {
  enabled?: boolean;
  status?: string;
  [key: string]: unknown;
}

export interface RuntimeMetrics {
  poll_duration_ms_avg?: number;
  poll_duration_ms_max?: number;
  local_clock_drift_ms_avg?: number;
  local_clock_warning?: boolean;
  ingress_errors?: string[];
  updated_at?: string;
  [key: string]: unknown;
}

export interface SymbolCatalogStatus {
  status?: string;
  symbol_count?: number;
  updated_at?: string;
}

// ─── Account full payload (from /account) ────────────────────────────────────
export interface AccountPayload {
  account_state?: AccountState;
  exposure_state?: ExposureState;
  positions?: PositionRow[];
  orders?: OrderRow[];
  recent_deals?: RecentDeal[];
  recent_orders?: RecentOrder[];
  [key: string]: unknown;
}

// ─── Alert Item ───────────────────────────────────────────────────────────────
export type AlertSeverity = "critical" | "warning" | "info";
export type AlertSource = "live" | "derived" | "preview" | "unknown";

export interface AlertItem {
  id: string;
  severity: AlertSeverity;
  source: AlertSource;
  title: string;
  detail?: string;
  timestamp: string;
}

// ─── Ownership ──────────────────────────────────────────────────────────────
export interface OwnershipItem {
  operation_uid: string;
  operation_type: "position" | "order";
  position_id?: number | null;
  order_id?: number | null;
  desk_owner: "fast" | "smc" | "unassigned";
  ownership_status: "fast_owned" | "smc_owned" | "unassigned" | "inherited_fast";
  lifecycle_status: "active" | "closed" | "cancelled";
  origin_type?: string;
  reevaluation_required?: boolean;
  reason?: string | null;
  adopted_at?: string | null;
  reassigned_at?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
  cancelled_at?: string | null;
  last_seen_open_at?: string | null;
  updated_at?: string | null;
  age_seconds?: number | null;
  metadata?: Record<string, unknown>;
}

export interface OwnershipSummary {
  total: number;
  open: number;
  history: number;
  reevaluation_required_open: number;
  inherited_open: number;
  by_owner: { fast: number; smc: number; unassigned: number };
}

export interface OwnershipPayload {
  items: OwnershipItem[];
  summary: OwnershipSummary;
}

// ─── Risk ────────────────────────────────────────────────────────────────────
export interface RiskLimitSet {
  max_total_exposure?: number;
  max_single_position?: number;
  max_daily_loss?: number;
  max_drawdown_pct?: number;
  max_open_positions?: number;
  max_pending_orders?: number;
  [key: string]: unknown;
}

export interface RiskLimitsPayload {
  global: RiskLimitSet;
  desks: { fast: RiskLimitSet; smc: RiskLimitSet };
}

export interface RiskProfilePayload {
  global: number;
  fast: number;
  smc: number;
  overrides: Record<string, unknown>;
  weights: { fast: number; smc: number };
  kill_switch_enabled: boolean;
}

export interface RiskStatusPayload {
  profile: RiskProfilePayload;
  limits: RiskLimitsPayload;
  allocator: Record<string, unknown>;
  usage: Record<string, unknown>;
  ownership_usage: Record<string, unknown>;
  kill_switch: Record<string, unknown>;
  events: unknown[];
}

// ─── Boot State ───────────────────────────────────────────────────────────────
export type BootState =
  | "launching_ui"
  | "waiting_for_control_plane"
  | "control_plane_detected_syncing"
  | "ready"
  | "reconnecting"
  | "degraded_unavailable";

// ─── Fast Desk Activity ──────────────────────────────────────────────────────
export interface FastScanEvent {
  timestamp: string;
  symbol: string;
  gate_reached: string;
  gate_passed: boolean;
  details: Record<string, unknown>;
}

// ─── Fast Desk Pipeline Trace ────────────────────────────────────────────────
export interface PipelineStageResult {
  name: string;
  passed: boolean;
  details: Record<string, unknown>;
}

export interface PipelineTrace {
  trace_id: string;
  timestamp: string;
  symbol: string;
  stages: PipelineStageResult[];
  final_gate: string;
  final_passed: boolean;
}

export interface PipelineSnapshotResponse {
  status: string;
  traces: PipelineTrace[];
  cursor: number;
  updated_at: string;
}

export interface PipelineSSEPayload {
  traces: PipelineTrace[];
  cursor: number;
}

export interface FastSymbolSummary {
  last_gate: string;
  last_passed: boolean;
  last_timestamp: string;
  blocked_count: number;
  passed_count: number;
  block_by_gate: Record<string, number>;
}

export interface FastActivityResponse {
  status: string;
  events: FastScanEvent[];
  per_symbol_summary: Record<string, FastSymbolSummary>;
  updated_at: string;
}

// ─── Correlation Engine ───────────────────────────────────────────────────────
export interface CorrelationPairRow {
  symbol_a: string;
  symbol_b: string;
  coefficient: number | null;
  bars_used: number;
  coverage_ratio: number;
  coverage_ok: boolean;
  source_stale: boolean;
  computed_at: string;
}

export interface CorrelationMatrixResponse {
  status: string;
  timeframe: string;
  pairs: CorrelationPairRow[];
  pair_count: number;
  min_pair_bars: number;
  all_pairs_coverage_ok: boolean;
  computed_at: string;
  symbols: string[];
}

export interface FastSignalRow {
  signal_id: string;
  symbol: string;
  side: string;
  trigger: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  stop_loss_pips: number;
  outcome: string;
  generated_at: string;
  evidence_json?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface FastTradeLogRow {
  log_id: string;
  symbol: string;
  action: string;
  position_id?: number | null;
  signal_id?: string | null;
  details_json?: Record<string, unknown>;
  logged_at: string;
  [key: string]: unknown;
}

export interface FastZoneRow {
  symbol: string;
  source: "fast";
  setup_type: string;
  zone_type: string;
  side: string;
  timeframe_origin: string;
  display_timeframes?: string[];
  price_low: number;
  price_high: number;
  entry_price?: number;
  retest_level?: number;
  confidence?: number;
  htf_zone_state?: string;
  [key: string]: unknown;
}

// ─── SMC Desk Data ───────────────────────────────────────────────────────────
export interface SmcThesis {
  symbol: string;
  thesis_id: string;
  bias: string;
  status: string;
  base_scenario?: string | null;
  validator_decision?: string | null;
  analyst_notes?: string | null;
  operation_candidates?: SmcCandidate[];
  invalidations?: unknown[];
  watch_conditions?: unknown[];
  watch_levels?: unknown[];
  alternate_scenarios?: unknown[];
  prepared_zones?: unknown[];
  primary_zone_id?: string | null;
  multi_tf_alignment?: Record<string, unknown> | null;
  validation_summary?: Record<string, unknown> | null;
  validator_result?: Record<string, unknown> | null;
  created_at?: string;
  last_review_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface SmcCandidate {
  side?: string;
  entry_zone_high?: number;
  entry_zone_low?: number;
  stop_loss?: number;
  take_profit_1?: number;
  take_profit_2?: number;
  rr_ratio?: number;
  sl_justification?: string;
  tp_justification?: string;
  confluences?: string[];
  [key: string]: unknown;
}

export interface SmcZone {
  zone_id: string;
  symbol: string;
  timeframe: string;
  zone_type: string;
  price_high: number;
  price_low: number;
  quality_score: number;
  status: string;
  distance_pct?: number | null;
  confluences?: unknown[];
  detected_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface SmcEventRow {
  symbol: string;
  event_type: string;
  payload_json?: Record<string, unknown>;
  created_at: string;
  [key: string]: unknown;
}
