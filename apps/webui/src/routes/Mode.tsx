import type { Component } from "solid-js";
import { runtimeStore } from "../stores/runtimeStore";

const Mode: Component = () => {
  const acct = () => runtimeStore.snapshot?.account_summary;

  return (
    <>
      <div style={{ flex: "1", padding: "8px 10px", "overflow-y": "auto", display: "flex", "flex-direction": "column", gap: "6px" }}>

        {/* MT5 Account Mode panel */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--blue)" }} />
              MT5 Account Mode
            </div>
            <span class="cap-badge partial">Partial</span>
          </div>
          <div class="panel-body">
            <div
              style={{
                display: "flex",
                "align-items": "center",
                gap: "10px",
                "margin-bottom": "8px",
              }}
            >
              <span
                style={{
                  "font-family": "var(--font-mono)",
                  "font-size": "14px",
                  "font-weight": "700",
                  color: "var(--text-primary)",
                }}
              >
                {(acct() as Record<string,unknown>)?.account_mode as string
                  ?? "—"}
              </span>
              <span class="cap-badge partial">Partial</span>
            </div>
            <div style={{ "font-size": "10px", color: "var(--text-muted)", "font-family": "var(--font-mono)", "line-height": "1.5" }}>
              Reflects the MT5 account's trade_mode field. Not the same as the product's Live/Paper execution mode concept.
            </div>
          </div>
        </div>

        {/* Product execution mode */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--unknown-purple)" }} />
              Product Execution Mode
            </div>
            <span class="cap-badge unknown">Unknown</span>
          </div>
          <div class="panel-body">
            <div class="unknown-notice">
              Not exposed by the current control plane — cannot confirm Live vs Paper via current API. The MT5 account_mode_guard config exists internally but is not surfaced as a clean HTTP field.
            </div>
          </div>
        </div>

        {/* Warning */}
        <div class="no-write-notice">
          ⚠ Do not equate MT5 account_mode with the product's Live/Paper execution mode. These are distinct concepts. Account switching is a dangerous operation and is not available here.
        </div>

        {/* Planned switch */}
        <div class="preview-box">
          <div class="pb-title">
            <span class="cap-badge planned">Planned</span>
            Live / Paper Switch
          </div>
          <div class="pb-desc">
            When the backend exposes an explicit execution mode API, a controlled switch workflow will appear here with operator warnings and confirmation steps.
            <br />• Current mode state (explicit) · Controlled switch · Operator risk warnings · Mode transition audit trail
          </div>
        </div>

      </div>

      <div class="footer-bar">
        <span>heuristic-mt5-bridge · Live / Paper Mode</span>
        <span>Planned — execution mode API not yet available</span>
        <span>Solid.js · v1</span>
      </div>
    </>
  );
};

export default Mode;
