import type { Component } from "solid-js";
import { For, Show, createMemo, onMount, createSignal } from "solid-js";
import { runtimeStore } from "../stores/runtimeStore";
import { api } from "../api/client";

type HealthClass = "ok" | "warn" | "crit";

function healthClass(val: string | undefined): HealthClass {
  if (!val) return "warn";
  if (["up", "ok", "running", "ready", "connected"].includes(val)) return "ok";
  if (["error", "failed", "down", "disconnected"].includes(val)) return "crit";
  return "warn";
}

function healthValColor(cls: HealthClass): string {
  if (cls === "ok") return "green";
  if (cls === "warn") return "amber";
  return "red";
}

type AlertClass = "crit" | "warn" | "info" | "unknown";

function alertClass(sev: string | undefined): AlertClass {
  if (sev === "critical") return "crit";
  if (sev === "warning") return "warn";
  if (sev === "info") return "info";
  return "unknown";
}

const RuntimeOverview: Component = () => {
  const snap = () => runtimeStore.snapshot;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const health = () => (snap()?.health ?? {}) as Record<string, string>;
  const acct = () => snap()?.account_summary;
  const universes = () => snap()?.universes;
  
  // Phase 2: Feed Health & Desk Status signals
  const [feedHealth, setFeedHealth] = createSignal<any>(null);
  const [deskStatus, setDeskStatus] = createSignal<any>(null);
  
  onMount(async () => {
    // Fetch feed health and desk status
    try {
      const [feed, desk] = await Promise.all([
        api.feedHealth(),
        api.deskStatus(),
      ]);
      setFeedHealth(feed);
      setDeskStatus(desk);
    } catch (e) {
      console.error("Failed to fetch Phase 2 data", e);
    }
  });

  const healthCards = createMemo(() => [
    {
      label: "MT5 Connection",
      val: health().mt5_connector ?? "—",
      cls: healthClass(health().mt5_connector),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      detail: (acct() as any)?.server ?? "Not available",
    },
    {
      label: "Data Feed",
      val: health().market_state ?? "—",
      cls: healthClass(health().market_state),
      detail: `${universes()?.subscribed_universe?.length ?? 0} subscribed`,
    },
    {
      label: "SSE Stream",
      val: runtimeStore.sseConnected ? "Active" : "Disconnected",
      cls: (runtimeStore.sseConnected ? "ok" : "crit") as HealthClass,
      detail: runtimeStore.lastUpdated
        ? `Last ${Math.round((Date.now() - new Date(runtimeStore.lastUpdated).getTime()) / 1000)}s ago`
        : "—",
    },
    {
      label: "Broker Sessions",
      val: health().broker_sessions ?? "—",
      cls: healthClass(health().broker_sessions),
      detail: "Broker session layer",
    },
    {
      label: "Runtime",
      val: health().status ?? "—",
      cls: healthClass(health().status),
      detail: "Core runtime process",
    },
  ]);

  const streamRows = createMemo(() => {
    const s = snap();
    if (!s) return [];
    const now = runtimeStore.lastUpdated;
    const t = now ? new Date(now).toISOString().slice(11, 19) : "—";
    const delta = now ? `Δ ${Math.round((Date.now() - new Date(now).getTime()) / 1000)}s` : "";
    const rows: { time: string; type: string; content: string; delta: string }[] = [];
    if (health().status) {
      rows.push({
        time: t,
        type: "runtime",
        content: `Bridge ${health().status} · ${universes()?.subscribed_universe?.length ?? 0} subscribed`,
        delta,
      });
    }
    if (acct()) {
      const a = acct()!;
      const profit = Number(a.profit ?? 0);
      rows.push({
        time: t,
        type: "account",
        content: `Equity ${Number(a.equity ?? 0).toFixed(2)} · Float ${profit >= 0 ? "+" : ""}${profit.toFixed(2)}`,
        delta,
      });
    }
    return rows;
  });

  const deskCards = createMemo(() => {
    const ds = deskStatus();
    return [
      {
        name: "Fast Desk",
        color: "var(--teal)",
        cap: ds?.fast_desk?.enabled ? "live" : ("preview" as const),
        rows: [
          ["Status", ds?.fast_desk?.enabled ? "Active" : "Disabled", ds?.fast_desk?.enabled ? "var(--green)" : "var(--slate)"],
          ["Workers", String(ds?.fast_desk?.workers ?? 0), "var(--cyan-live)"],
          ["Config", ds?.fast_desk?.config ? "Available" : "Not loaded", ds?.fast_desk?.config ? "var(--green)" : "var(--amber)"],
        ] as [string, string, string][],
      },
      {
        name: "SMC Desk",
        color: "var(--blue)",
        cap: ds?.smc_desk?.enabled ? "live" : ("preview" as const),
        rows: [
          ["Status", ds?.smc_desk?.enabled ? "Active" : "Disabled", ds?.smc_desk?.enabled ? "var(--green)" : "var(--slate)"],
          ["Scanner", ds?.smc_desk?.scanner_active ? "Running" : "Stopped", ds?.smc_desk?.scanner_active ? "var(--green)" : "var(--slate)"],
          ["Config", ds?.smc_desk?.config ? "Available" : "Not loaded", ds?.smc_desk?.config ? "var(--green)" : "var(--amber)"],
        ] as [string, string, string][],
      },
      {
        name: "Risk Kernel",
        color: "var(--amber)",
        cap: "live" as const,
        rows: [
          ["Read-only signals", "Available", "var(--green)"],
          ["Governance actions", "Available via API", "var(--green)"],
          ["Kill switch", "Available", "var(--green)"],
        ] as [string, string, string][],
      },
    ];
  });

  return (
    <>
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "1fr 1fr 280px",
          "grid-template-rows": "auto auto 1fr",
          gap: "6px",
          padding: "8px 10px",
          "overflow-y": "auto",
        }}
      >
        {/* Bridge Health (cols 1–2) */}
        <div class="panel" style={{ "grid-column": "1 / 3" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--green)" }} />
              Bridge Health & Freshness
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <div style={{ display: "grid", "grid-template-columns": "repeat(5, 1fr)", gap: "6px" }}>
              <For each={healthCards()}>
                {(c) => (
                  <div class={`health-card ${c.cls}`}>
                    <div class="hl">{c.label}</div>
                    <div class={`hv ${healthValColor(c.cls)}`}>{c.val}</div>
                    <div class="hd">{c.detail}</div>
                  </div>
                )}
              </For>
            </div>
          </div>
        </div>

        {/* Active Alerts Rail (col 3, rows 1–2) */}
        <div class="panel" style={{ "grid-column": "3", "grid-row": "1 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--red)" }} />
              Active Alerts
            </div>
            <span class="cap-badge derived">Derived</span>
          </div>
          <div class="panel-body" style={{ "overflow-y": "auto", flex: "1" }}>
            <Show
              when={runtimeStore.alerts.length > 0}
              fallback={
                <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)", "padding-top": "4px" }}>
                  No active alerts
                </div>
              }
            >
              <For each={runtimeStore.alerts.slice(0, 8)}>
                {(a) => {
                  const cls = alertClass(a.severity);
                  return (
                    <div class={`alert-card ${cls}`} style={{ "margin-bottom": "6px" }}>
                      <div class={`alert-sev ${cls}`}>
                        {(a.severity ?? "UNKNOWN").toUpperCase()}
                      </div>
                      <div class="alert-msg">{a.title}</div>
                      <Show when={a.timestamp}>
                        <div class="alert-meta">
                          scope: system · {String(a.timestamp).slice(11, 19)}
                        </div>
                      </Show>
                    </div>
                  );
                }}
              </For>
            </Show>
            {/* Always-present unknown trade permission notice */}
            <div class="alert-card unknown">
              <div class="alert-sev unknown">UNKNOWN</div>
              <div class="alert-msg" style={{ color: "var(--unknown-purple)" }}>
                Trading permission not exposed by current API. Cannot confirm AutoTrading state.
              </div>
              <div class="alert-meta" style={{ color: "var(--unknown-purple)" }}>
                scope: terminal · Unknown
              </div>
            </div>
          </div>
        </div>

        {/* Subscription Footprint (col 1, row 2) */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--teal)" }} />
              Subscription Footprint
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            {(
              [
                ["Catalog Universe", `${universes()?.catalog_universe_count ?? 0} symbols`],
                ["Subscribed (chart workers)", `${universes()?.subscribed_universe?.length ?? 0}`],
                ["Subscribe / Unsubscribe", "Available"],
                [
                  "Last refresh",
                  runtimeStore.lastUpdated
                    ? new Date(runtimeStore.lastUpdated).toISOString().slice(11, 19)
                    : "—",
                ],
              ] as [string, string][]
            ).map(([k, v]) => (
              <div class="sub-row">
                <span class="k">{k}</span>
                <span class="v" style={{ color: k === "Subscribe / Unsubscribe" ? "var(--green)" : undefined }}>
                  {v}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Account Headline (col 2, row 2) */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--green)" }} />
              Account Headline
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <Show
              when={acct()}
              fallback={
                <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                  Waiting for account data…
                </div>
              }
            >
              <div class="acct-grid">
                {(
                  [
                    ["Balance", `${Number(acct()?.balance ?? 0).toFixed(2)}`],
                    ["Equity", `${Number(acct()?.equity ?? 0).toFixed(2)}`],
                    ["Margin Used", `${Number((acct() as Record<string, unknown>)?.margin as number ?? 0).toFixed(2)}`],
                    ["Free Margin", `${Number((acct() as Record<string, unknown>)?.free_margin as number ?? 0).toFixed(2)}`],
                    [
                      "Margin Level",
                      (acct() as Record<string, unknown>)?.margin_level
                        ? `${Number((acct() as Record<string, unknown>).margin_level).toFixed(0)}%`
                        : "—",
                    ],
                    [
                      "Float PnL",
                      `${Number(acct()?.profit ?? 0) >= 0 ? "+" : ""}${Number(acct()?.profit ?? 0).toFixed(2)}`,
                    ],
                  ] as [string, string][]
                ).map(([lbl, val]) => (
                  <div class="acct-field">
                    <label>{lbl}</label>
                    <div
                      class="val"
                      style={{
                        color:
                          lbl === "Equity"
                            ? "var(--green)"
                            : lbl === "Float PnL" && Number(acct()?.profit ?? 0) < 0
                            ? "var(--red)"
                            : lbl === "Float PnL"
                            ? "var(--green)"
                            : undefined,
                      }}
                    >
                      {val}
                    </div>
                  </div>
                ))}
              </div>
            </Show>
          </div>
        </div>

        {/* Feed Health (col 1, row 3) — Phase 2 */}
        <Show when={feedHealth()}>
          <div class="panel" style={{ "grid-column": "1", "grid-row": "3" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
                Feed Health
              </div>
              <span class="cap-badge live">Live</span>
            </div>
            <div class="panel-body" style={{ "overflow-y": "auto", "max-height": "200px" }}>
              <Show
                when={feedHealth()?.feed_status?.length > 0}
                fallback={
                  <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                    No feed status available
                  </div>
                }
              >
                <For each={feedHealth()?.feed_status}>
                  {(row) => (
                    <div class="sub-row" style={{ "margin-bottom": "4px" }}>
                      <span class="k">{row.symbol} {row.timeframe}</span>
                      <span class={`v ${row.bar_age_seconds < 60 ? 'text-green' : 'text-amber'}`} style={{ "font-size": "8px" }}>
                        {row.bar_age_seconds}s
                      </span>
                    </div>
                  )}
                </For>
              </Show>
            </div>
          </div>
        </Show>

        {/* Desk Status (col 2, row 3) — Phase 2 */}
        <Show when={deskStatus()}>
          <div class="panel" style={{ "grid-column": "2", "grid-row": "3" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--teal)" }} />
                Desk Status
              </div>
              <span class="cap-badge live">Live</span>
            </div>
            <div class="panel-body">
              <div class="sub-row">
                <span class="k">Fast Desk:</span>
                <span class={`v ${deskStatus()?.fast_desk?.enabled ? 'text-green' : 'text-muted'}`}>
                  {deskStatus()?.fast_desk?.enabled ? `Active (${deskStatus()?.fast_desk?.workers} workers)` : 'Disabled'}
                </span>
              </div>
              <div class="sub-row">
                <span class="k">SMC Desk:</span>
                <span class={`v ${deskStatus()?.smc_desk?.enabled ? 'text-green' : 'text-muted'}`}>
                  {deskStatus()?.smc_desk?.enabled ? 'Active' : 'Disabled'}
                </span>
              </div>
            </div>
          </div>
        </Show>

        {/* Live-State Stream (cols 1–2, row 3) */}
        <div class="panel" style={{ "grid-column": "1 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              Live-State Stream
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body" style={{ "overflow-y": "auto", flex: "1" }}>
            <div class="stream-note">
              ℹ Repeating snapshot stream from /events (SSE) — not a durable event log. Entries show latest state per refresh cycle.
            </div>
            <Show
              when={snap()}
              fallback={
                <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)", "padding-top": "4px" }}>
                  Waiting for SSE stream…
                </div>
              }
            >
              <For each={streamRows()}>
                {(row) => (
                  <div class="snapshot-row">
                    <span class="snapshot-time">{row.time}</span>
                    <span class={`snapshot-type ${row.type}`}>{row.type}</span>
                    <span class="snapshot-content">{row.content}</span>
                    <span class="snapshot-fresh">{row.delta}</span>
                  </div>
                )}
              </For>
            </Show>
          </div>
        </div>

        {/* Desk Status (col 3, row 3) */}
        <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--slate)" }} />
              Desk Status
            </div>
            <span class="cap-badge preview">Preview</span>
          </div>
          <div class="panel-body" style={{ "overflow-y": "auto", flex: "1" }}>
            <For each={deskCards()}>
              {(desk) => (
                <div class="desk-card">
                  <div class="desk-card-head">
                    <span class="desk-name" style={{ color: desk.color }}>
                      {desk.name}
                    </span>
                    <span class={`cap-badge ${desk.cap}`}>
                      {desk.cap.charAt(0).toUpperCase() + desk.cap.slice(1)}
                    </span>
                  </div>
                  <For each={desk.rows}>
                    {([k, v, vc]) => (
                      <div class="desk-row">
                        <span class="k">{k}</span>
                        <span class="v" style={{ color: vc }}>
                          {v}
                        </span>
                      </div>
                    )}
                  </For>
                </div>
              )}
            </For>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Runtime Overview</span>
        <span>Source: /status · /events (SSE) · /account · /exposure · /catalog</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default RuntimeOverview;
