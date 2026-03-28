import type { Component } from "solid-js";

interface Props {
  reason?: string;
}

export const DisabledActionLane: Component<Props> = (props) => (
  <div
    style={{
      padding: "16px",
      "text-align": "center",
      border: "1px dashed var(--bg-border)",
      "border-radius": "var(--radius-md)",
      color: "var(--text-dim)",
      "font-size": "12px",
    }}
  >
    <div
      style={{
        "font-size": "11px",
        "text-transform": "uppercase",
        "letter-spacing": "0.07em",
        "margin-bottom": "4px",
        color: "var(--text-dim)",
        "font-weight": "600",
      }}
    >
      Disabled
    </div>
    <div>
      {props.reason ??
        "Action endpoints are not exposed by the current control plane."}
    </div>
  </div>
);
