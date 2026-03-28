import type { Component } from "solid-js";
import { Show } from "solid-js";
import { runtimeStore } from "../stores/runtimeStore";

function fmt(v: unknown, dp = 2): string {
  const n = Number(v);
  if (isNaN(n) || v == null) return "—";
  return n.toFixed(dp);
}

function bridgeDotClass(status: string | undefined): string {
  if (!status) return "gs-dot gs-dot-unknown";
  if (["running", "ready", "ok", "up", "connected"].includes(status)) return "gs-dot gs-dot-up live-pulse";
  if (["starting", "syncing", "reconnecting"].includes(status)) return "gs-dot gs-dot-warn";
  return "gs-dot gs-dot-down";
}

function bridgeLabel(status: string | undefined, bootState: string): string {
  if (status === "running" || status === "ready") return "Connected";
  if (status) return status;
  if (bootState === "waiting_for_control_plane") return "Waiting…";
  if (bootState === "degraded_unavailable") return "Unreachable";
  return "—";
}

export const GlobalStatusStrip: Component = () => {
  const snap = () => runtimeStore.snapshot;
  const identity = () => snap()?.broker_identity;
  const acct = () => snap()?.account_summary;
  const health = () => snap()?.health as Record<string, string> | undefined;
  const status = () => snap()?.status ?? snap()?.health?.status;

  const equity = () => Number(acct()?.equity ?? 0);
  const balance = () => Number(acct()?.balance ?? 0);
  const profit = () => equity() - balance();
  const positions = () => snap()?.open_positions?.length ?? 0;

  const lastSec = () => {
    const t = runtimeStore.lastUpdated;
    if (!t) return null;
    return Math.floor((Date.now() - new Date(t).getTime()) / 1000);
  };

  return (
    <div
      style={{
        display: "flex",
        "align-items": "center",
        gap: "5px",
        padding: "6px 14px",
        background: "var(--bg-panel)",
        "border-bottom": "1px solid var(--border-subtle)",
        "flex-shrink": "0",
        "flex-wrap": "wrap",
        "min-height": "var(--strip-height)",
      }}
    >
      {/* Bridge status chip */}
      <div class="gs-chip">
        <span class={bridgeDotClass(status())} />
        <span class="gs-k">Bridge</span>
        <span class="gs-v">{bridgeLabel(status(), runtimeStore.bootState)}</span>
      </div>

      {/* MT5 server + account */}
      <Show when={identity()?.broker_server}>
        <div class="gs-chip">
          <span class="gs-k">MT5</span>
          <span class="gs-v">{String(identity()?.broker_server ?? "").replace("ICMarkets-", "").replace("-", " ")}</span>
        </div>
      </Show>

      <Show when={identity()?.account_login}>
        <div class="gs-chip">
          <span class="gs-k">Acct</span>
          <span class="gs-v">#{String(identity()?.account_login ?? "")}</span>
        </div>
      </Show>

      {/* Feed */}
      <Show when={snap()?.universes?.subscribed_universe?.length}>
        <div class="gs-chip">
          <span class="gs-k">Feed</span>
          <span class="gs-v">{snap()?.universes?.subscribed_universe?.length} sym</span>
        </div>
      </Show>

      {/* SSE status */}
      <div class="gs-chip">
        <span class="gs-k">SSE</span>
        <span
          class="gs-v"
          style={{ color: runtimeStore.sseConnected ? "var(--cyan-live)" : "var(--amber)" }}
        >
          {runtimeStore.sseConnected ? "Streaming" : "Disconnected"}
        </span>
      </div>

      {/* Equity */}
      <Show when={acct()?.equity}>
        <div class="gs-chip">
          <span class="gs-k">Equity</span>
          <span class="gs-v" style={{ color: profit() >= 0 ? "var(--green)" : "var(--red)" }}>
            ${fmt(equity())}
          </span>
        </div>
      </Show>

      {/* Open positions */}
      <Show when={snap()}>
        <div class="gs-chip">
          <span class="gs-k">Pos</span>
          <span class="gs-v" style={{ color: positions() > 0 ? "var(--cyan-live)" : "var(--text-secondary)" }}>
            {positions()}
          </span>
        </div>
      </Show>

      {/* Trade permission */}
      <Show when={snap()?.trade_allowed !== undefined}>
        <div class="gs-chip">
          <span class={`gs-dot ${snap()?.trade_allowed ? 'gs-dot-up' : 'gs-dot-down'}`} />
          <span class="gs-k">Trade</span>
          <span class="gs-v" style={{ color: snap()?.trade_allowed ? "var(--green)" : "var(--red)" }}>
            {snap()?.trade_allowed ? "Allowed" : "Blocked"}
          </span>
        </div>
      </Show>

      {/* Spacer */}
      <div style={{ flex: "1" }} />

      {/* Freshness */}
      <span
        style={{
          "font-family": "var(--font-mono)",
          "font-size": "9px",
          color: "var(--text-muted)",
        }}
      >
        {lastSec() != null ? `fresh ${lastSec()}s ago` : "—"}
      </span>
    </div>
  );
};

