import type { Component } from "solid-js";
import { Show, For, createSignal, createResource, onMount } from "solid-js";
import { api } from "../api/client";
import type { OwnershipItem } from "../types/api";

function ageStr(secs: number | null | undefined): string {
  if (secs == null) return "—";
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h`;
}

function ownerColor(owner: string): string {
  if (owner === "fast") return "var(--teal)";
  if (owner === "smc") return "var(--cyan-live)";
  return "var(--text-muted)";
}

const Ownership: Component = () => {
  const [tab, setTab] = createSignal<"open" | "history">("open");

  const [openData, { refetch: refetchOpen }] = createResource(() => api.ownershipOpen());
  const [historyData] = createResource(() => tab() === "history" ? api.ownershipHistory() : null);

  onMount(() => void refetchOpen());

  const items = (): OwnershipItem[] =>
    (tab() === "open" ? openData()?.items : historyData()?.items) ?? [];

  const summary = () => openData()?.summary;

  return (
    <>
      <div style={{ flex: "1", padding: "8px 10px", "overflow-y": "auto", display: "flex", "flex-direction": "column", gap: "6px" }}>

        {/* Summary strip */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              Ownership Registry
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div class="panel-body">
            <Show when={summary()} fallback={
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                {openData.loading ? "Loading…" : "No ownership data"}
              </div>
            }>
              <div style={{ display: "grid", "grid-template-columns": "repeat(6, 1fr)", gap: "8px" }}>
                {([
                  ["Total", String(summary()?.total ?? 0)],
                  ["Open", String(summary()?.open ?? 0)],
                  ["History", String(summary()?.history ?? 0)],
                  ["Fast", String(summary()?.by_owner?.fast ?? 0)],
                  ["SMC", String(summary()?.by_owner?.smc ?? 0)],
                  ["Unassigned", String(summary()?.by_owner?.unassigned ?? 0)],
                ] as [string, string][]).map(([lbl, val]) => (
                  <div class="acct-field">
                    <label>{lbl}</label>
                    <div class="val">{val}</div>
                  </div>
                ))}
              </div>
              <Show when={(summary()?.reevaluation_required_open ?? 0) > 0}>
                <div style={{ "margin-top": "6px", "font-family": "var(--font-mono)", "font-size": "8.5px", color: "var(--amber)" }}>
                  ⚠ {summary()?.reevaluation_required_open} operations require reevaluation
                </div>
              </Show>
            </Show>
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ display: "flex", gap: "4px" }}>
          {(["open", "history"] as const).map((t) => (
            <button
              onClick={() => setTab(t)}
              style={{
                "font-family": "var(--font-mono)",
                "font-size": "9px",
                padding: "3px 12px",
                "border-radius": "3px",
                border: "1px solid",
                cursor: "pointer",
                background: tab() === t ? "var(--cyan-live)" : "var(--bg-elevated)",
                color: tab() === t ? "var(--bg-base)" : "var(--cyan-live)",
                "border-color": "var(--cyan-live)",
              }}
            >{t.charAt(0).toUpperCase() + t.slice(1)}</button>
          ))}
        </div>

        {/* Table */}
        <div class="panel" style={{ flex: "1", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              {tab() === "open" ? "Open Operations" : "History"}
            </div>
            <span class="cap-badge live">Live</span>
          </div>
          <div style={{ flex: "1", "overflow-y": "auto" }}>
            <Show
              when={items().length > 0}
              fallback={
                <div style={{ padding: "12px", "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                  {openData.loading || historyData.loading ? "Loading…" : "No records"}
                </div>
              }
            >
              <table class="data-table">
                <thead>
                  <tr>
                    {["ID", "Type", "Symbol", "Side", "Owner", "Status", "Lifecycle", "Age", "Reeval"].map((h) => (
                      <th>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <For each={items()}>
                    {(item) => {
                      const id = item.operation_type === "position" ? item.position_id : item.order_id;
                      const sym = String((item.metadata as Record<string, unknown>)?.symbol ?? "—");
                      const side = String((item.metadata as Record<string, unknown>)?.side ?? "—");
                      return (
                        <tr>
                          <td style={{ "font-family": "var(--font-mono)", "font-size": "8.5px" }}>
                            #{String(id ?? "—")}
                          </td>
                          <td>{item.operation_type}</td>
                          <td class="td-sym">{sym}</td>
                          <td class={side === "buy" ? "td-buy" : side === "sell" ? "td-sell" : ""}>{side.toUpperCase()}</td>
                          <td style={{ color: ownerColor(item.desk_owner), "font-weight": "600", "font-family": "var(--font-mono)", "font-size": "9px" }}>
                            {item.desk_owner}
                          </td>
                          <td style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", color: "var(--text-secondary)" }}>
                            {item.ownership_status}
                          </td>
                          <td style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", color: item.lifecycle_status === "active" ? "var(--green)" : "var(--text-muted)" }}>
                            {item.lifecycle_status}
                          </td>
                          <td style={{ "text-align": "right", "font-family": "var(--font-mono)", "font-size": "8.5px" }}>
                            {ageStr(item.age_seconds)}
                          </td>
                          <td style={{ "text-align": "center", color: item.reevaluation_required ? "var(--amber)" : "var(--text-muted)" }}>
                            {item.reevaluation_required ? "⚠" : "—"}
                          </td>
                        </tr>
                      );
                    }}
                  </For>
                </tbody>
              </table>
            </Show>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Ownership Registry</span>
        <span>Source: /ownership/open · /ownership/history</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Ownership;
