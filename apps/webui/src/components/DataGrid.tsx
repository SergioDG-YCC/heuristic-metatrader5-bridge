import type { Component, JSXElement } from "solid-js";
import { For } from "solid-js";

export interface Column<T> {
  key: string;
  header: string;
  width?: string;
  render?: (row: T) => JSXElement;
  align?: "left" | "right" | "center";
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  emptyText?: string;
  rowKey?: (row: T, i: number) => string;
}

export function DataGrid<T extends Record<string, unknown>>(
  props: Props<T>
): JSXElement {
  return (
    <div style={{ "overflow-x": "auto", width: "100%" }}>
      <table
        style={{
          width: "100%",
          "border-collapse": "collapse",
          "font-size": "12px",
          "font-variant-numeric": "tabular-nums",
        }}
      >
        <thead>
          <tr>
            <For each={props.columns}>
              {(col) => (
                <th
                  style={{
                    padding: "5px 10px",
                    "text-align": col.align ?? "left",
                    "font-size": "10px",
                    "text-transform": "uppercase",
                    "letter-spacing": "0.07em",
                    color: "var(--text-dim)",
                    "border-bottom": "1px solid var(--bg-border)",
                    "white-space": "nowrap",
                    width: col.width,
                  }}
                >
                  {col.header}
                </th>
              )}
            </For>
          </tr>
        </thead>
        <tbody>
          {props.rows.length === 0 ? (
            <tr>
              <td
                colspan={props.columns.length}
                style={{
                  padding: "16px 10px",
                  "text-align": "center",
                  color: "var(--text-dim)",
                  "font-style": "italic",
                  "font-size": "12px",
                }}
              >
                {props.emptyText ?? "No data"}
              </td>
            </tr>
          ) : (
            <For each={props.rows}>
              {(row, i) => (
                <tr
                  style={{
                    "border-bottom": "1px solid var(--bg-border)",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background =
                      "var(--bg-panel-hover)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = "transparent";
                  }}
                >
                  <For each={props.columns}>
                    {(col) => (
                      <td
                        style={{
                          padding: "5px 10px",
                          "text-align": col.align ?? "left",
                          color: "var(--text-primary)",
                          "white-space": "nowrap",
                        }}
                      >
                        {col.render
                          ? col.render(row)
                          : String(row[col.key] ?? "—")}
                      </td>
                    )}
                  </For>
                </tr>
              )}
            </For>
          )}
        </tbody>
      </table>
    </div>
  );
}
