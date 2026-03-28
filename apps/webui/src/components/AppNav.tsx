import type { Component } from "solid-js";
import { A, useMatch } from "@solidjs/router";

interface NavItem {
  path: string;
  icon: string;
  title: string;
  /** accent color for active state */
  accent?: string;
  secondary?: boolean;
}

// Mockup order: Core section, Desks section, Governance section
const coreItems: NavItem[] = [
  { path: "/",           icon: "◉", title: "Runtime Overview" },
  { path: "/symbols",    icon: "⊕", title: "Symbol Catalog" },
  { path: "/operations", icon: "☰", title: "Operations Console" },
  { path: "/terminal",   icon: "⊡", title: "Terminal / Account" },
  { path: "/alerts",     icon: "⚑", title: "Alerts / Events", accent: "var(--red)" },
];

const deskItems: NavItem[] = [
  { path: "/fast",          icon: "⚡", title: "Fast Desk", accent: "var(--teal)" },
  { path: "/fast/pipeline", icon: "▸", title: "Pipeline",  accent: "var(--teal)" },
  { path: "/smc",           icon: "◆", title: "SMC Desk",  accent: "var(--blue)" },
  { path: "/risk",          icon: "⊘", title: "Risk Center", accent: "var(--amber)" },
];

const govItems: NavItem[] = [
  { path: "/ownership", icon: "⊞", title: "Ownership (Preview)", secondary: true },
  { path: "/mode",      icon: "⇄", title: "Live / Paper (Planned)", secondary: true },
  { path: "/settings",  icon: "⚙", title: "Settings", secondary: true },
];

function NavIcon(props: NavItem) {
  const isEnd = props.path === "/";
  const match = useMatch(() => isEnd ? "/" : `${props.path}/*`);
  const isActive = () => match() != null;
  const accent = () => props.accent ?? "var(--cyan-live)";
  const bgActive = () => {
    const a = props.accent;
    if (a === "var(--red)")   return "var(--red-dim)";
    if (a === "var(--teal)")  return "var(--teal-dim)";
    if (a === "var(--blue)")  return "var(--blue-dim)";
    if (a === "var(--amber)") return "var(--amber-dim)";
    return "var(--cyan-dim)";
  };

  return (
    <A
      href={props.path}
      end={isEnd}
      title={props.title}
      style={{
        width: "34px",
        height: "34px",
        display: "flex",
        "align-items": "center",
        "justify-content": "center",
        "border-radius": "4px",
        color: isActive() ? accent() : "var(--text-muted)",
        background: isActive() ? bgActive() : "transparent",
        cursor: "pointer",
        "font-size": "12px",
        position: "relative",
        "text-decoration": "none",
        opacity: props.secondary ? "0.5" : "1",
        "flex-shrink": "0",
      }}
      onMouseEnter={(e) => {
        if (!isActive())
          (e.currentTarget as HTMLAnchorElement).style.background = "var(--bg-elevated)";
      }}
      onMouseLeave={(e) => {
        if (!isActive())
          (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
      }}
    >
      {/* Left accent bar when active */}
      {isActive() && (
        <span
          style={{
            position: "absolute",
            left: "-7px",
            width: "3px",
            height: "16px",
            background: accent(),
            "border-radius": "0 2px 2px 0",
          }}
        />
      )}
      {props.icon}
    </A>
  );
}

function SectionLabel(props: { label: string }) {
  return (
    <div
      style={{
        "font-family": "var(--font-mono)",
        "font-size": "7px",
        color: "var(--text-muted)",
        "text-transform": "uppercase",
        "letter-spacing": "0.08em",
        "margin-top": "6px",
        "margin-bottom": "2px",
        "text-align": "center",
        "line-height": "1",
      }}
    >
      {props.label}
    </div>
  );
}

function NavSep() {
  return (
    <div
      style={{
        width: "24px",
        height: "1px",
        background: "var(--border-subtle)",
        margin: "4px 0",
      }}
    />
  );
}

export const AppNav: Component = () => (
  <nav
    style={{
      width: "var(--nav-width)",
      "flex-shrink": "0",
      background: "var(--bg-panel)",
      "border-right": "1px solid var(--border-subtle)",
      display: "flex",
      "flex-direction": "column",
      "align-items": "center",
      padding: "10px 0",
      gap: "2px",
      "overflow-y": "auto",
    }}
  >
    {/* Brand monogram */}
    <div
      style={{
        "font-family": "var(--font-mono)",
        "font-size": "10px",
        "font-weight": "700",
        color: "var(--cyan-live)",
        "margin-bottom": "10px",
        "letter-spacing": "0.05em",
      }}
    >
      HB
    </div>

    <SectionLabel label="Core" />
    {coreItems.map((item) => <NavIcon {...item} />)}

    <NavSep />

    <SectionLabel label="Desks" />
    {deskItems.map((item) => <NavIcon {...item} />)}

    <NavSep />

    <SectionLabel label="Gov" />
    {govItems.map((item) => <NavIcon {...item} />)}

    {/* Spacer pushes everything to top */}
    <div style={{ flex: "1" }} />
  </nav>
);

