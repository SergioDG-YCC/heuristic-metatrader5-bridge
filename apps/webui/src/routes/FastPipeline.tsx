import { createSignal, onMount, onCleanup, For, Show } from "solid-js";
import type { Component } from "solid-js";
import { api } from "../api/client";
import type {
  PipelineTrace,
  PipelineStageResult,
  PipelineSSEPayload,
} from "../types/api";

// ── Canonical stage order ────────────────────────────────────────────────────
const STAGE_ORDER = [
  "context",
  "setup",
  "cooldown",
  "risk_gate",
  "account_safe",
  "trigger",
  "entry_policy",
  "execution",
] as const;

const STAGE_LABELS: Record<string, string> = {
  context: "Stage 1 · Context",
  setup: "Stage 2 · Setup",
  cooldown: "Stage 3 · Cooldown",
  risk_gate: "Stage 4 · Risk Gate",
  account_safe: "Stage 5 · Account Safe",
  trigger: "Stage 6 · Trigger",
  entry_policy: "Stage 7 · Entry Policy",
  execution: "Stage 8 · Execution",
};

const MAX_TRACES = 120;

// ── Helpers ──────────────────────────────────────────────────────────────────
function sideColor(trace: PipelineTrace): string {
  const exec = trace.stages.find((s) => s.name === "execution");
  const trig = trace.stages.find((s) => s.name === "trigger");
  const side =
    String(exec?.details?.side ?? trig?.details?.side ?? "").toLowerCase();
  if (side === "buy") return "var(--green)";
  if (side === "sell") return "var(--red)";
  return "var(--text-muted)";
}

function sideBg(trace: PipelineTrace): string {
  const exec = trace.stages.find((s) => s.name === "execution");
  const trig = trace.stages.find((s) => s.name === "trigger");
  const side =
    String(exec?.details?.side ?? trig?.details?.side ?? "").toLowerCase();
  if (side === "buy") return "rgba(34,197,94,0.12)";
  if (side === "sell") return "rgba(239,68,68,0.12)";
  return "rgba(100,116,139,0.08)";
}

function stageStatus(
  trace: PipelineTrace,
  stageName: string
): "passed" | "rejected" | "pending" {
  const idx = STAGE_ORDER.indexOf(stageName as any);
  const finalIdx = STAGE_ORDER.indexOf(trace.final_gate as any);
  if (idx > finalIdx) return "pending";
  const stage = trace.stages.find((s) => s.name === stageName);
  if (!stage) return "pending";
  return stage.passed ? "passed" : "rejected";
}

function statusDot(status: "passed" | "rejected" | "pending"): string {
  if (status === "passed") return "var(--green)";
  if (status === "rejected") return "var(--red)";
  return "var(--text-muted)";
}

function statusBg(status: "passed" | "rejected" | "pending"): string {
  if (status === "passed") return "rgba(34,197,94,0.10)";
  if (status === "rejected") return "rgba(239,68,68,0.10)";
  return "rgba(100,116,139,0.06)";
}

function timeShort(ts: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toISOString().slice(11, 19) + "Z";
}

function detailLine(details: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(details)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) {
      parts.push(`${k}: [${v.join(", ")}]`);
    } else if (typeof v === "object") {
      parts.push(`${k}: {…}`);
    } else {
      parts.push(`${k}: ${v}`);
    }
  }
  return parts.join(" · ");
}

// ── Component ────────────────────────────────────────────────────────────────
const FastPipeline: Component = () => {
  const [traces, setTraces] = createSignal<PipelineTrace[]>([]);
  const [selected, setSelected] = createSignal<string | null>(null);
  const [cursor, setCursor] = createSignal(0);
  const [connected, setConnected] = createSignal(false);

  let sseSource: EventSource | null = null;

  // Initial REST load
  onMount(async () => {
    try {
      const snap = await api.fastPipeline(MAX_TRACES);
      setTraces(snap.traces);
      setCursor(snap.cursor);
    } catch {
      // will retry via SSE
    }
    startSSE();
  });

  onCleanup(() => {
    if (sseSource) {
      sseSource.close();
      sseSource = null;
    }
  });

  function startSSE() {
    sseSource = new EventSource("/events/fast/pipeline?interval=1");
    sseSource.onopen = () => setConnected(true);
    sseSource.onerror = () => setConnected(false);
    sseSource.onmessage = (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data as string) as PipelineSSEPayload;
        if (payload.traces.length > 0) {
          setTraces((prev) => {
            const merged = [...payload.traces, ...prev];
            return merged.slice(0, MAX_TRACES);
          });
        }
        setCursor(payload.cursor);
      } catch {
        // malformed — skip
      }
    };
  }

  // Derived: last accepted trace
  const lastAccepted = () =>
    traces().find((t) => t.final_passed);

  // Derived: selected trace object
  const selectedTrace = () =>
    traces().find((t) => t.trace_id === selected());

  // Traces grouped by symbol for display
  const tracesBySymbol = () => {
    const map = new Map<string, PipelineTrace[]>();
    for (const t of traces()) {
      const arr = map.get(t.symbol) ?? [];
      arr.push(t);
      map.set(t.symbol, arr);
    }
    return map;
  };

  // Get unique operations (most recent per symbol)
  const latestPerSymbol = () => {
    const map = new Map<string, PipelineTrace>();
    for (const t of traces()) {
      if (!map.has(t.symbol)) map.set(t.symbol, t);
    }
    return [...map.values()];
  };

  return (
    <div
      style={{
        flex: "1",
        display: "flex",
        "flex-direction": "column",
        overflow: "hidden",
        padding: "8px 10px",
        gap: "6px",
      }}
    >
      {/* ── Top Status Bar ── */}
      <div
        style={{
          display: "flex",
          gap: "6px",
          "flex-shrink": "0",
        }}
      >
        {/* Left: Last Accepted */}
        <div
          class="panel"
          style={{ flex: "1", overflow: "hidden" }}
        >
          <div class="panel-head">
            <span class="panel-title">
              <span
                class="panel-dot"
                style={{ background: "var(--green)" }}
              />
              Last Accepted Operation
            </span>
            <Show when={connected()}>
              <span
                style={{
                  "font-size": "7px",
                  color: "var(--green)",
                  "font-family": "var(--font-mono)",
                }}
              >
                ● LIVE
              </span>
            </Show>
          </div>
          <div class="panel-body">
            <Show
              when={lastAccepted()}
              fallback={
                <span
                  style={{
                    "font-size": "9px",
                    color: "var(--text-muted)",
                    "font-family": "var(--font-mono)",
                  }}
                >
                  No accepted operations yet
                </span>
              }
            >
              {(t) => <TraceCard trace={t()} compact />}
            </Show>
          </div>
        </div>

        {/* Right: Selected Details */}
        <div
          class="panel"
          style={{ flex: "1", overflow: "hidden" }}
        >
          <div class="panel-head">
            <span class="panel-title">
              <span
                class="panel-dot"
                style={{ background: "var(--cyan-live)" }}
              />
              Selected Operation Details
            </span>
          </div>
          <div class="panel-body">
            <Show
              when={selectedTrace()}
              fallback={
                <span
                  style={{
                    "font-size": "9px",
                    color: "var(--text-muted)",
                    "font-family": "var(--font-mono)",
                  }}
                >
                  Click an operation to view details
                </span>
              }
            >
              {(t) => <TraceDetail trace={t()} />}
            </Show>
          </div>
        </div>
      </div>

      {/* ── 8-Stage Pipeline Grid ── */}
      <div
        style={{
          flex: "1",
          display: "grid",
          "grid-template-columns": "repeat(8, minmax(0, 1fr))",
          gap: "4px",
          "overflow-y": "auto",
          "min-height": "0",
        }}
      >
        <For each={[...STAGE_ORDER]}>
          {(stageName) => (
            <div
              class="panel"
              style={{
                display: "flex",
                "flex-direction": "column",
                overflow: "hidden",
              }}
            >
              <div
                class="panel-head"
                style={{ "justify-content": "center" }}
              >
                <span
                  class="panel-title"
                  style={{ "font-size": "8px" }}
                >
                  {STAGE_LABELS[stageName]}
                </span>
              </div>
              <div
                style={{
                  flex: "1",
                  "overflow-y": "auto",
                  padding: "4px",
                  display: "flex",
                  "flex-direction": "column",
                  gap: "3px",
                }}
              >
                <For each={latestPerSymbol()}>
                  {(trace) => {
                    const status = () => stageStatus(trace, stageName);
                    const isSelected = () => selected() === trace.trace_id;
                    const isOtherSelected = () =>
                      selected() !== null && selected() !== trace.trace_id;
                    const stageData = () =>
                      trace.stages.find((s) => s.name === stageName);

                    return (
                      <div
                        onClick={() =>
                          setSelected((prev) =>
                            prev === trace.trace_id ? null : trace.trace_id
                          )
                        }
                        style={{
                          position: "relative",
                          background: isSelected()
                            ? sideBg(trace)
                            : "var(--bg-elevated)",
                          border: isSelected()
                            ? `1px solid ${sideColor(trace)}`
                            : "1px solid var(--border-subtle)",
                          "border-radius": "4px",
                          padding: "5px 6px",
                          cursor: "pointer",
                          opacity: isOtherSelected() ? "0.35" : "1",
                          transition: "opacity 0.15s, border-color 0.15s",
                        }}
                      >
                        {/* Left color bar */}
                        <div
                          style={{
                            position: "absolute",
                            left: "0",
                            top: "0",
                            bottom: "0",
                            width: "2px",
                            background: statusDot(status()),
                            "border-radius": "4px 0 0 4px",
                            opacity: "0.85",
                          }}
                        />
                        {/* Symbol + status dot */}
                        <div
                          style={{
                            display: "flex",
                            "align-items": "center",
                            gap: "4px",
                            "margin-bottom": "2px",
                          }}
                        >
                          <span
                            style={{
                              width: "5px",
                              height: "5px",
                              "border-radius": "50%",
                              background: statusDot(status()),
                              "flex-shrink": "0",
                              "box-shadow": status() === "passed"
                                ? `0 0 4px ${statusDot(status())}`
                                : status() === "rejected"
                                ? `0 0 4px ${statusDot(status())}`
                                : "none",
                            }}
                          />
                          <span
                            style={{
                              "font-family": "var(--font-mono)",
                              "font-size": "8.5px",
                              "font-weight": "600",
                              color: "var(--text-primary)",
                            }}
                          >
                            {trace.symbol}
                          </span>
                          <span
                            style={{
                              "font-family": "var(--font-mono)",
                              "font-size": "7px",
                              "font-weight": "600",
                              padding: "0 3px",
                              "border-radius": "2px",
                              background: sideBg(trace),
                              color: sideColor(trace),
                              "margin-left": "auto",
                            }}
                          >
                            {String(
                              trace.stages.find(
                                (s) => s.name === "trigger" || s.name === "execution"
                              )?.details?.side ?? ""
                            ).toUpperCase() || "—"}
                          </span>
                        </div>
                        {/* Stage detail line */}
                        <Show when={stageData() && status() !== "pending"}>
                          <div
                            style={{
                              "font-family": "var(--font-mono)",
                              "font-size": "7px",
                              color:
                                status() === "rejected"
                                  ? "var(--red)"
                                  : "var(--text-muted)",
                              "white-space": "nowrap",
                              overflow: "hidden",
                              "text-overflow": "ellipsis",
                              "max-width": "100%",
                            }}
                            title={detailLine(stageData()!.details)}
                          >
                            {detailLine(stageData()!.details).slice(0, 50) ||
                              (status() === "passed" ? "✓ passed" : "✗ blocked")}
                          </div>
                        </Show>
                        <Show when={status() === "pending"}>
                          <div
                            style={{
                              "font-family": "var(--font-mono)",
                              "font-size": "7px",
                              color: "var(--text-muted)",
                              opacity: "0.5",
                            }}
                          >
                            — pending
                          </div>
                        </Show>
                      </div>
                    );
                  }}
                </For>
              </div>
            </div>
          )}
        </For>
      </div>

      {/* ── Recent Traces Table ── */}
      <div
        class="panel"
        style={{
          "max-height": "180px",
          overflow: "hidden",
          display: "flex",
          "flex-direction": "column",
          "flex-shrink": "0",
        }}
      >
        <div class="panel-head">
          <span class="panel-title">
            <span
              class="panel-dot"
              style={{ background: "var(--teal)" }}
            />
            Recent Pipeline Traces
          </span>
          <span
            style={{
              "font-family": "var(--font-mono)",
              "font-size": "8px",
              color: "var(--text-muted)",
            }}
          >
            {traces().length} traces
          </span>
        </div>
        <div style={{ flex: "1", "overflow-y": "auto" }}>
          <table class="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Final Gate</th>
                <th>Status</th>
                <th>Stages</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              <For each={traces().slice(0, 60)}>
                {(t) => (
                  <tr
                    onClick={() =>
                      setSelected((prev) =>
                        prev === t.trace_id ? null : t.trace_id
                      )
                    }
                    style={{
                      cursor: "pointer",
                      background:
                        selected() === t.trace_id
                          ? "rgba(34,211,238,0.06)"
                          : "transparent",
                    }}
                  >
                    <td>{timeShort(t.timestamp)}</td>
                    <td class="td-sym">{t.symbol}</td>
                    <td>{t.final_gate}</td>
                    <td
                      style={{
                        color: t.final_passed
                          ? "var(--green)"
                          : "var(--red)",
                        "font-weight": "600",
                      }}
                    >
                      {t.final_passed ? "PASS" : "BLOCK"}
                    </td>
                    <td>
                      <StageDots trace={t} />
                    </td>
                    <td
                      style={{
                        "max-width": "280px",
                        overflow: "hidden",
                        "text-overflow": "ellipsis",
                      }}
                    >
                      {detailLine(
                        t.stages[t.stages.length - 1]?.details ?? {}
                      ).slice(0, 60)}
                    </td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// ── Sub-components ───────────────────────────────────────────────────────────

/** Compact trace card for the top status panels */
function TraceCard(props: { trace: PipelineTrace; compact?: boolean }) {
  const t = () => props.trace;
  const exec = () => t().stages.find((s) => s.name === "execution");
  const trig = () => t().stages.find((s) => s.name === "trigger");
  const side = () =>
    String(exec()?.details?.side ?? trig()?.details?.side ?? "").toUpperCase();

  return (
    <div
      style={{
        display: "flex",
        "align-items": "center",
        gap: "8px",
        "font-family": "var(--font-mono)",
        "font-size": "9px",
      }}
    >
      <span
        style={{
          "font-weight": "700",
          color: "var(--text-primary)",
        }}
      >
        {t().symbol}
      </span>
      <span
        style={{
          "font-size": "8px",
          "font-weight": "600",
          padding: "1px 5px",
          "border-radius": "3px",
          background:
            side() === "BUY"
              ? "rgba(34,197,94,0.15)"
              : side() === "SELL"
              ? "rgba(239,68,68,0.15)"
              : "rgba(100,116,139,0.1)",
          color:
            side() === "BUY"
              ? "var(--green)"
              : side() === "SELL"
              ? "var(--red)"
              : "var(--text-muted)",
        }}
      >
        {side() || "—"}
      </span>
      <Show when={exec()?.details?.entry_price}>
        <span style={{ color: "var(--text-muted)" }}>
          @ {String(exec()!.details.entry_price)}
        </span>
      </Show>
      <Show when={exec()?.details?.stop_loss}>
        <span style={{ color: "var(--red)", "font-size": "8px" }}>
          SL {String(exec()!.details.stop_loss)}
        </span>
      </Show>
      <Show when={exec()?.details?.take_profit}>
        <span style={{ color: "var(--green)", "font-size": "8px" }}>
          TP {String(exec()!.details.take_profit)}
        </span>
      </Show>
      <span style={{ color: "var(--text-muted)", "margin-left": "auto" }}>
        {timeShort(t().timestamp)}
      </span>
    </div>
  );
}

/** Detailed trace view for the selected-operation panel */
function TraceDetail(props: { trace: PipelineTrace }) {
  const t = () => props.trace;

  return (
    <div
      style={{
        display: "flex",
        "flex-direction": "column",
        gap: "4px",
        "font-family": "var(--font-mono)",
        "font-size": "9px",
      }}
    >
      <div class="kv-row">
        <span class="k">Trace ID</span>
        <span class="v">{t().trace_id}</span>
      </div>
      <div class="kv-row">
        <span class="k">Symbol</span>
        <span class="v">{t().symbol}</span>
      </div>
      <div class="kv-row">
        <span class="k">Time</span>
        <span class="v">{t().timestamp}</span>
      </div>
      <div class="kv-row">
        <span class="k">Final Gate</span>
        <span class="v">{t().final_gate}</span>
      </div>
      <div class="kv-row">
        <span class="k">Result</span>
        <span
          class="v"
          style={{
            color: t().final_passed ? "var(--green)" : "var(--red)",
            "font-weight": "700",
          }}
        >
          {t().final_passed ? "ACCEPTED" : "BLOCKED"}
        </span>
      </div>
      <div
        style={{
          "margin-top": "4px",
          "border-top": "1px solid var(--border-subtle)",
          "padding-top": "4px",
        }}
      >
        <div
          style={{
            "font-size": "8px",
            color: "var(--text-muted)",
            "text-transform": "uppercase",
            "letter-spacing": "0.06em",
            "margin-bottom": "3px",
          }}
        >
          Stage Results
        </div>
        <For each={t().stages}>
          {(stage) => (
            <div
              style={{
                display: "flex",
                "align-items": "flex-start",
                gap: "5px",
                padding: "2px 0",
                "border-bottom": "1px solid rgba(37,44,56,0.3)",
              }}
            >
              <span
                style={{
                  width: "5px",
                  height: "5px",
                  "border-radius": "50%",
                  background: stage.passed ? "var(--green)" : "var(--red)",
                  "margin-top": "3px",
                  "flex-shrink": "0",
                }}
              />
              <span
                style={{
                  "min-width": "70px",
                  color: "var(--text-secondary)",
                  "font-weight": "500",
                }}
              >
                {stage.name}
              </span>
              <span
                style={{
                  color: "var(--text-muted)",
                  "font-size": "8px",
                  overflow: "hidden",
                  "text-overflow": "ellipsis",
                  "white-space": "nowrap",
                }}
                title={detailLine(stage.details)}
              >
                {detailLine(stage.details).slice(0, 80) || "—"}
              </span>
            </div>
          )}
        </For>
      </div>
    </div>
  );
}

/** Mini stage dots for the table row */
function StageDots(props: { trace: PipelineTrace }) {
  return (
    <div
      style={{
        display: "flex",
        gap: "2px",
        "align-items": "center",
      }}
    >
      <For each={[...STAGE_ORDER]}>
        {(stage) => {
          const st = stageStatus(props.trace, stage);
          return (
            <span
              title={`${stage}: ${st}`}
              style={{
                width: "6px",
                height: "6px",
                "border-radius": "50%",
                background: statusDot(st),
                opacity: st === "pending" ? "0.3" : "1",
              }}
            />
          );
        }}
      </For>
    </div>
  );
}

export default FastPipeline;
