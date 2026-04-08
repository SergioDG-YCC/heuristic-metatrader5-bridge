import type { Component } from "solid-js";
import { Show, For, onMount, createSignal, createResource } from "solid-js";
import { operationsStore, initOperationsStore } from "../stores/operationsStore";
import { api } from "../api/client";
import type { RiskStatusPayload } from "../types/api";

function numStr(v: unknown, dp = 2): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function marginLevelClass(v: number): "ok" | "warn" | "crit" {
  if (v === 0) return "warn";
  if (v < 100) return "crit";
  if (v < 150) return "warn";
  return "ok";
}

function marginLevelColor(v: number): string {
  if (v === 0) return "var(--text-muted)";
  if (v < 100) return "var(--red)";
  if (v < 150) return "var(--amber)";
  return "var(--green)";
}

const Risk: Component = () => {
  onMount(() => {
    initOperationsStore();
  });

  const acct = () => operationsStore.account?.account_state;
  const exp = () => operationsStore.exposure;
  const bal = () => Number(acct()?.balance ?? 0);
  const eq = () => Number(acct()?.equity ?? 0);
  const marginLevel = () => Number(acct()?.margin_level ?? 0);
  const drawdownPct = () => (bal() > 0 ? ((bal() - eq()) / bal()) * 100 : 0);

  const maxExpVol = () => {
    const syms = exp()?.symbols ?? [];
    return syms.reduce((mx, r) => Math.max(mx, Math.abs(Number(r.net_volume ?? 0))), 0) || 1;
  };

  const [riskStatus, { refetch: refetchRisk }] = createResource<RiskStatusPayload>(() => api.riskStatus());
  const [killSwitchPending, setKillSwitchPending] = createSignal(false);

  async function handleKillSwitch(trip: boolean) {
    setKillSwitchPending(true);
    try {
      if (trip) {
        await api.riskTripKillSwitch({ reason: "manual – UI operator" });
      } else {
        await api.riskResetKillSwitch({ reason: "manual – UI operator" });
      }
      void refetchRisk();
    } finally {
      setKillSwitchPending(false);
    }
  }

  return (
    <>
      {/* Desk accent */}
      <div class="desk-accent-amber" />

      {/* 3-column grid */}
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "1fr 1fr 200px",
          "grid-template-rows": "auto 1fr",
          gap: "6px",
          padding: "8px 10px",
          "overflow-y": "auto",
        }}
      >
        {/* Global risk profile health cards (full width) */}
        <div class="panel" style={{ "grid-column": "1 / 4" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--amber)" }} />
              Global Risk Profile
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <div style={{ display: "grid", "grid-template-columns": "repeat(5, 1fr)", gap: "6px" }}>
              <div class={`health-card ${marginLevelClass(marginLevel())}`}>
                <div class="hl">Margin Level</div>
                <div class="hv" style={{ color: marginLevelColor(marginLevel()) }}>
                  {marginLevel() > 0 ? `${marginLevel().toFixed(0)}%` : "—"}
                </div>
                <div class="hd">{marginLevel() < 150 && marginLevel() > 0 ? "Below 150% threshold" : "Healthy"}</div>
              </div>
              <div class={`health-card ${drawdownPct() > 5 ? "warn" : "ok"}`}>
                <div class="hl">Drawdown</div>
                <div class="hv" style={{ color: drawdownPct() > 5 ? "var(--amber)" : "var(--green)" }}>
                  {drawdownPct().toFixed(2)}%
                </div>
                <div class="hd">of account balance</div>
              </div>
              <div class="health-card ok">
                <div class="hl">Used Margin</div>
                <div class="hv" style={{ color: "var(--cyan-live)" }}>{numStr(acct()?.margin, 2)}</div>
                <div class="hd">of free {numStr(acct()?.free_margin, 2)}</div>
              </div>
              <div class="health-card ok">
                <div class="hl">Float PnL</div>
                <div class="hv" style={{ color: Number(acct()?.profit ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                  {Number(acct()?.profit ?? 0) >= 0 ? "+" : ""}{numStr(acct()?.profit, 2)}
                </div>
                <div class="hd">unrealised P&L</div>
              </div>
              <div class="health-card ok">
                <div class="hl">Open Positions</div>
                <div class="hv" style={{ color: "var(--text-primary)" }}>
                  {String(exp()?.open_position_count ?? 0)}
                </div>
                <div class="hd">{String(exp()?.gross_exposure ?? 0)} gross exp</div>
              </div>
            </div>
          </div>
        </div>

        {/* Exposure budget bars (left col) */}
        <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--amber)" }} />
              Exposure by Symbol
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body" style={{ "overflow-y": "auto", flex: "1" }}>
            <Show
              when={(exp()?.symbols?.length ?? 0) > 0}
              fallback={
                <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                  No exposure data
                </div>
              }
            >
              <For each={exp()?.symbols ?? []}>
                {(row) => {
                  const net = Number(row.net_volume ?? 0);
                  const pct = Math.min(Math.abs(net) / maxExpVol() * 45, 45);
                  const isLong = net >= 0;
                  const pnl = Number(row.floating_profit ?? 0);
                  const barColor = pnl >= 0 ? "var(--green)" : "var(--red)";
                  return (
                    <div class="exp-row">
                      <span class="exp-sym">{String(row.symbol ?? "—")}</span>
                      <div class="exp-track">
                        <div class="exp-center" />
                        <div
                          style={{
                            position: "absolute",
                            ...(isLong ? { left: "50%" } : { right: "50%" }),
                            height: "100%",
                            width: `${pct}%`,
                            background: barColor,
                            opacity: "0.65",
                            "border-radius": isLong ? "0 2px 2px 0" : "2px 0 0 2px",
                          }}
                        />
                      </div>
                      <span class="exp-val" style={{ color: pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                        {pnl >= 0 ? "+" : ""}{numStr(row.floating_profit, 2)}
                      </span>
                    </div>
                  );
                }}
              </For>
            </Show>
          </div>
        </div>

        {/* Derived risk warnings (center col) */}
        <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--red)" }} />
              Risk Signals
            </div>
            <span class="cap-badge derived">Derived</span>
          </div>
          <div class="panel-body" style={{ "overflow-y": "auto", flex: "1" }}>
            <Show when={marginLevel() > 0 && marginLevel() < 150}>
              <div class="alert-card warn" style={{ "margin-bottom": "6px" }}>
                <div class="alert-sev warn">WARN</div>
                <div class="alert-msg">
                  Margin level {marginLevel().toFixed(0)}% — {marginLevel() < 100 ? "margin call risk" : "approaching unsafe level"}.
                </div>
              </div>
            </Show>
            <Show when={drawdownPct() > 3}>
              <div class={`alert-card ${drawdownPct() > 5 ? "warn" : "info"}`} style={{ "margin-bottom": "6px" }}>
                <div class={`alert-sev ${drawdownPct() > 5 ? "warn" : "info"}`}>
                  {drawdownPct() > 5 ? "WARN" : "INFO"}
                </div>
                <div class="alert-msg">Drawdown {drawdownPct().toFixed(2)}% of balance.</div>
              </div>
            </Show>
            <Show when={marginLevel() === 0 && (exp()?.open_position_count ?? 0) === 0}>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)", "font-style": "italic" }}>
                No open positions — no active risk signals.
              </div>
            </Show>

            <div
              style={{
                "margin-top": "10px",
                "padding-top": "8px",
                "border-top": "1px solid var(--border-subtle)",
                "font-family": "var(--font-mono)",
                "font-size": "8.5px",
                color: "var(--text-muted)",
                "line-height": "1.6",
              }}
            >
              Signals derived from live /exposure and /account payloads. Not a certified risk system.
            </div>
          </div>
        </div>

        {/* Risk kernel governance (right col) */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--red)" }} />
              Risk Kernel
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <Show when={!riskStatus.loading && riskStatus()} fallback={
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                {riskStatus.loading ? "Loading…" : "Unavailable"}
              </div>
            }>
              {/* Kill switch */}
              <div style={{ "margin-bottom": "8px", padding: "6px 8px", background: "var(--bg-elevated)", "border-radius": "4px", "border": "1px solid var(--border-subtle)" }}>
                <div style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", "font-weight": "700", color: "var(--red)", "text-transform": "uppercase", "letter-spacing": "0.07em", "margin-bottom": "5px" }}>
                  Kill Switch
                </div>
                <div style={{ "font-family": "var(--font-mono)", "font-size": "9.5px", "margin-bottom": "6px" }}>
                  <span style={{ color: riskStatus()?.profile?.kill_switch_enabled ? "var(--red)" : "var(--green)", "font-weight": "700" }}>
                    {riskStatus()?.profile?.kill_switch_enabled ? "ARMED" : "SAFE"}
                  </span>
                  <span style={{ color: "var(--text-muted)", "margin-left": "6px", "font-size": "8.5px" }}>
                    {riskStatus()?.kill_switch ? JSON.stringify(riskStatus()?.kill_switch).slice(0, 60) : ""}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "5px" }}>
                  <button
                    disabled={killSwitchPending() || riskStatus()?.profile?.kill_switch_enabled === true}
                    onClick={() => void handleKillSwitch(true)}
                    style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", padding: "3px 10px", "border-radius": "3px", border: "1px solid var(--red)", background: "transparent", color: "var(--red)", cursor: "pointer", opacity: (killSwitchPending() || riskStatus()?.profile?.kill_switch_enabled) ? "0.4" : "1" }}
                  >Trip</button>
                  <button
                    disabled={killSwitchPending() || riskStatus()?.profile?.kill_switch_enabled !== true}
                    onClick={() => void handleKillSwitch(false)}
                    style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", padding: "3px 10px", "border-radius": "3px", border: "1px solid var(--green)", background: "transparent", color: "var(--green)", cursor: "pointer", opacity: (killSwitchPending() || !riskStatus()?.profile?.kill_switch_enabled) ? "0.4" : "1" }}
                  >Reset</button>
                </div>
              </div>

              {/* Profile */}
              <div style={{ "margin-bottom": "8px" }}>
                <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)", "text-transform": "uppercase", "letter-spacing": "0.06em", "margin-bottom": "4px" }}>Risk Profile</div>
                {(["global", "fast", "smc"] as const).map((k) => (
                  <div class="sub-row">
                    <span class="k">{k}</span>
                    <span class="v" style={{ color: "var(--amber)" }}>{String(riskStatus()?.profile?.[k] ?? "—")}</span>
                  </div>
                ))}
              </div>

              {/* Allocator */}
              <Show when={riskStatus()?.allocator}>
                <div>
                  <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)", "text-transform": "uppercase", "letter-spacing": "0.06em", "margin-bottom": "4px" }}>Allocator</div>
                  {Object.entries(riskStatus()?.allocator ?? {}).slice(0, 6).map(([k, v]) => (
                    <div class="sub-row">
                      <span class="k">{k.replace(/_/g, " ")}</span>
                      <span class="v">{typeof v === "number" ? v.toFixed(3) : String(v)}</span>
                    </div>
                  ))}
                </div>
              </Show>
            </Show>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Risk Center</span>
        <span>Source: /exposure · /account · Derived</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Risk;
