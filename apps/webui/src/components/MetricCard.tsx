import type { Component, JSXElement } from "solid-js";

interface Props {
  label: string;
  value: JSXElement;
  sub?: string;
  color?: string;
  cap?: string; // capability label shown in corner
}

export const MetricCard: Component<Props> = (props) => (
  <div
    style={{
      background: "var(--bg-panel)",
      border: "1px solid var(--bg-border)",
      "border-radius": "var(--radius-md)",
      padding: "10px 14px",
      display: "flex",
      "flex-direction": "column",
      gap: "2px",
      "min-width": "120px",
    }}
  >
    <div
      style={{
        "font-size": "10px",
        color: "var(--text-secondary)",
        "text-transform": "uppercase",
        "letter-spacing": "0.07em",
        display: "flex",
        "justify-content": "space-between",
      }}
    >
      <span>{props.label}</span>
      {props.cap && (
        <span style={{ color: "var(--text-dim)" }}>{props.cap}</span>
      )}
    </div>
    <div
      style={{
        "font-size": "18px",
        "font-weight": "700",
        color: props.color ?? "var(--text-primary)",
        "font-variant-numeric": "tabular-nums",
        "line-height": "1.2",
      }}
    >
      {props.value}
    </div>
    {props.sub && (
      <div style={{ "font-size": "10px", color: "var(--text-dim)" }}>
        {props.sub}
      </div>
    )}
  </div>
);
