import type { Component } from "solid-js";
import type { AlertSeverity } from "../types/api";

const COLORS: Record<AlertSeverity, string> = {
  critical: "var(--color-danger)",
  warning: "var(--color-caution)",
  info: "var(--color-live)",
};

interface Props {
  severity: AlertSeverity;
  small?: boolean;
}

export const SeverityBadge: Component<Props> = (props) => {
  const color = () => COLORS[props.severity] ?? "var(--text-secondary)";
  const label = () => props.severity.toUpperCase();

  return (
    <span
      style={{
        display: "inline-flex",
        "align-items": "center",
        gap: "4px",
        "font-size": props.small ? "10px" : "11px",
        color: color(),
        "text-transform": "uppercase",
        "letter-spacing": "0.06em",
        "font-weight": "700",
      }}
    >
      {label()}
    </span>
  );
};
