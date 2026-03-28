import type { Component } from "solid-js";
import type { CapabilityState } from "../types/api";

const COLORS: Record<CapabilityState, string> = {
  Live: "var(--color-live)",
  Derived: "var(--color-live)",
  Partial: "var(--color-caution)",
  Preview: "var(--color-preview)",
  Planned: "var(--text-dim)",
  Unknown: "var(--color-caution)",
  Disabled: "var(--text-dim)",
};

interface Props {
  state: CapabilityState;
  small?: boolean;
}

export const CapabilityBadge: Component<Props> = (props) => {
  const color = () => COLORS[props.state] ?? "var(--text-dim)";
  const size = () => (props.small ? "10px" : "11px");

  return (
    <span
      style={{
        display: "inline-flex",
        "align-items": "center",
        gap: "4px",
        "font-size": size(),
        color: color(),
        "text-transform": "uppercase",
        "letter-spacing": "0.06em",
        "font-weight": "600",
        "white-space": "nowrap",
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          "border-radius": "50%",
          background: color(),
          "flex-shrink": "0",
        }}
      />
      {props.state}
    </span>
  );
};
