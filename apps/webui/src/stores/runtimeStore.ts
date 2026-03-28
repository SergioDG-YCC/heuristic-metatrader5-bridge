import { createSignal, createEffect, onCleanup } from "solid-js";
import { createStore } from "solid-js/store";
import type { LiveStateSnapshot, BootState, AlertItem } from "../types/api";
import { api } from "../api/client";
import { startSSE, onSnapshot, onSSEError, isSSEConnected } from "../api/sse";

// ─── State ────────────────────────────────────────────────────────────────────
interface RuntimeStore {
  bootState: BootState;
  snapshot: LiveStateSnapshot | null;
  lastUpdated: string | null;
  sseConnected: boolean;
  /** true if last /status poll succeeded */
  statusReachable: boolean;
  /** ms since last live snapshot */
  staleSince: number | null;
  alerts: AlertItem[];
}

const [state, setState] = createStore<RuntimeStore>({
  bootState: "launching_ui",
  snapshot: null,
  lastUpdated: null,
  sseConnected: false,
  statusReachable: false,
  staleSince: null,
  alerts: [],
});

export { state as runtimeStore };

// ─── Freshness tracking ───────────────────────────────────────────────────────
const STALE_THRESHOLD_MS = 15_000;
const [, setLastSnapshotAt] = createSignal<number>(0);

function markFresh() {
  setLastSnapshotAt(Date.now());
  setState("staleSince", null);
}

// ─── Snapshot ingestion ───────────────────────────────────────────────────────
function ingestSnapshot(snapshot: LiveStateSnapshot) {
  setState("snapshot", snapshot);
  setState("lastUpdated", snapshot.updated_at ?? new Date().toISOString());
  setState("statusReachable", true);
  markFresh();

  if (state.bootState !== "ready") {
    setState("bootState", "ready");
  }

  // Derive alerts from snapshot
  setState("alerts", deriveAlerts(snapshot));
}

// ─── Alert derivation (derived from live payload) ─────────────────────────────
function deriveAlerts(snap: LiveStateSnapshot): AlertItem[] {
  const items: AlertItem[] = [];
  const now = new Date().toISOString();

  const status = snap.status ?? "unknown";
  if (status !== "running" && status !== "ready" && status !== "ok") {
    items.push({
      id: "runtime-status",
      severity: "warning",
      source: "live",
      title: `Runtime status: ${status}`,
      detail: "Bridge is not in a running/ready state.",
      timestamp: now,
    });
  }

  const health = snap.health ?? {};
  if (health.mt5_connector && !["up", "ok", "connected"].includes(String(health.mt5_connector))) {
    items.push({
      id: "mt5-connector",
      severity: "critical",
      source: "live",
      title: `MT5 connector: ${health.mt5_connector}`,
      timestamp: now,
    });
  }
  if (health.market_state === "degraded") {
    items.push({
      id: "market-state-degraded",
      severity: "warning",
      source: "live",
      title: "Market state is degraded",
      detail: String(health.market_state_error ?? ""),
      timestamp: now,
    });
  }
  if (snap.runtime_metrics?.local_clock_warning) {
    items.push({
      id: "clock-drift",
      severity: "warning",
      source: "derived",
      title: "Local clock drift detected (>1.5s)",
      detail: `avg drift: ${snap.runtime_metrics.local_clock_drift_ms_avg ?? 0}ms`,
      timestamp: now,
    });
  }

  const acct = snap.account_summary;
  if (acct) {
    const marginLevel = Number(acct.margin_level ?? 0);
    if (marginLevel > 0 && marginLevel < 150) {
      items.push({
        id: "margin-level-low",
        severity: marginLevel < 100 ? "critical" : "warning",
        source: "derived",
        title: `Margin level low: ${marginLevel.toFixed(0)}%`,
        timestamp: now,
      });
    }
    const profit = Number(acct.profit ?? 0);
    if (profit < -500) {
      items.push({
        id: "floating-pnl-negative",
        severity: "warning",
        source: "derived",
        title: `Floating P&L: ${profit.toFixed(2)} ${acct.currency ?? ""}`,
        timestamp: now,
      });
    }
  }

  return items;
}

// ─── Startup sequence ─────────────────────────────────────────────────────────
let _statusPollId: ReturnType<typeof setInterval> | null = null;
let _stalenessCheckId: ReturnType<typeof setInterval> | null = null;
let _pollFailCount = 0;

export function initRuntimeStore() {
  setState("bootState", "waiting_for_control_plane");
  _pollFailCount = 0;

  // SSE setup
  startSSE(1.0);

  const offSnapshot = onSnapshot((snap) => {
    setState("sseConnected", true);
    ingestSnapshot(snap);
  });

  const offError = onSSEError(() => {
    setState("sseConnected", false);
    if (state.bootState === "ready") {
      setState("bootState", "reconnecting");
    }
  });

  // Poll /status as authoritative boot signal and fallback
  async function pollStatus() {
    try {
      const snap = await api.status();
      _pollFailCount = 0;
      if (state.bootState === "waiting_for_control_plane") {
        setState("bootState", "control_plane_detected_syncing");
      }
      ingestSnapshot(snap);
    } catch {
      _pollFailCount++;
      setState("statusReachable", false);
      if (state.bootState === "ready") {
        setState("bootState", "reconnecting");
      } else if (_pollFailCount >= 3 && state.bootState !== "degraded_unavailable") {
        setState("bootState", "degraded_unavailable");
      }
    }
  }

  // Poll immediately, then every 5s
  void pollStatus();
  _statusPollId = setInterval(pollStatus, 5_000);

  // Staleness guard — check every 3s
  _stalenessCheckId = setInterval(() => {
    setState("sseConnected", isSSEConnected());
  }, 3_000);

  onCleanup(() => {
    offSnapshot();
    offError();
    if (_statusPollId !== null) clearInterval(_statusPollId);
    if (_stalenessCheckId !== null) clearInterval(_stalenessCheckId);
  });
}
