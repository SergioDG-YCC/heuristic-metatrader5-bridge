import type { Component } from "solid-js";
import { Show, For, onMount, createSignal } from "solid-js";
import { terminalStore, initTerminalStore, loadSpec } from "../stores/terminalStore";
import type { SymbolSpec } from "../types/api";

function numStr(v: unknown, dp = 5): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function deskLabel(owner: string | undefined): string {
  if (owner === "fast") return "FAST";
  if (owner === "smc") return "SMC";
  return "—";
}

function deskClass(owner: string | undefined): string {
  if (owner === "fast") return "desk-badge fast on";
  if (owner === "smc") return "desk-badge smc on";
  return "desk-badge";
}

const Terminal: Component = () => {
  onMount(() => {
    initTerminalStore();
  });

  const acct = () => terminalStore.account?.account_state;
  const [selectedSym, setSelectedSym] = createSignal<string | null>(null);

  async function handleSpecLoad(sym: string) {
    setSelectedSym(sym);
    await loadSpec(sym);
  }

  const spec = () => terminalStore.selectedSpec as SymbolSpec | null;

  return (
    <>
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "1fr 1fr",
          "grid-template-rows": "auto auto 1fr",
          gap: "6px",
          padding: "8px 10px",
          "overflow-y": "auto",
        }}
      >
        {/* Account Identity (full width) */}
        <div class="panel" style={{ "grid-column": "1 / 3" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              Account Identity
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
              <div style={{ display: "grid", "grid-template-columns": "repeat(6, 1fr)", gap: "8px" }}>
                {(
                  [
                    ["Login", String(acct()?.account_login ?? "—")],
                    ["Server", String(acct()?.broker_server ?? "—")],
                    ["Broker", String(acct()?.broker_company ?? "—")],
                    ["Currency", String(acct()?.currency ?? "—")],
                    ["Mode", String(acct()?.account_mode ?? "—")],
                    ["Leverage", acct()?.leverage ? `1:${acct()?.leverage}` : "—"],
                  ] as [string, string][]
                ).map(([lbl, val]) => (
                  <div class="acct-field">
                    <label>{lbl}</label>
                    <div class="val">{val}</div>
                  </div>
                ))}
              </div>
            </Show>
          </div>
        </div>

        {/* Account metrics (left col) */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--green)" }} />
              Account Metrics
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <div class="acct-grid">
              {(
                [
                  ["Balance", `${numStr(acct()?.balance, 2)} ${acct()?.currency ?? ""}`],
                  ["Equity", numStr(acct()?.equity, 2)],
                  ["Margin", numStr(acct()?.margin, 2)],
                  ["Free Margin", numStr(acct()?.free_margin, 2)],
                  ["Margin Level", acct()?.margin_level ? `${numStr(acct()?.margin_level, 0)}%` : "—"],
                  ["Float PnL", `${Number(acct()?.profit ?? 0) >= 0 ? "+" : ""}${numStr(acct()?.profit, 2)}`],
                ] as [string, string][]
              ).map(([lbl, val]) => (
                <div class="acct-field">
                  <label>{lbl}</label>
                  <div
                    class="val"
                    style={{
                      color:
                        lbl === "Equity" ? "var(--green)"
                        : lbl === "Float PnL" && Number(acct()?.profit ?? 0) < 0 ? "var(--red)"
                        : lbl === "Float PnL" ? "var(--green)"
                        : lbl === "Margin Level" && Number(acct()?.margin_level ?? 999) < 150 ? "var(--amber)"
                        : undefined,
                    }}
                  >
                    {val}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Trade permission (right col) */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--unknown-purple)" }} />
              Trading Permission
            </div>
            <span class="cap-badge unknown">Unknown</span>
          </div>
          <div class="panel-body">
            <div class="unknown-notice">
              <span style={{ "font-weight": "700" }}>trade_allowed</span> is not a first-class field in the current HTTP surface.
              AutoTrading on/off status cannot be confirmed. Permission is always shown as Unknown.
            </div>
            <div
              style={{
                "margin-top": "8px",
                display: "flex",
                "align-items": "center",
                gap: "6px",
                "font-family": "var(--font-mono)",
                "font-size": "10px",
              }}
            >
              <span
                style={{
                  width: "8px",
                  height: "8px",
                  "border-radius": "50%",
                  background: "var(--unknown-purple)",
                  "flex-shrink": "0",
                }}
              />
              <span style={{ color: "var(--unknown-purple)", "font-weight": "600" }}>Unknown</span>
              <span style={{ color: "var(--text-muted)" }}>— not exposed by API</span>
            </div>
          </div>
        </div>

        {/* Recent deals (full width) */}
        <div class="panel" style={{ "grid-column": "1 / 3", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--teal)" }} />
              Recent Deals
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div style={{ flex: "1", "overflow-y": "auto" }}>
            <Show
              when={(terminalStore.account?.recent_deals?.length ?? 0) > 0}
              fallback={
                <div style={{ padding: "12px", "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                  No recent deals
                </div>
              }
            >
              <table class="data-table">
                <thead>
                  <tr>
                    {["Ticket", "Desk", "Symbol", "Type", "Vol", "Price", "PnL", "Time"].map((h) => (
                      <th>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <For each={(terminalStore.account?.recent_deals ?? []) as Record<string, unknown>[]}>
                    {(deal) => {
                      const owner = terminalStore.ownershipByOrderId[deal.order_id as number]?.desk_owner;
                      return (
                        <tr>
                          <td>#{String(deal.deal_id ?? "—")}</td>
                          <td><span class={deskClass(owner)}>{deskLabel(owner)}</span></td>
                          <td class="td-sym">{String(deal.symbol ?? "—")}</td>
                          <td>{deal.entry === 0 ? "IN" : deal.entry === 1 ? "OUT" : "—"}</td>
                          <td style={{ "text-align": "right" }}>{numStr(deal.volume, 2)}</td>
                          <td style={{ "text-align": "right" }}>{numStr(deal.price)}</td>
                          <td
                            style={{ "text-align": "right" }}
                            class={deal.entry === 1 ? (Number(deal.profit ?? 0) >= 0 ? "td-pos" : "td-neg") : undefined}
                          >
                            {deal.entry === 1
                              ? `${Number(deal.profit ?? 0) >= 0 ? "+" : ""}${numStr(deal.profit, 2)}`
                              : <span style={{ color: "var(--text-muted)" }}>—</span>}
                          </td>
                          <td style={{ color: "var(--text-muted)", "font-size": "8.5px" }}>{String(deal.time ?? "—")}</td>
                        </tr>
                      );
                    }}
                  </For>
                </tbody>
              </table>
            </Show>
          </div>
        </div>

        {/* Symbol spec explorer (full width) */}
        <div class="panel" style={{ "grid-column": "1 / 3" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
              Symbol Spec Explorer
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            {/* Symbol picker */}
            <div style={{ display: "flex", "flex-wrap": "wrap", gap: "5px", "margin-bottom": "10px" }}>
              <For each={Object.keys(terminalStore.specs)}>
                {(sym) => (
                  <button
                    style={{
                      "font-family": "var(--font-mono)",
                      "font-size": "9px",
                      padding: "2px 8px",
                      "border-radius": "3px",
                      border: "1px solid",
                      cursor: "pointer",
                      background: selectedSym() === sym ? "var(--cyan-live)" : "var(--bg-elevated)",
                      color: selectedSym() === sym ? "var(--bg-base)" : "var(--cyan-live)",
                      "border-color": "var(--cyan-live)",
                    }}
                    onClick={() => handleSpecLoad(sym)}
                  >
                    {sym}
                  </button>
                )}
              </For>
              <Show when={Object.keys(terminalStore.specs).length === 0}>
                <span style={{ "font-family": "var(--font-mono)", "font-size": "9px", color: "var(--text-muted)", "font-style": "italic" }}>
                  No specs loaded. Subscribe to symbols to populate.
                </span>
              </Show>
            </div>

            {/* Spec detail */}
            <Show when={spec() && selectedSym()}>
              <div style={{ display: "grid", "grid-template-columns": "repeat(auto-fill, minmax(140px, 1fr))", gap: "6px" }}>
                {(
                  [
                    ["Symbol", String(spec()?.symbol ?? "—")],
                    ["Description", String(spec()?.description ?? "—")],
                    ["Contract Size", numStr(spec()?.contract_size)],
                    ["Tick Size", numStr(spec()?.tick_size)],
                    ["Tick Value", numStr(spec()?.tick_value)],
                    ["Min Volume", numStr(spec()?.volume_min, 2)],
                    ["Max Volume", numStr(spec()?.volume_max, 2)],
                    ["Vol Step", numStr(spec()?.volume_step, 2)],
                    ["Digits", String(spec()?.digits ?? "—")],
                    ["Spread", String(spec()?.spread_points ?? "—")],
                    ["Base", String(spec()?.currency_base ?? "—")],
                    ["Profit", String(spec()?.currency_profit ?? "—")],
                  ] as [string, string][]
                ).map(([lbl, val]) => (
                  <div class="acct-field">
                    <label>{lbl}</label>
                    <div class="val" style={{ "font-size": "10px", "word-break": "break-word" }}>{val}</div>
                  </div>
                ))}
              </div>
            </Show>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Terminal / Account Context</span>
        <span>Source: /account · /symbol_spec/:symbol</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Terminal;
