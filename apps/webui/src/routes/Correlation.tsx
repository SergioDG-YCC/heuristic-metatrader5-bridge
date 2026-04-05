import type { Component } from "solid-js";
import {
  createSignal,
  createMemo,
  onMount,
  onCleanup,
  For,
  Show,
} from "solid-js";
import { api } from "../api/client";
import type { CorrelationMatrixResponse, CorrelationPairRow } from "../types/api";

// ── Constants ─────────────────────────────────────────────────────────────────

const TIMEFRAMES = ["M5", "M30", "H1"] as const;
type TF = (typeof TIMEFRAMES)[number];

// ── Helpers ───────────────────────────────────────────────────────────────────

function cellBg(coeff: number | undefined): string {
  if (coeff == null) return "var(--bg-panel)";
  const alpha = Math.min(0.85, Math.abs(coeff) * 0.8 + 0.05);
  if (coeff >= 0) return `rgba(34, 197, 94, ${alpha.toFixed(2)})`;
  return `rgba(239, 68, 68, ${alpha.toFixed(2)})`;
}

function cellFg(coeff: number | undefined): string {
  if (coeff == null) return "var(--text-muted)";
  return Math.abs(coeff) >= 0.55 ? "#fff" : "var(--text-primary)";
}

function fmt(coeff: number): string {
  return (coeff >= 0 ? "+" : "") + coeff.toFixed(2);
}

function buildMatrix(
  pairs: CorrelationPairRow[]
): Map<string, CorrelationPairRow> {
  const m = new Map<string, CorrelationPairRow>();
  for (const p of pairs) {
    m.set(`${p.symbol_a}|${p.symbol_b}`, p);
    m.set(`${p.symbol_b}|${p.symbol_a}`, p);
  }
  return m;
}

function shortTs(iso: string): string {
  try {
    return iso.slice(11, 16) + " UTC";
  } catch {
    return iso;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

const Correlation: Component = () => {
  const [activeTab, setActiveTab] = createSignal<TF>("M5");
  const [matrixData, setMatrixData] =
    createSignal<CorrelationMatrixResponse | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [fetchError, setFetchError] = createSignal<string | null>(null);

  let intervalId: ReturnType<typeof setInterval> | undefined;

  const pairMap = createMemo<Map<string, CorrelationPairRow> | null>(() => {
    const d = matrixData();
    return d ? buildMatrix(d.pairs) : null;
  });

  // True when every pair reports stale source data (market closed / weekend)
  const staleCount = createMemo(() => {
    const d = matrixData();
    if (!d) return 0;
    return d.pairs.filter((p) => p.source_stale).length;
  });
  const allStale = createMemo(() => {
    const d = matrixData();
    if (!d || d.pairs.length === 0) return false;
    return staleCount() === d.pairs.length;
  });

  async function doFetch(tf: TF): Promise<void> {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await api.correlationMatrix(tf);
      setMatrixData(data);
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : String(err));
      setMatrixData(null);
    } finally {
      setLoading(false);
    }
  }

  function start(tf: TF): void {
    if (intervalId !== undefined) clearInterval(intervalId);
    void doFetch(tf);
    intervalId = setInterval(() => void doFetch(tf), 30_000);
  }

  function switchTab(tf: TF): void {
    setActiveTab(tf);
    start(tf);
  }

  onMount(() => start("M5"));
  onCleanup(() => {
    if (intervalId !== undefined) clearInterval(intervalId);
  });

  return (
    <div
      style={{
        padding: "14px 16px",
        "overflow-y": "auto",
        height: "100%",
        "box-sizing": "border-box",
        "font-family": "var(--font-mono)",
      }}
    >
      {/* ── Header strip ── */}
      <div
        style={{
          display: "flex",
          "align-items": "center",
          gap: "10px",
          "margin-bottom": "12px",
        }}
      >
        <span
          style={{
            "font-size": "11px",
            "font-weight": "700",
            color: "var(--cyan-live)",
            "letter-spacing": "0.08em",
            "text-transform": "uppercase",
          }}
        >
          ⊠ Correlation Matrix
        </span>
        <Show when={matrixData()}>
          <span style={{ "font-size": "10px", color: "var(--text-muted)" }}>
            {matrixData()!.symbols.length} symbols
          </span>
          <span style={{ "font-size": "10px", color: "var(--text-muted)" }}>
            · computed {shortTs(matrixData()!.computed_at)}
          </span>
          <Show when={allStale()}>
            <span
              style={{
                "font-size": "9px",
                color: "var(--amber)",
                background: "rgba(245,166,35,0.12)",
                border: "1px solid rgba(245,166,35,0.3)",
                "border-radius": "3px",
                padding: "1px 6px",
              }}
            >
              STALE SOURCE
            </span>
          </Show>
        </Show>
        <Show when={loading()}>
          <span style={{ "font-size": "10px", color: "var(--text-muted)" }}>
            ···
          </span>
        </Show>
      </div>

      {/* ── Timeframe tab strip ── */}
      <div
        style={{
          display: "flex",
          gap: "4px",
          "margin-bottom": "12px",
        }}
      >
        <For each={TIMEFRAMES}>
          {(tf) => (
            <button
              onClick={() => switchTab(tf)}
              style={{
                padding: "3px 10px",
                "border-radius": "3px",
                border: `1px solid ${
                  activeTab() === tf ? "var(--cyan-live)" : "var(--bg-border)"
                }`,
                background:
                  activeTab() === tf ? "var(--cyan-dim)" : "var(--bg-panel)",
                color:
                  activeTab() === tf ? "var(--cyan-live)" : "var(--text-muted)",
                "font-family": "var(--font-mono)",
                "font-size": "10px",
                cursor: "pointer",
              }}
            >
              {tf}
            </button>
          )}
        </For>
      </div>

      {/* ── Error panel ── */}
      <Show when={fetchError()}>
        <div
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.3)",
            "border-radius": "4px",
            padding: "10px 12px",
            "margin-bottom": "12px",
            "font-size": "11px",
            color: "var(--red)",
          }}
        >
          {fetchError()}
        </div>
      </Show>

      {/* ── Matrix ── */}
      <Show when={matrixData() && !fetchError()}>
        {/* Legend */}
        <div
          style={{
            display: "flex",
            "align-items": "center",
            gap: "12px",
            "margin-bottom": "8px",
            "font-size": "10px",
            color: "var(--text-muted)",
          }}
        >
          <span>
            <span
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                background: "rgba(34,197,94,0.7)",
                "border-radius": "2px",
                "vertical-align": "middle",
                "margin-right": "3px",
              }}
            />
            positive
          </span>
          <span>
            <span
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                background: "rgba(239,68,68,0.7)",
                "border-radius": "2px",
                "vertical-align": "middle",
                "margin-right": "3px",
              }}
            />
            negative
          </span>
          <span>window = {matrixData()!.min_pair_bars} bars</span>
          <span style={{ color: "var(--amber)" }}>⚠ = low coverage</span>
          <span style={{ color: "var(--amber)" }}>~ = stale source ({staleCount()}/{matrixData()!.pairs.length})</span>
        </div>

        {/* All-sources stale banner — market closed / weekend / inactive feed */}
        <Show when={allStale()}>
          <div
            style={{
              background: "rgba(245,166,35,0.06)",
              border: "1px solid rgba(245,166,35,0.35)",
              "border-radius": "4px",
              padding: "8px 12px",
              "margin-bottom": "8px",
              "font-size": "10px",
              color: "var(--amber)",
              display: "flex",
              gap: "8px",
              "align-items": "center",
            }}
          >
            <span style={{ "font-size": "12px" }}>⏸</span>
            <span>
              All market sources are stale — prices are frozen (market closed or
              MT5 feed inactive). Coefficients reflect historical data only.
            </span>
          </div>
        </Show>

        {/* Coverage warning banner */}
        <Show when={!matrixData()!.all_pairs_coverage_ok}>
          <div
            style={{
              background: "rgba(245,166,35,0.08)",
              border: "1px solid rgba(245,166,35,0.3)",
              "border-radius": "4px",
              padding: "6px 12px",
              "margin-bottom": "8px",
              "font-size": "10px",
              color: "var(--amber)",
            }}
          >
            ⚠ Some pairs have insufficient bar coverage — coefficients may be
            unreliable
          </div>
        </Show>

        {/* Heatmap table */}
        <div style={{ "overflow-x": "auto" }}>
          <table
            style={{
              "border-collapse": "collapse",
              "font-size": "10px",
              "font-family": "var(--font-mono)",
            }}
          >
            <thead>
              <tr>
                {/* Empty top-left corner */}
                <th style={{ width: "72px", "min-width": "72px" }} />
                <For each={matrixData()!.symbols}>
                  {(sym) => (
                    <th
                      style={{
                        height: "72px",
                        width: "46px",
                        "min-width": "46px",
                        "vertical-align": "bottom",
                        padding: "0 0 6px 0",
                        "text-align": "center",
                        "font-weight": "400",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <div
                        style={{
                          "writing-mode": "vertical-rl",
                          transform: "rotate(180deg)",
                          "white-space": "nowrap",
                          "font-size": "9px",
                          "letter-spacing": "0.05em",
                        }}
                      >
                        {sym}
                      </div>
                    </th>
                  )}
                </For>
              </tr>
            </thead>
            <tbody>
              <For each={matrixData()!.symbols}>
                {(rowSym) => (
                  <tr>
                    {/* Row label */}
                    <td
                      style={{
                        "text-align": "right",
                        "padding-right": "8px",
                        "white-space": "nowrap",
                        color: "var(--text-secondary)",
                        "font-size": "9px",
                        "letter-spacing": "0.05em",
                      }}
                    >
                      {rowSym}
                    </td>
                    {/* Cells */}
                    <For each={matrixData()!.symbols}>
                      {(colSym) => {
                        const isDiag = rowSym === colSym;
                        const pair = isDiag
                          ? undefined
                          : pairMap()?.get(`${rowSym}|${colSym}`);
                        const coeff = pair?.coefficient;
                        const isStale = !isDiag && (pair?.source_stale ?? false);
                        const title = isDiag
                          ? rowSym
                          : pair != null && coeff != null
                          ? `${rowSym} / ${colSym}: ${fmt(coeff)} (${
                              pair.bars_used
                            } bars, ${(pair.coverage_ratio * 100).toFixed(
                              0
                            )}% coverage${isStale ? " · SOURCE STALE" : ""})`
                          : `${rowSym} / ${colSym}: no data`;

                        return (
                          <td
                            title={title}
                            style={{
                              width: "46px",
                              "min-width": "46px",
                              height: "32px",
                              "text-align": "center",
                              "vertical-align": "middle",
                              background: isDiag
                                ? "var(--bg-elevated)"
                                : cellBg(coeff),
                              color: isDiag ? "var(--text-dim)" : cellFg(coeff),
                              border: isStale
                                ? "1px solid rgba(245,166,35,0.5)"
                                : "1px solid var(--bg-border)",
                              "font-size": "10px",
                              "font-weight":
                                coeff != null && Math.abs(coeff) >= 0.7
                                  ? "700"
                                  : "400",
                              "letter-spacing": "0.02em",
                              cursor: isDiag ? "default" : "help",
                              opacity: isStale ? "0.75" : "1",
                            }}
                          >
                            {isDiag
                              ? "—"
                              : coeff != null
                              ? (isStale ? "~" : "") + fmt(coeff)
                              : "—"}
                            <Show
                              when={
                                !isDiag &&
                                pair != null &&
                                coeff != null &&
                                !pair.coverage_ok
                              }
                            >
                              <sup
                                style={{
                                  color: "var(--amber)",
                                  "font-size": "8px",
                                  "margin-left": "1px",
                                }}
                              >
                                ⚠
                              </sup>
                            </Show>
                          </td>
                        );
                      }}
                    </For>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
      </Show>

      {/* ── Empty / waiting state ── */}
      <Show when={!matrixData() && !fetchError() && !loading()}>
        <div
          style={{
            color: "var(--text-muted)",
            "font-size": "11px",
            "padding-top": "32px",
            "text-align": "center",
          }}
        >
          Waiting for first refresh cycle…
        </div>
      </Show>
    </div>
  );
};

export default Correlation;
