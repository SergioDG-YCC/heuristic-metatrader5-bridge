import type { Component } from "solid-js";

interface Props {
  updatedAt: string | null;
  sseConnected: boolean;
}

function ageLabel(updatedAt: string | null): string {
  if (!updatedAt) return "—";
  const diffMs = Date.now() - new Date(updatedAt).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  return `${diffMin}m ago`;
}

function isStale(updatedAt: string | null): boolean {
  if (!updatedAt) return true;
  return Date.now() - new Date(updatedAt).getTime() > 15_000;
}

export const FreshnessBadge: Component<Props> = (props) => {
  const stale = () => isStale(props.updatedAt);
  const color = () =>
    stale() ? "var(--color-caution)" : props.sseConnected ? "var(--color-live)" : "var(--text-secondary)";

  return (
    <span
      style={{
        display: "inline-flex",
        "align-items": "center",
        gap: "4px",
        "font-size": "11px",
        color: color(),
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
          animation: props.sseConnected && !stale() ? "pulse 2s infinite" : "none",
        }}
      />
      {ageLabel(props.updatedAt)}
    </span>
  );
};
