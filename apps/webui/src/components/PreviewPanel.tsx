import type { Component, JSXElement } from "solid-js";
import type { CapabilityState } from "../types/api";
import { CapabilityBadge } from "./CapabilityBadge";

interface Props {
  capability: CapabilityState;
  title: string;
  description?: string;
  children?: JSXElement;
}

export const PreviewPanel: Component<Props> = (props) => (
  <section
    style={{
      background: "var(--bg-panel)",
      border: `1px dashed ${
        props.capability === "Preview"
          ? "var(--color-preview)"
          : "var(--bg-border)"
      }`,
      "border-radius": "var(--radius-md)",
      padding: "16px",
      display: "flex",
      "flex-direction": "column",
      gap: "8px",
      opacity: "0.8",
    }}
  >
    <div
      style={{
        display: "flex",
        "align-items": "center",
        "justify-content": "space-between",
      }}
    >
      <span
        style={{
          "font-size": "13px",
          "font-weight": "600",
          color: "var(--text-primary)",
        }}
      >
        {props.title}
      </span>
      <CapabilityBadge state={props.capability} small />
    </div>
    {props.description && (
      <p style={{ "font-size": "12px", color: "var(--text-secondary)" }}>
        {props.description}
      </p>
    )}
    {props.children}
  </section>
);
