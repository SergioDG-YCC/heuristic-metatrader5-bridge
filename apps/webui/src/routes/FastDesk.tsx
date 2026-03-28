import type { Component } from "solid-js";
import { Show, For, onMount, onCleanup, createSignal } from "solid-js";
import { runtimeStore } from "../stores/runtimeStore";
import { operationsStore, initOperationsStore } from "../stores/operationsStore";
import { api } from "../api/client";
import type { PositionRow, FastScanEvent, FastSignalRow, FastTradeLogRow, FastSymbolSummary } from "../types/api";

function numStr(v: unknown, dp = 5): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function isBuyType(v: string | undefined): boolean {
  return v === "buy";
}

function typeLabel(v: string | undefined): string {
  return v ? v.toUpperCase() : "—";
}

const FastDesk: Component = () => {
  const [fastConfig, setFastConfig] = createSignal<any>(null);
  const [deskStatus, setDeskStatus] = createSignal<any>(null);
  const [loading, setLoading] = createSignal(true);
  const [activityEvents, setActivityEvents] = createSignal<FastScanEvent[]>([]);
  const [symbolSummary, setSymbolSummary] = createSignal<Record<string, FastSymbolSummary>>({});
  const [signals, setSignals] = createSignal<FastSignalRow[]>([]);
  const [tradeLog, setTradeLog] = createSignal<FastTradeLogRow[]>([]);
  
  let activityTimer: ReturnType<typeof setInterval> | undefined;
  let signalsTimer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    initOperationsStore();
    loadFastDeskData();
    pollActivity();
    pollSignals();
    activityTimer = setInterval(pollActivity, 3000);
    signalsTimer = setInterval(pollSignals, 5000);
  });

  onCleanup(() => {
    if (activityTimer) clearInterval(activityTimer);
    if (signalsTimer) clearInterval(signalsTimer);
  });

  async function pollActivity() {
    try {
      const r = await api.fastActivity(40);
      if (r.status === "success") {
        setActivityEvents(r.events);
        setSymbolSummary(r.per_symbol_summary);
      }
    } catch { /* ignore */ }
  }

  async function pollSignals() {
    try {
      const [sigR, logR] = await Promise.all([api.fastSignals(30), api.fastTradeLog(30)]);
      if (sigR.status === "success") setSignals(sigR.signals);
      if (logR.status === "success") setTradeLog(logR.events);
    } catch { /* ignore */ }
  }
  
  async function loadFastDeskData() {
    try {
      const [config, status] = await Promise.all([
        api.getFastConfig(),
        api.deskStatus(),
      ]);
      setFastConfig(config.status === "success" ? config.config : null);
      setDeskStatus(status.status === "success" ? status : null);
    } catch (e) {
      console.error("Failed to fetch Fast Desk data", e);
    } finally {
      setLoading(false);
    }
  }

  const snap = () => runtimeStore.snapshot;
  const exp = () => operationsStore.exposure;
  const positions = () => operationsStore.positions as PositionRow[];
  const acct = () => operationsStore.account?.account_state;

  // Pick first open position as the "focused symbol" for the header
  const focusSym = () => positions()[0]?.symbol ?? snap()?.universes?.subscribed_universe?.[0] ?? "—";

  return (
    <>
      {/* Desk accent */}
      <div class="desk-accent-teal" />

      {/* 2-column grid */}
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "1fr 220px",
          "grid-template-rows": "auto 1fr",
          gap: "6px",
          padding: "8px 10px",
          "overflow-y": "auto",
        }}
      >
        {/* Symbol Focus Header (full width) */}
        <div class="panel" style={{ "grid-column": "1 / 3" }}>
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
              <div style={{ display: "grid", "grid-template-columns": "repeat(6, 1fr)", gap: "8px" }}>
                {(
                  [
                    ["Status", deskStatus()?.fast_desk?.enabled ? "Active" : "Disabled", deskStatus()?.fast_desk?.enabled ? "var(--green)" : "var(--slate)"],
                    ["Workers", String(deskStatus()?.fast_desk?.workers ?? 0), "var(--cyan-live)"],
                    ["Open Positions", String(positions().length), "var(--text-primary)"],
                    ["Floating PnL", `${Number(exp()?.floating_profit ?? 0) >= 0 ? "+" : ""}${numStr(exp()?.floating_profit, 2)}`, Number(exp()?.floating_profit ?? 0) >= 0 ? "var(--green)" : "var(--red)"],
                    ["Subscribed", String(snap()?.universes?.subscribed_universe?.length ?? 0), "var(--text-primary)"],
                    ["Balance", numStr(acct()?.balance, 2), "var(--text-primary)"],
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

        {/* Positions table (left column) */}
        <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--green)" }} />
              Current Positions
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div style={{ flex: "1", "overflow-y": "auto" }}>
            <table class="data-table">
              <thead>
                <tr>
                  {["Ticket", "Symbol", "Side", "Vol", "Entry", "Current", "SL", "TP", "PnL"].map((h) => (
                    <th>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <Show
                  when={positions().length > 0}
                  fallback={
                    <tr>
                      <td colspan="9" style={{ "text-align": "center", color: "var(--text-muted)", padding: "14px" }}>
                        No open positions
                      </td>
                    </tr>
                  }
                >
                  <For each={positions()}>
                    {(p) => (
                      <tr>
                        <td>#{String(p.position_id ?? "—")}</td>
                        <td class="td-sym">{String(p.symbol ?? "—")}</td>
                        <td class={isBuyType(p.side) ? "td-buy" : "td-sell"}>{typeLabel(p.side)}</td>
                        <td style={{ "text-align": "right" }}>{numStr(p.volume, 2)}</td>
                        <td style={{ "text-align": "right" }}>{numStr(p.price_open)}</td>
                        <td style={{ "text-align": "right" }}>{numStr(p.price_current)}</td>
                        <td style={{ "text-align": "right", color: "var(--text-muted)" }}>{numStr(p.stop_loss)}</td>
                        <td style={{ "text-align": "right", color: "var(--text-muted)" }}>{numStr(p.take_profit)}</td>
                        <td
                          style={{ "text-align": "right" }}
                          class={Number(p.profit ?? 0) >= 0 ? "td-pos" : "td-neg"}
                        >
                          {Number(p.profit ?? 0) >= 0 ? "+" : ""}{numStr(p.profit, 2)}
                        </td>
                      </tr>
                    )}
                  </For>
                </Show>
              </tbody>
            </table>
          </div>
        </div>

        {/* Right column — spec summary + config panel */}
        <div style={{ display: "flex", "flex-direction": "column", gap: "6px" }}>
          {/* Spec summary */}
          <div class="panel">
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--teal)" }} />
                Spec Summary
              </div>
              <span class="cap-badge live">Live</span>
            </div>
            <div class="panel-body">
              {(
                [
                  ["Gross Exposure", numStr(exp()?.gross_exposure, 2)],
                  ["Net Exposure", numStr(exp()?.net_exposure, 2)],
                  ["Float PnL", `${Number(exp()?.floating_profit ?? 0) >= 0 ? "+" : ""}${numStr(exp()?.floating_profit, 2)}`],
                  ["Free Margin", numStr(acct()?.free_margin, 2)],
                ] as [string, string][]
              ).map(([k, v]) => (
                <div class="sub-row">
                  <span class="k">{k}</span>
                  <span class="v">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Fast Desk Config — Phase 3 */}
          <Show when={fastConfig()}>
            <div class="panel">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-dot" style={{ background: "var(--green)" }} />
                  Fast Desk Config
                </div>
                <span class="cap-badge live">Live</span>
              </div>
              <div class="panel-body">
                <div class="sub-row">
                  <span class="k">Scan Interval:</span>
                  <span class="v">{fastConfig()?.scan_interval ?? "—"}s</span>
                </div>
                <div class="sub-row">
                  <span class="k">Risk %:</span>
                  <span class="v">{fastConfig()?.risk_per_trade_percent ?? "—"}%</span>
                </div>
                <div class="sub-row">
                  <span class="k">Max Positions:</span>
                  <span class="v">{fastConfig()?.max_positions_total ?? "—"}</span>
                </div>
                <div class="sub-row">
                  <span class="k">Min Confidence:</span>
                  <span class="v">{fastConfig()?.min_signal_confidence ?? "—"}</span>
                </div>
                <div class="sub-row">
                  <span class="k">ATR SL Mult:</span>
                  <span class="v">{fastConfig()?.atr_multiplier_sl ?? "—"}</span>
                </div>
              </div>
            </div>
          </Show>

          <Show when={!fastConfig() && deskStatus()?.fast_desk?.enabled}>
            <div class="panel">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-dot" style={{ background: "var(--amber)" }} />
                  Config Not Loaded
                </div>
                <span class="cap-badge preview">Preview</span>
              </div>
              <div class="panel-body">
                <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                  Fast Desk config endpoint not available. Config will appear here when API is ready.
                </div>
              </div>
            </div>
          </Show>
        </div>
      </div>

      {/* ── Pipeline Activity Panel (full width) ── */}
      <div style={{ padding: "0 10px 6px" }}>
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--amber)" }} />
              Pipeline Activity
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          {/* Per-symbol summary badges */}
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
                    <span style={{
                      "font-family": "var(--font-mono)", "font-size": "8px", padding: "2px 6px",
                      "border-radius": "3px",
                      background: s.last_passed ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                      color: s.last_passed ? "var(--green)" : "var(--red)",
                    }}>
                      {sym}: {topGate() || "passed"}
                    </span>
                  );
                }}
              </For>
            </div>
          </Show>
          <div style={{ "max-height": "220px", "overflow-y": "auto" }}>
            <table class="data-table">
              <thead>
                <tr>
                  {["Time", "Symbol", "Gate", "Status", "Details"].map((h) => <th>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                <Show when={activityEvents().length > 0} fallback={
                  <tr><td colspan="5" style={{ "text-align": "center", color: "var(--text-muted)", padding: "14px" }}>No activity events yet</td></tr>
                }>
                  <For each={activityEvents().slice(0, 30)}>
                    {(evt) => (
                      <tr>
                        <td style={{ "font-size": "8px", "white-space": "nowrap" }}>{evt.timestamp.replace("T", " ").replace("Z", "")}</td>
                        <td class="td-sym">{evt.symbol}</td>
                        <td style={{ "font-family": "var(--font-mono)", "font-size": "8px" }}>{evt.gate_reached}</td>
                        <td>
                          <span style={{
                            "font-size": "8px", "font-weight": "600", padding: "1px 5px", "border-radius": "3px",
                            background: evt.gate_passed ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                            color: evt.gate_passed ? "var(--green)" : "var(--red)",
                          }}>
                            {evt.gate_passed ? "PASS" : "BLOCKED"}
                          </span>
                        </td>
                        <td style={{ "font-size": "8px", color: "var(--text-muted)", "max-width": "300px", overflow: "hidden", "text-overflow": "ellipsis", "white-space": "nowrap" }}>
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

      {/* ── Signals & Trade Log (2-column) ── */}
      <div style={{ display: "grid", "grid-template-columns": "1fr 1fr", gap: "6px", padding: "0 10px 6px" }}>
        {/* Signals panel */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--green)" }} />
              Signals &amp; Execution
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div style={{ "max-height": "200px", "overflow-y": "auto" }}>
            <table class="data-table">
              <thead>
                <tr>
                  {["Time", "Symbol", "Side", "Setup:Trigger", "Conf", "Outcome", "Vol"].map((h) => <th>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                <Show when={signals().length > 0} fallback={
                  <tr><td colspan="7" style={{ "text-align": "center", color: "var(--text-muted)", padding: "14px" }}>No signals yet</td></tr>
                }>
                  <For each={signals()}>
                    {(sig) => (
                      <tr>
                        <td style={{ "font-size": "8px", "white-space": "nowrap" }}>{(sig.generated_at || "").replace("T", " ").replace("Z", "")}</td>
                        <td class="td-sym">{sig.symbol}</td>
                        <td class={sig.side === "buy" ? "td-buy" : "td-sell"}>{(sig.side || "").toUpperCase()}</td>
                        <td style={{ "font-size": "8px" }}>{sig.trigger}</td>
                        <td style={{ "text-align": "right" }}>{(sig.confidence || 0).toFixed(2)}</td>
                        <td>
                          <span style={{
                            "font-size": "8px", "font-weight": "600", padding: "1px 5px", "border-radius": "3px",
                            background: sig.outcome === "accepted" ? "rgba(34,197,94,0.15)" : sig.outcome === "rejected" ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)",
                            color: sig.outcome === "accepted" ? "var(--green)" : sig.outcome === "rejected" ? "var(--red)" : "var(--amber)",
                          }}>
                            {(sig.outcome || "?").toUpperCase()}
                          </span>
                        </td>
                        <td style={{ "text-align": "right", "font-size": "8px" }}>{(sig.evidence_json as any)?.volume_lots != null ? Number((sig.evidence_json as any).volume_lots).toFixed(2) : "—"}</td>
                      </tr>
                    )}
                  </For>
                </Show>
              </tbody>
            </table>
          </div>
        </div>

        {/* Trade actions log panel */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              Trade Actions Log
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div style={{ "max-height": "200px", "overflow-y": "auto" }}>
            <table class="data-table">
              <thead>
                <tr>
                  {["Time", "Symbol", "Action", "Position", "Details"].map((h) => <th>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                <Show when={tradeLog().length > 0} fallback={
                  <tr><td colspan="5" style={{ "text-align": "center", color: "var(--text-muted)", padding: "14px" }}>No trade actions yet</td></tr>
                }>
                  <For each={tradeLog()}>
                    {(evt) => (
                      <tr>
                        <td style={{ "font-size": "8px", "white-space": "nowrap" }}>{(evt.logged_at || "").replace("T", " ").replace("Z", "")}</td>
                        <td class="td-sym">{evt.symbol}</td>
                        <td style={{ "font-family": "var(--font-mono)", "font-size": "8px" }}>{evt.action}</td>
                        <td>{evt.position_id ? `#${evt.position_id}` : "—"}</td>
                        <td style={{ "font-size": "8px", color: "var(--text-muted)", "max-width": "200px", overflow: "hidden", "text-overflow": "ellipsis", "white-space": "nowrap" }}>
                          {evt.details_json ? `${(evt.details_json as any)?.setup || ""} ${(evt.details_json as any)?.entry_type || ""}`.trim() || JSON.stringify(evt.details_json).slice(0, 60) : "—"}
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
        <span>Source: /positions · /exposure · /api/v1/config/fast · {deskStatus()?.fast_desk?.enabled ? "Live" : "Preview"}</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default FastDesk;
