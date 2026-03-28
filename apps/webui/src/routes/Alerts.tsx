import type { Component } from "solid-js";
import { Show, For, createSignal } from "solid-js";
import { runtimeStore } from "../stores/runtimeStore";
import { operationsStore } from "../stores/operationsStore";
import type { RecentDeal } from "../types/api";

type TabId = "critical" | "warnings" | "broker" | "state" | "audit";

type AlertClass = "crit" | "warn" | "info" | "unknown";

function alertClass(sev: string | undefined): AlertClass {
  if (sev === "critical") return "crit";
  if (sev === "warning") return "warn";
  if (sev === "info") return "info";
  return "unknown";
}

function numStr(v: unknown, dp = 5): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

const Alerts: Component = () => {
  const [activeTab, setActiveTab] = createSignal<TabId>("critical");

  const alerts = () => runtimeStore.alerts;
  const critical = () => alerts().filter((a) => a.severity === "critical");
  const warnings = () => alerts().filter((a) => a.severity === "warning");
  const info = () => alerts().filter((a) => a.severity === "info");
  const recentDeals = () => (operationsStore.account?.recent_deals ?? []) as RecentDeal[];

  return (
    <>
      {/* Tab bar */}
      <div class="tab-bar">
        <div
          class={`tab ${activeTab() === "critical" ? "active" : ""}`}
          onClick={() => setActiveTab("critical")}
        >
          Critical
          <Show when={critical().length > 0}>
            <span class="count count-red">{critical().length}</span>
          </Show>
        </div>
        <div
          class={`tab ${activeTab() === "warnings" ? "active" : ""}`}
          onClick={() => setActiveTab("warnings")}
        >
          Warnings
          <Show when={warnings().length > 0}>
            <span class="count count-amber">{warnings().length}</span>
          </Show>
        </div>
        <div
          class={`tab ${activeTab() === "broker" ? "active" : ""}`}
          onClick={() => setActiveTab("broker")}
        >
          Broker Activity
        </div>
        <div
          class={`tab ${activeTab() === "state" ? "active" : ""}`}
          onClick={() => setActiveTab("state")}
        >
          State Changes
        </div>
        <div
          class={`tab ${activeTab() === "audit" ? "active" : ""}`}
          onClick={() => setActiveTab("audit")}
          style={{ opacity: "0.5", cursor: "not-allowed" }}
          title="Planned — not yet available"
        >
          Audit History
          <span class="cap-badge planned" style={{ "margin-left": "5px", "font-size": "7px" }}>Planned</span>
        </div>
      </div>

      {/* Content area */}
      <div style={{ flex: "1", "overflow-y": "auto", padding: "8px 10px" }}>

        {/* Disclaimer */}
        <div class="disclaimer">
          ℹ Alerts are computed from live payloads each refresh cycle — not a certified audit log. History does not persist across page loads.
        </div>

        {/* Critical tab */}
        <Show when={activeTab() === "critical"}>
          <Show
            when={critical().length > 0}
            fallback={
              <div style={{ "font-size": "10px", color: "var(--text-muted)", "font-family": "var(--font-mono)", padding: "12px 0" }}>
                No critical alerts
              </div>
            }
          >
            <For each={critical()}>
              {(a) => (
                <div class="alert-card crit" style={{ "margin-bottom": "6px" }}>
                  <div style={{ display: "flex", "align-items": "center", gap: "6px", "margin-bottom": "3px" }}>
                    <span class="alert-sev crit">CRITICAL</span>
                    <Show when={a.source}>
                      <span style={{ "font-family": "var(--font-mono)", "font-size": "7.5px", color: "var(--text-muted)" }}>
                        {a.source}
                      </span>
                    </Show>
                  </div>
                  <div class="alert-msg">{a.title}</div>
                  <Show when={a.timestamp}>
                    <div class="alert-meta">{String(a.timestamp).slice(0, 19)}</div>
                  </Show>
                </div>
              )}
            </For>
          </Show>

          {/* Always-present unknown trade perm */}
          <div class="alert-card unknown">
            <div style={{ display: "flex", "align-items": "center", gap: "6px", "margin-bottom": "3px" }}>
              <span class="alert-sev unknown">UNKNOWN</span>
            </div>
            <div class="alert-msg" style={{ color: "var(--unknown-purple)" }}>
              Trading permission not exposed by current API. Cannot confirm AutoTrading state.
            </div>
            <div class="alert-meta" style={{ color: "var(--unknown-purple)" }}>scope: terminal · Unknown</div>
          </div>
        </Show>

        {/* Warnings tab */}
        <Show when={activeTab() === "warnings"}>
          <Show
            when={warnings().length > 0}
            fallback={
              <div style={{ "font-size": "10px", color: "var(--text-muted)", "font-family": "var(--font-mono)", padding: "12px 0" }}>
                No warnings — runtime is healthy
              </div>
            }
          >
            <For each={warnings()}>
              {(a) => (
                <div class="alert-card warn" style={{ "margin-bottom": "6px" }}>
                  <div style={{ display: "flex", "align-items": "center", gap: "6px", "margin-bottom": "3px" }}>
                    <span class="alert-sev warn">WARN</span>
                    <Show when={a.source}>
                      <span style={{ "font-family": "var(--font-mono)", "font-size": "7.5px", color: "var(--text-muted)" }}>
                        {a.source}
                      </span>
                    </Show>
                  </div>
                  <div class="alert-msg">{a.title}</div>
                  <Show when={a.timestamp}>
                    <div class="alert-meta">{String(a.timestamp).slice(0, 19)}</div>
                  </Show>
                </div>
              )}
            </For>
          </Show>
          <Show when={info().length > 0}>
            <div style={{ "margin-top": "8px", "margin-bottom": "4px", "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)", "text-transform": "uppercase" }}>
              Info
            </div>
            <For each={info()}>
              {(a) => (
                <div class={`alert-card ${alertClass(a.severity)}`} style={{ "margin-bottom": "6px" }}>
                  <div class={`alert-sev ${alertClass(a.severity)}`}>{(a.severity ?? "info").toUpperCase()}</div>
                  <div class="alert-msg">{a.title}</div>
                </div>
              )}
            </For>
          </Show>
        </Show>

        {/* Broker activity tab */}
        <Show when={activeTab() === "broker"}>
          <Show
            when={recentDeals().length > 0}
            fallback={
              <div style={{ "font-size": "10px", color: "var(--text-muted)", "font-family": "var(--font-mono)", padding: "12px 0" }}>
                No recent broker activity
              </div>
            }
          >
            <For each={recentDeals().slice(0, 30)}>
              {(deal) => (
                <div class="broker-tl-entry">
                  <span class="broker-tl-time">{String(deal.time ?? "—").slice(11, 19)}</span>
                  <span class="broker-tl-type deal">Deal</span>
                  <span class="broker-tl-detail">
                    #{String(deal.ticket ?? "—")} {String(deal.symbol ?? "—")} {String(deal.type ?? "")} {numStr(deal.volume, 2)} · P&L{" "}
                    <span style={{ color: Number(deal.profit ?? 0) >= 0 ? "var(--green)" : "var(--red)", "font-weight": "600" }}>
                      {Number(deal.profit ?? 0) >= 0 ? "+" : ""}{numStr(deal.profit, 2)}
                    </span>
                  </span>
                </div>
              )}
            </For>
          </Show>
        </Show>

        {/* State changes tab */}
        <Show when={activeTab() === "state"}>
          <Show
            when={alerts().length > 0}
            fallback={
              <div style={{ "font-size": "10px", color: "var(--text-muted)", "font-family": "var(--font-mono)", padding: "12px 0" }}>
                No state change events recorded this session
              </div>
            }
          >
            <For each={alerts()}>
              {(a) => (
                <div class={`alert-card ${alertClass(a.severity)}`} style={{ "margin-bottom": "6px" }}>
                  <div class={`alert-sev ${alertClass(a.severity)}`}>{(a.severity ?? "info").toUpperCase()}</div>
                  <div class="alert-msg">{a.title}</div>
                  <Show when={a.timestamp}>
                    <div class="alert-meta">{String(a.timestamp).slice(0, 19)}</div>
                  </Show>
                </div>
              )}
            </For>
          </Show>
        </Show>

        {/* Audit history tab (planned) */}
        <Show when={activeTab() === "audit"}>
          <div class="preview-box">
            <div class="pb-title">
              <span class="cap-badge planned">Planned</span>
              Audit History
            </div>
            <div class="pb-desc">
              Durable audit trail requires a persistent event log. Not yet implemented — the /events endpoint is a live SSE snapshot stream, not a stored audit log.
            </div>
          </div>
        </Show>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Alerts / Events</span>
        <span>Source: derived from /status · /events (SSE) · /account (recent_deals)</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Alerts;
