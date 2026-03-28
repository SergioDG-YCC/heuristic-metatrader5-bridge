import type { Component } from "solid-js";
import type { BootState } from "../types/api";

interface Props {
  bootState: BootState;
}

type StepStatus = "done" | "active" | "waiting" | "error";

interface Step {
  label: string;
  detail: (state: BootState) => string;
  status: (state: BootState) => StepStatus;
}

const STEPS: Step[] = [
  {
    label: "Starting WebUI",
    detail: () => "shell ready",
    status: () => "done",
  },
  {
    label: "Waiting for control plane",
    detail: () => "GET /status…",
    status: (s) =>
      s === "waiting_for_control_plane" ? "active"
        : s === "degraded_unavailable" ? "error"
        : s === "launching_ui" ? "waiting"
        : "done",
  },
  {
    label: "Synchronizing runtime state",
    detail: () => "",
    status: (s) =>
      s === "control_plane_detected_syncing" ? "active"
        : ["ready", "reconnecting"].includes(s) ? "done"
        : "waiting",
  },
  {
    label: "Establishing SSE stream",
    detail: () => "",
    status: (s) =>
      ["ready", "reconnecting"].includes(s) ? "done" : "waiting",
  },
  {
    label: "Loading account context",
    detail: () => "",
    status: (s) => s === "ready" ? "done" : "waiting",
  },
];

const BOOT_MESSAGE: Record<BootState, string> = {
  launching_ui: "Starting WebUI…",
  waiting_for_control_plane: "Waiting for control plane…",
  control_plane_detected_syncing: "Synchronizing runtime state…",
  ready: "",
  reconnecting: "Reconnecting…",
  degraded_unavailable: "Control plane unreachable",
};

function stepIcon(status: StepStatus) {
  if (status === "done")    return { icon: "✓", bg: "rgba(34,197,94,0.15)",  color: "var(--green)" };
  if (status === "active")  return { icon: "⟳", bg: "var(--cyan-dim)",         color: "var(--cyan-live)", pulse: true };
  if (status === "error")   return { icon: "✕", bg: "rgba(239,68,68,0.12)",  color: "var(--red)" };
  return { icon: "·", bg: "var(--bg-elevated)", color: "var(--text-muted)" };
}

export const BootOverlay: Component<Props> = (props) => (
  <div
    style={{
      position: "fixed",
      inset: "0",
      background: "var(--bg-base)",
      display: "flex",
      "flex-direction": "column",
      "align-items": "center",
      "justify-content": "center",
      "z-index": "9999",
    }}
  >
    <div
      style={{
        "text-align": "center",
        "max-width": "380px",
        width: "100%",
      }}
    >
      {/* Logo */}
      <div
        style={{
          "font-family": "var(--font-mono)",
          "font-size": "13px",
          "font-weight": "700",
          color: "var(--cyan-live)",
          "letter-spacing": "0.15em",
          "text-transform": "uppercase",
          "margin-bottom": "28px",
        }}
      >
        heuristic mt5 bridge
        <span
          style={{
            display: "block",
            "font-size": "10px",
            "font-weight": "400",
            color: "var(--text-muted)",
            "letter-spacing": "0.08em",
            "margin-top": "4px",
          }}
        >
          operator console · solid.js
        </span>
      </div>

      {/* Spinner */}
      <div
        style={{
          width: "36px",
          height: "36px",
          margin: "0 auto 20px",
          "border-radius": "50%",
          border: "2px solid var(--border-subtle)",
          "border-top-color": props.bootState === "degraded_unavailable"
            ? "var(--amber)"
            : "var(--cyan-live)",
          animation: "spin 1s linear infinite",
        }}
      />

      {/* Boot state message */}
      <div
        style={{
          "font-family": "var(--font-mono)",
          "font-size": "11px",
          color: props.bootState === "degraded_unavailable" ? "var(--amber)" : "var(--text-secondary)",
          "margin-bottom": "20px",
        }}
      >
        {BOOT_MESSAGE[props.bootState]}
      </div>

      {/* Step checklist */}
      <div
        style={{
          display: "flex",
          "flex-direction": "column",
          gap: "5px",
          "text-align": "left",
          padding: "14px",
          background: "var(--bg-panel)",
          border: "1px solid var(--border-subtle)",
          "border-radius": "6px",
          "margin-bottom": props.bootState === "degraded_unavailable" ? "12px" : "0",
        }}
      >
        {STEPS.map((step) => {
          const s = stepIcon(step.status(props.bootState));
          const detail = step.detail(props.bootState);
          return (
            <div
              style={{
                display: "flex",
                "align-items": "center",
                gap: "8px",
                "font-family": "var(--font-mono)",
                "font-size": "10px",
              }}
            >
              <span
                style={{
                  width: "14px",
                  height: "14px",
                  "border-radius": "3px",
                  display: "flex",
                  "align-items": "center",
                  "justify-content": "center",
                  "font-size": "8px",
                  "font-weight": "700",
                  "flex-shrink": "0",
                  background: s.bg,
                  color: s.color,
                  animation: s.pulse ? "pulse 1.5s ease infinite" : "none",
                }}
              >
                {s.icon}
              </span>
              <span
                style={{
                  color: step.status(props.bootState) === "waiting"
                    ? "var(--text-muted)"
                    : "var(--text-secondary)",
                  flex: "1",
                }}
              >
                {step.label}
              </span>
              {detail && (
                <span style={{ color: "var(--text-muted)", "font-size": "9px" }}>
                  {detail}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Unreachable warning */}
      {props.bootState === "degraded_unavailable" && (
        <div
          style={{
            padding: "8px 12px",
            background: "var(--amber-dim)",
            border: "1px solid rgba(245,166,35,0.25)",
            "border-radius": "4px",
            "font-family": "var(--font-mono)",
            "font-size": "9.5px",
            color: "var(--amber)",
            "text-align": "left",
            "line-height": "1.6",
            "margin-bottom": "12px",
          }}
        >
          ⚠ Control plane unreachable at http://127.0.0.1:8765 — retrying every 5s.
          <br />
          Verify backend:{" "}
          <code style={{ color: "var(--amber)", "font-weight": "700" }}>
            .venv\Scripts\python.exe apps/control_plane.py
          </code>
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          "margin-top": "20px",
          "font-family": "var(--font-mono)",
          "font-size": "9px",
          color: "var(--text-muted)",
        }}
      >
        apps/webui · vite proxy → http://127.0.0.1:8765
      </div>
    </div>
  </div>
);


interface Props {
  bootState: BootState;
}

const MESSAGES: Record<BootState, string> = {
  launching_ui: "Starting WebUI…",
  waiting_for_control_plane: "Waiting for control plane…",
  control_plane_detected_syncing: "Synchronizing runtime state…",
  ready: "",
  reconnecting: "Reconnecting…",
  degraded_unavailable: "Control plane unavailable",
};

