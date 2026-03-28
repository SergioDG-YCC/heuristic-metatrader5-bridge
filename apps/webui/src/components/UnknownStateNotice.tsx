import type { Component } from "solid-js";

interface Props {
  label?: string;
}

export const UnknownStateNotice: Component<Props> = (props) => (
  <div
    style={{
      display: "inline-flex",
      "align-items": "center",
      gap: "5px",
      "font-size": "11px",
      color: "var(--color-caution)",
      "background-color": "rgba(245,158,11,0.08)",
      border: "1px solid rgba(245,158,11,0.25)",
      "border-radius": "var(--radius-sm)",
      padding: "2px 7px",
    }}
  >
    <span>?</span>
    <span>{props.label ?? "Unknown — not exposed by current API"}</span>
  </div>
);
