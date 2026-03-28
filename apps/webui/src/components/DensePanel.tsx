import type { Component, JSXElement } from "solid-js";

interface Props {
  title?: string;
  children: JSXElement;
  badge?: JSXElement;
  noPad?: boolean;
}

export const DensePanel: Component<Props> = (props) => (
  <section
    style={{
      background: "var(--bg-panel)",
      border: "1px solid var(--bg-border)",
      "border-radius": "var(--radius-md)",
      overflow: "hidden",
      display: "flex",
      "flex-direction": "column",
    }}
  >
    {props.title && (
      <header
        style={{
          display: "flex",
          "align-items": "center",
          "justify-content": "space-between",
          padding: "7px 12px",
          "border-bottom": "1px solid var(--bg-border)",
          "font-size": "11px",
          "text-transform": "uppercase",
          "letter-spacing": "0.07em",
          color: "var(--text-secondary)",
          "flex-shrink": "0",
        }}
      >
        <span>{props.title}</span>
        {props.badge}
      </header>
    )}
    <div style={{ padding: props.noPad ? "0" : "10px 12px", flex: "1", "overflow-y": "auto" }}>
      {props.children}
    </div>
  </section>
);
