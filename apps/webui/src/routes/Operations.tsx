import type { Component } from "solid-js";
import { Show, For, onMount } from "solid-js";
import { operationsStore, initOperationsStore } from "../stores/operationsStore";
import type { PositionRow, OrderRow, RecentDeal } from "../types/api";

function numStr(v: unknown, dp = 5): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function typeLabel(v: unknown): string {
  const s = String(v ?? "").toLowerCase();
  if (s.startsWith("buy")) return s.replace(/_/g, " ").toUpperCase();
  if (s.startsWith("sell")) return s.replace(/_/g, " ").toUpperCase();
  return String(v ?? "—");
}

function isBuyType(v: unknown): boolean {
  return String(v ?? "").toLowerCase().startsWith("buy");
}

const Operations: Component = () => {
  onMount(() => {
    initOperationsStore();
  });

  const acct = () => operationsStore.account;
  const exp = () => operationsStore.exposure;
  const positions = () => operationsStore.positions as PositionRow[];
  const orders = () => operationsStore.orders as OrderRow[];
  const recentDeals = () => (acct()?.recent_deals ?? []) as RecentDeal[];

  // Normalise gross volume to percentage for the exposure bar (capped at 100%)
  const maxExpVol = () => {
    const syms = exp()?.symbols ?? [];
    return syms.reduce((mx, r) => Math.max(mx, Math.abs(Number(r.gross_volume ?? 0))), 0) || 1;
  };

  return (
    <>
      {/* 2-column grid: main left, exposure rail right */}
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "1fr 260px",
          "grid-template-rows": "1fr auto",
          gap: "6px",
          padding: "8px 10px",
          overflow: "hidden",
        }}
      >
        {/* Left column — positions + orders + broker activity */}
        <div style={{ display: "flex", "flex-direction": "column", gap: "6px", "overflow-y": "auto" }}>

          {/* Positions + Orders panel */}
          <div class="panel" style={{ "flex-shrink": "0" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--green)" }} />
                Positions & Orders
              </div>
              <div style={{ display: "flex", gap: "6px", "align-items": "center" }}>
                <span class="cap-badge live">Live</span>
                <span style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                  /positions · /orders
                </span>
              </div>
            </div>
            <div style={{ "overflow-x": "auto" }}>
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
                        <td colspan="9" style={{ "text-align": "center", color: "var(--text-muted)", padding: "12px" }}>
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
                          <td style={{ "text-align": "right" }} class={Number(p.profit ?? 0) >= 0 ? "td-pos" : "td-neg"}>
                            {Number(p.profit ?? 0) >= 0 ? "+" : ""}{numStr(p.profit, 2)}
                          </td>
                        </tr>
                      )}
                    </For>
                  </Show>
                </tbody>
              </table>

              <div
                style={{
                  padding: "3px 8px",
                  "border-top": "1px solid var(--border-subtle)",
                  "font-family": "var(--font-mono)",
                  "font-size": "8px",
                  color: "var(--text-muted)",
                  "text-transform": "uppercase",
                  "letter-spacing": "0.06em",
                }}
              >
                Pending Orders
              </div>

              <table class="data-table">
                <thead>
                  <tr>
                    {["Ticket", "Symbol", "Type", "Vol", "Price", "SL", "TP", "Comment"].map((h) => (
                      <th>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <Show
                    when={orders().length > 0}
                    fallback={
                      <tr>
                        <td colspan="8" style={{ "text-align": "center", color: "var(--text-muted)", padding: "10px" }}>
                          No pending orders
                        </td>
                      </tr>
                    }
                  >
                    <For each={orders()}>
                      {(o) => (
                        <tr>
                          <td>#{String(o.order_id ?? "—")}</td>
                          <td class="td-sym">{String(o.symbol ?? "—")}</td>
                          <td class={isBuyType(o.order_type) ? "td-buy" : "td-sell"}>{typeLabel(o.order_type)}</td>
                          <td style={{ "text-align": "right" }}>{numStr(o.volume_initial, 2)}</td>
                          <td style={{ "text-align": "right" }}>{numStr(o.price_open)}</td>
                          <td style={{ "text-align": "right", color: "var(--text-muted)" }}>{numStr(o.stop_loss)}</td>
                          <td style={{ "text-align": "right", color: "var(--text-muted)" }}>{numStr(o.take_profit)}</td>
                          <td style={{ color: "var(--text-muted)", "font-size": "8.5px" }}>{String(o.comment ?? "—")}</td>
                        </tr>
                      )}
                    </For>
                  </Show>
                </tbody>
              </table>
            </div>
          </div>

          {/* Broker activity */}
          <div class="panel" style={{ "flex-shrink": "0" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
                Recent Broker Activity
              </div>
              <div style={{ display: "flex", gap: "6px", "align-items": "center" }}>
                <span class="cap-badge live">Live</span>
                <span style={{ "font-family": "var(--font-mono)", "font-size": "8px", color: "var(--text-muted)" }}>
                  /account → recent_deals
                </span>
              </div>
            </div>
            <div class="panel-body">
              <Show
                when={recentDeals().length > 0}
                fallback={
                  <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                    No recent deal history
                  </div>
                }
              >
                <For each={recentDeals().slice(0, 15)}>
                  {(deal) => (
                    <div class="broker-tl-entry">
                      <span class="broker-tl-time">{String(deal.time ?? "—").slice(11, 19)}</span>
                      <span class="broker-tl-type deal">Deal</span>
                      <span class="broker-tl-detail">
                        #{String(deal.deal_id ?? "—")} {String(deal.symbol ?? "—")}{" "}
                        {numStr(deal.volume, 2)} @ {numStr(deal.price)} · P&L{" "}
                        <span style={{ color: Number(deal.profit ?? 0) >= 0 ? "var(--green)" : "var(--red)", "font-weight": "600" }}>
                          {Number(deal.profit ?? 0) >= 0 ? "+" : ""}{numStr(deal.profit, 2)}
                        </span>
                      </span>
                    </div>
                  )}
                </For>
              </Show>
            </div>
          </div>

          {/* Disabled action notice */}
          <div class="no-write-notice">
            Trade actions (open / close / modify / remove) require HTTP write endpoints not yet exposed by the
            control plane. This lane activates when action endpoints are added.
          </div>
        </div>

        {/* Right column — exposure matrix */}
        <div class="panel" style={{ overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--amber)" }} />
              Exposure Matrix
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
                  const gross = Number(row.gross_volume ?? 0);
                  const pct = Math.min(Math.abs(gross) / maxExpVol() * 45, 45);
                  const isLong = net >= 0;
                  return (
                    <div class="exp-row">
                      <span class="exp-sym">{String(row.symbol ?? "—")}</span>
                      <div class="exp-track">
                        <div class="exp-center" />
                        <Show when={isLong}>
                          <div class="exp-bar-long" style={{ width: `${pct}%` }} />
                        </Show>
                        <Show when={!isLong}>
                          <div class="exp-bar-short" style={{ width: `${pct}%` }} />
                        </Show>
                      </div>
                      <span class="exp-val" style={{ color: isLong ? "var(--green)" : "var(--red)" }}>
                        {isLong ? "+" : ""}{numStr(net, 2)}
                      </span>
                    </div>
                  );
                }}
              </For>
            </Show>

            {/* Account summary band */}
            <Show when={exp()}>
              <div
                style={{
                  "margin-top": "10px",
                  "padding-top": "8px",
                  "border-top": "1px solid var(--border-subtle)",
                  display: "flex",
                  "flex-direction": "column",
                  gap: "4px",
                }}
              >
                {(
                  [
                    ["Float PnL", `${Number(exp()?.floating_profit ?? 0) >= 0 ? "+" : ""}${numStr(exp()?.floating_profit, 2)}`],
                    ["Gross Exposure", numStr(exp()?.gross_exposure, 2)],
                    ["Net Exposure", numStr(exp()?.net_exposure, 2)],
                  ] as [string, string][]
                ).map(([k, v]) => (
                  <div class="sub-row">
                    <span class="k">{k}</span>
                    <span class="v" style={{ color: k === "Float PnL" && Number(exp()?.floating_pnl ?? 0) < 0 ? "var(--red)" : k === "Float PnL" ? "var(--green)" : undefined }}>
                      {v}
                    </span>
                  </div>
                ))}
              </div>
            </Show>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Operations Console</span>
        <span>Source: /positions · /orders · /exposure · /account (recent_deals)</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Operations;
