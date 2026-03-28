import type { Component } from "solid-js";
import { For } from "solid-js";
import type { AlertItem } from "../types/api";
import { SeverityBadge } from "./SeverityBadge";

interface Props {
  alerts: AlertItem[];
  emptyText?: string;
}

export const AlertList: Component<Props> = (props) => (
  <div style={{ display: "flex", "flex-direction": "column", gap: "4px" }}>
    {props.alerts.length === 0 ? (
      <div
        style={{
          padding: "12px",
          color: "var(--text-dim)",
          "font-style": "italic",
          "font-size": "12px",
          "text-align": "center",
        }}
      >
        {props.emptyText ?? "No alerts"}
      </div>
    ) : (
      <For each={props.alerts}>
        {(alert) => (
          <div
            style={{
              display: "flex",
              gap: "8px",
              "align-items": "flex-start",
              padding: "7px 10px",
              background: "var(--bg-panel)",
              border: "1px solid var(--bg-border)",
              "border-radius": "var(--radius-sm)",
              "border-left": `3px solid ${
                alert.severity === "critical"
                  ? "var(--color-danger)"
                  : alert.severity === "warning"
                  ? "var(--color-caution)"
                  : "var(--color-live)"
              }`,
            }}
          >
            <SeverityBadge severity={alert.severity} small />
            <div style={{ flex: "1", "min-width": "0" }}>
              <div
                style={{
                  "font-size": "12px",
                  color: "var(--text-primary)",
                  "font-weight": "600",
                }}
              >
                {alert.title}
              </div>
              {alert.detail && (
                <div
                  style={{
                    "font-size": "11px",
                    color: "var(--text-secondary)",
                    "margin-top": "2px",
                  }}
                >
                  {alert.detail}
                </div>
              )}
            </div>
            <div
              style={{
                "font-size": "10px",
                color: "var(--text-dim)",
                "white-space": "nowrap",
                "flex-shrink": "0",
              }}
            >
              {alert.source}
            </div>
          </div>
        )}
      </For>
    )}
  </div>
);
