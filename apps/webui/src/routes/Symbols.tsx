import type { Component } from "solid-js";
import { Show, For, createSignal, createResource, createMemo, onMount } from "solid-js";
import { api } from "../api/client";
import { runtimeStore } from "../stores/runtimeStore";
import type { CatalogEntry, SymbolSpec } from "../types/api";

/* ── helpers ────────────────────────────────────────────────────────────────── */

const TRADE_MODE_LABELS: Record<number, string> = {
  0: "Disabled",
  1: "LongOnly",
  2: "ShortOnly",
  3: "CloseOnly",
  4: "Full",
};

function tradeModeLabel(m: number | undefined): string {
  return TRADE_MODE_LABELS[m ?? -1] ?? String(m ?? "?");
}

function tradeModeColor(m: number | undefined): string {
  if (m === 4) return "var(--green)";
  if (m === 0) return "var(--red)";
  return "var(--amber)";
}

/** Build nested tree from flat catalog entries: asset_class → path_group → entries */
interface TreeGroup {
  name: string;
  entries: CatalogEntry[];
}
interface TreeNode {
  name: string;
  groups: TreeGroup[];
  totalCount: number;
}

function buildTree(entries: CatalogEntry[]): TreeNode[] {
  const map = new Map<string, Map<string, CatalogEntry[]>>();
  for (const e of entries) {
    const ac = e.asset_class || "(unclassified)";
    const pg = e.path_group || "(root)";
    if (!map.has(ac)) map.set(ac, new Map());
    const groups = map.get(ac)!;
    if (!groups.has(pg)) groups.set(pg, []);
    groups.get(pg)!.push(e);
  }

  // Detect groups where every symbol IS the group (like Crypto on FBS).
  // In that case, flatten into a single "(all)" group.
  const nodes: TreeNode[] = [];
  for (const [ac, groups] of map) {
    const allEntries: CatalogEntry[] = [];
    const groupList: TreeGroup[] = [];
    let allSingletons = true;
    for (const [pg, entries] of groups) {
      allEntries.push(...entries);
      if (entries.length > 1) allSingletons = false;
      groupList.push({ name: pg, entries: entries.sort((a, b) => (a.symbol ?? "").localeCompare(b.symbol ?? "")) });
    }
    // If every group is a single-symbol group AND there are >3 groups, flatten them
    if (allSingletons && groupList.length > 3) {
      nodes.push({
        name: ac,
        groups: [{ name: "(all)", entries: allEntries.sort((a, b) => (a.symbol ?? "").localeCompare(b.symbol ?? "")) }],
        totalCount: allEntries.length,
      });
    } else {
      groupList.sort((a, b) => a.name.localeCompare(b.name));
      nodes.push({ name: ac, groups: groupList, totalCount: allEntries.length });
    }
  }

  // Use broker order (first-seen order from catalog)
  return nodes;
}

/* ── component ──────────────────────────────────────────────────────────────── */

const Symbols: Component = () => {
  const [catalogRes] = createResource(() => api.catalog());
  const [filter, setFilter] = createSignal("");
  const [expandedAC, setExpandedAC] = createSignal<Set<string>>(new Set());
  const [expandedPG, setExpandedPG] = createSignal<Set<string>>(new Set());
  const [selectedSymbol, setSelectedSymbol] = createSignal<string | null>(null);
  const [selectedSpec, setSelectedSpec] = createSignal<SymbolSpec | null>(null);
  const [specLoading, setSpecLoading] = createSignal(false);
  const [subAction, setSubAction] = createSignal<string | null>(null);

  const brokerName = () => {
    const b = runtimeStore.snapshot?.broker_identity;
    return b ? `${b.broker_company ?? "?"} (${b.broker_server ?? "?"})` : "Broker";
  };

  const subscribedSet = (): Set<string> => {
    const arr = runtimeStore.snapshot?.universes?.subscribed_universe ?? [];
    return new Set(arr);
  };

  /** Desk assignments from runtime snapshot (symbol → desks[]) */
  const deskAssignments = (): Record<string, string[]> =>
    runtimeStore.snapshot?.symbol_desk_assignments ?? {};

  function symbolDesks(sym: string): string[] {
    return deskAssignments()[sym] ?? ["fast", "smc"];
  }

  const catalogEntries = (): CatalogEntry[] => catalogRes()?.symbols ?? [];
  const catalogStatus = () => catalogRes()?.status;

  const filteredEntries = createMemo(() => {
    const q = filter().trim().toUpperCase();
    if (!q) return catalogEntries();
    return catalogEntries().filter(
      (e) =>
        (e.symbol ?? "").toUpperCase().includes(q) ||
        (e.description ?? "").toUpperCase().includes(q) ||
        (e.asset_class ?? "").toUpperCase().includes(q) ||
        (e.path_group ?? "").toUpperCase().includes(q)
    );
  });

  const tree = createMemo(() => buildTree(filteredEntries()));

  // Auto-expand all groups when filtering
  createMemo(() => {
    const q = filter().trim();
    if (q.length > 0) {
      const acSet = new Set<string>();
      const pgSet = new Set<string>();
      for (const node of tree()) {
        acSet.add(node.name);
        for (const g of node.groups) pgSet.add(`${node.name}/${g.name}`);
      }
      setExpandedAC(acSet);
      setExpandedPG(pgSet);
    }
  });

  function toggleAC(name: string) {
    const s = new Set(expandedAC());
    if (s.has(name)) s.delete(name); else s.add(name);
    setExpandedAC(s);
  }

  function togglePG(key: string) {
    const s = new Set(expandedPG());
    if (s.has(key)) s.delete(key); else s.add(key);
    setExpandedPG(s);
  }

  async function selectSymbol(sym: string) {
    setSelectedSymbol(sym);
    setSelectedSpec(null);
    // Try to load full spec (only works for subscribed symbols)
    setSpecLoading(true);
    try {
      const spec = await api.spec(sym);
      setSelectedSpec(spec);
    } catch {
      setSelectedSpec(null);
    } finally {
      setSpecLoading(false);
    }
  }

  async function toggleSubscription(sym: string) {
    setSubAction(sym);
    try {
      if (subscribedSet().has(sym)) {
        await api.unsubscribe(sym);
      } else {
        await api.subscribe(sym);
      }
      // SSE will update the snapshot with new subscribed_universe
    } catch (e) {
      console.error("[Symbols] subscribe/unsubscribe error:", e);
    } finally {
      setSubAction(null);
    }
  }

  async function toggleDesk(sym: string, desk: string) {
    const current = new Set(symbolDesks(sym));
    if (current.has(desk)) {
      current.delete(desk);
    } else {
      current.add(desk);
    }
    if (current.size === 0) return; // must keep at least one desk
    try {
      await api.setSymbolDesks(sym, [...current]);
    } catch (e) {
      console.error("[Symbols] toggleDesk error:", e);
    }
  }

  /* ── render ─────────────────────────────────────────────────────────────── */

  return (
    <>
      <div style={{ flex: "1", padding: "8px 10px", "overflow-y": "auto", display: "flex", "flex-direction": "column", gap: "6px" }}>

        {/* Header panel */}
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <span class="panel-dot" style={{ background: "var(--cyan-live)" }} />
              Symbol Catalog
            </div>
            <Show when={catalogStatus()?.status === "ready"}>
              <span class="cap-badge live">Live</span>
            </Show>
          </div>
          <div class="panel-body">
            <div style={{ display: "flex", "align-items": "center", "justify-content": "space-between", "margin-bottom": "8px" }}>
              <div style={{ "font-size": "10px", color: "var(--text-secondary)", "font-family": "var(--font-mono)" }}>
                {brokerName()}
              </div>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                {catalogEntries().length} symbols
                {" · "}
                {subscribedSet().size} subscribed
              </div>
            </div>
            {/* Search */}
            <input
              type="text"
              placeholder="Filter symbols… (name, description, asset class)"
              value={filter()}
              onInput={(e) => setFilter(e.currentTarget.value)}
              style={{
                width: "100%",
                padding: "5px 8px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-subtle)",
                "border-radius": "3px",
                color: "var(--text-primary)",
                "font-family": "var(--font-mono)",
                "font-size": "10px",
                outline: "none",
              }}
            />
          </div>
        </div>

        {/* Main content: tree + detail */}
        <div style={{ flex: "1", display: "flex", gap: "6px", "min-height": "0" }}>

          {/* Left: tree panel */}
          <div class="panel" style={{ flex: "1", overflow: "hidden", display: "flex", "flex-direction": "column", "min-width": "0" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--teal)" }} />
                Symbol Tree
              </div>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "4px 0" }}>
              <Show when={!catalogRes.loading} fallback={
                <div style={{ padding: "12px", "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>Loading catalog…</div>
              }>
                <Show when={tree().length > 0} fallback={
                  <div style={{ padding: "12px", "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                    {filter() ? "No symbols match filter" : "Empty catalog"}
                  </div>
                }>
                  <For each={tree()}>
                    {(node) => {
                      const isExpanded = () => expandedAC().has(node.name);
                      return (
                        <div>
                          {/* Asset class row */}
                          <div
                            onClick={() => toggleAC(node.name)}
                            style={{
                              display: "flex",
                              "align-items": "center",
                              gap: "4px",
                              padding: "4px 8px",
                              cursor: "pointer",
                              "user-select": "none",
                              "font-family": "var(--font-mono)",
                              "font-size": "10px",
                              "font-weight": "600",
                              color: "var(--text-primary)",
                              background: isExpanded() ? "rgba(34,211,238,0.03)" : "transparent",
                            }}
                          >
                            <span style={{ color: "var(--text-muted)", "font-size": "8px", width: "10px", "text-align": "center" }}>
                              {isExpanded() ? "▼" : "▶"}
                            </span>
                            <span style={{ color: "var(--amber)", "font-size": "9px" }}>📁</span>
                            {node.name}
                            <span style={{ color: "var(--text-muted)", "font-size": "8px", "margin-left": "auto" }}>
                              {node.totalCount}
                            </span>
                          </div>

                          {/* Groups within asset class */}
                          <Show when={isExpanded()}>
                            <For each={node.groups}>
                              {(group) => {
                                const pgKey = () => `${node.name}/${group.name}`;
                                const isPGExpanded = () => expandedPG().has(pgKey());
                                const isSingleGroup = () => node.groups.length === 1 && group.name === "(all)";

                                return (
                                  <div>
                                    {/* Group row — hidden if only one "all" group */}
                                    <Show when={!isSingleGroup()}>
                                      <div
                                        onClick={() => togglePG(pgKey())}
                                        style={{
                                          display: "flex",
                                          "align-items": "center",
                                          gap: "4px",
                                          padding: "3px 8px 3px 24px",
                                          cursor: "pointer",
                                          "user-select": "none",
                                          "font-family": "var(--font-mono)",
                                          "font-size": "9.5px",
                                          color: "var(--text-secondary)",
                                        }}
                                      >
                                        <span style={{ color: "var(--text-muted)", "font-size": "7px", width: "10px", "text-align": "center" }}>
                                          {isPGExpanded() ? "▼" : "▶"}
                                        </span>
                                        <span style={{ color: "var(--amber)", "font-size": "8px" }}>📂</span>
                                        {group.name}
                                        <span style={{ color: "var(--text-muted)", "font-size": "8px", "margin-left": "auto" }}>
                                          {group.entries.length}
                                        </span>
                                      </div>
                                    </Show>

                                    {/* Symbol rows */}
                                    <Show when={isSingleGroup() || isPGExpanded()}>
                                      <For each={group.entries}>
                                        {(entry) => {
                                          const sym = () => entry.symbol ?? "?";
                                          const isSub = () => subscribedSet().has(sym());
                                          const isSelected = () => selectedSymbol() === sym();
                                          const indent = isSingleGroup() ? "24px" : "40px";

                                          return (
                                            <div
                                              onClick={() => selectSymbol(sym())}
                                              style={{
                                                display: "flex",
                                                "align-items": "center",
                                                gap: "6px",
                                                padding: `2px 8px 2px ${indent}`,
                                                cursor: "pointer",
                                                "user-select": "none",
                                                "font-family": "var(--font-mono)",
                                                "font-size": "9px",
                                                background: isSelected()
                                                  ? "rgba(34,211,238,0.08)"
                                                  : "transparent",
                                                "border-left": isSelected()
                                                  ? "2px solid var(--cyan-live)"
                                                  : "2px solid transparent",
                                              }}
                                            >
                                              {/* Subscribe toggle */}
                                              <div
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  toggleSubscription(sym());
                                                }}
                                                title={isSub() ? "Click to unsubscribe" : "Click to subscribe"}
                                                style={{
                                                  width: "14px",
                                                  height: "14px",
                                                  "border-radius": "3px",
                                                  border: isSub()
                                                    ? "1.5px solid var(--green)"
                                                    : "1.5px solid var(--border-medium)",
                                                  background: isSub()
                                                    ? "var(--green-dim)"
                                                    : "transparent",
                                                  display: "flex",
                                                  "align-items": "center",
                                                  "justify-content": "center",
                                                  "flex-shrink": "0",
                                                  "font-size": "8px",
                                                  cursor: "pointer",
                                                  opacity: subAction() === sym() ? "0.4" : "1",
                                                }}
                                              >
                                                {isSub() ? "✓" : ""}
                                              </div>
                                              {/* Symbol name */}
                                              <span style={{
                                                color: isSub() ? "var(--text-primary)" : "var(--text-secondary)",
                                                "font-weight": isSub() ? "600" : "400",
                                                "min-width": "70px",
                                              }}>
                                                {sym()}
                                              </span>
                                              {/* Description */}
                                              <span style={{
                                                color: "var(--text-muted)",
                                                "font-size": "8px",
                                                "white-space": "nowrap",
                                                overflow: "hidden",
                                                "text-overflow": "ellipsis",
                                                flex: "1",
                                                "min-width": "0",
                                              }}>
                                                {entry.description ?? ""}
                                              </span>
                                              {/* Trade mode badge */}
                                              <span style={{
                                                "font-size": "7px",
                                                color: tradeModeColor(entry.trade_mode),
                                                "white-space": "nowrap",
                                              }}>
                                                {tradeModeLabel(entry.trade_mode)}
                                              </span>
                                              {/* Desk badges (only for subscribed) */}
                                              <Show when={isSub()}>
                                                <DeskBadge desk="fast" sym={sym()} desks={symbolDesks(sym())} onToggle={toggleDesk} />
                                                <DeskBadge desk="smc" sym={sym()} desks={symbolDesks(sym())} onToggle={toggleDesk} />
                                              </Show>
                                            </div>
                                          );
                                        }}
                                      </For>
                                    </Show>
                                  </div>
                                );
                              }}
                            </For>
                          </Show>
                        </div>
                      );
                    }}
                  </For>
                </Show>
              </Show>
            </div>
          </div>

          {/* Right: detail panel */}
          <div class="panel" style={{ width: "340px", "flex-shrink": "0", overflow: "hidden", display: "flex", "flex-direction": "column" }}>
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-dot" style={{ background: "var(--blue)" }} />
                Symbol Detail
              </div>
            </div>
            <div style={{ flex: "1", "overflow-y": "auto", padding: "0" }}>
              <Show when={selectedSymbol()} fallback={
                <div style={{ padding: "16px", "font-size": "9px", color: "var(--text-muted)", "font-family": "var(--font-mono)", "text-align": "center" }}>
                  Select a symbol from the tree
                </div>
              }>
                {(_sym) => {
                  const sym = selectedSymbol()!;
                  const entry = () => catalogEntries().find((e) => e.symbol === sym);
                  const spec = () => selectedSpec();
                  const isSub = () => subscribedSet().has(sym);

                  return (
                    <div>
                      {/* Symbol header */}
                      <div style={{
                        padding: "10px",
                        "border-bottom": "1px solid var(--border-subtle)",
                        display: "flex",
                        "align-items": "center",
                        "justify-content": "space-between",
                      }}>
                        <div>
                          <div style={{ "font-family": "var(--font-mono)", "font-size": "13px", "font-weight": "700", color: "var(--text-primary)" }}>
                            {sym}
                          </div>
                          <div style={{ "font-family": "var(--font-mono)", "font-size": "8.5px", color: "var(--text-muted)", "margin-top": "2px" }}>
                            {entry()?.description ?? ""}
                          </div>
                        </div>
                        <button
                          onClick={() => toggleSubscription(sym)}
                          disabled={subAction() === sym}
                          style={{
                            "font-family": "var(--font-mono)",
                            "font-size": "8.5px",
                            "font-weight": "600",
                            padding: "4px 10px",
                            "border-radius": "3px",
                            border: "1px solid",
                            cursor: subAction() === sym ? "wait" : "pointer",
                            background: isSub() ? "var(--red-dim)" : "var(--green-dim)",
                            color: isSub() ? "var(--red)" : "var(--green)",
                            "border-color": isSub() ? "rgba(239,68,68,0.3)" : "rgba(34,197,94,0.3)",
                          }}
                        >
                          {subAction() === sym ? "…" : isSub() ? "UNSUBSCRIBE" : "SUBSCRIBE"}
                        </button>
                      </div>
                      {/* Desk assignment toggles (only for subscribed) */}
                      <Show when={isSub()}>
                        <div style={{
                          padding: "8px 10px",
                          "border-bottom": "1px solid var(--border-subtle)",
                          display: "flex",
                          "align-items": "center",
                          gap: "8px",
                        }}>
                          <span style={{ "font-family": "var(--font-mono)", "font-size": "8px", "text-transform": "uppercase", color: "var(--text-muted)", "letter-spacing": "0.06em" }}>
                            Desks
                          </span>
                          <DeskToggle desk="fast" label="⚡ FAST" sym={sym} desks={symbolDesks(sym)} onToggle={toggleDesk} />
                          <DeskToggle desk="smc" label="◆ SMC" sym={sym} desks={symbolDesks(sym)} onToggle={toggleDesk} />
                        </div>
                      </Show>
                      {/* Catalog info — always available */}
                      <div style={{ padding: "8px 10px" }}>
                        <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", "text-transform": "uppercase", color: "var(--text-muted)", "letter-spacing": "0.06em", "margin-bottom": "6px" }}>
                          Catalog Info
                        </div>
                        <SpecKV label="Path" value={entry()?.path ?? "—"} />
                        <SpecKV label="Asset Class" value={entry()?.asset_class ?? "—"} />
                        <SpecKV label="Trade Mode" value={tradeModeLabel(entry()?.trade_mode)} valueColor={tradeModeColor(entry()?.trade_mode)} />
                        <SpecKV label="Digits" value={String(entry()?.digits ?? "—")} />
                        <SpecKV label="Visible in MW" value={entry()?.visible ? "Yes" : "No"} />
                        <SpecKV label="Currency Base" value={entry()?.currency_base ?? "—"} />
                        <SpecKV label="Currency Profit" value={entry()?.currency_profit ?? "—"} />
                        <SpecKV label="Currency Margin" value={entry()?.currency_margin ?? "—"} />
                      </div>

                      {/* Full spec — only if subscribed / spec loaded */}
                      <Show when={specLoading()}>
                        <div style={{ padding: "6px 10px", "font-size": "8px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                          Loading spec…
                        </div>
                      </Show>
                      <Show when={spec()}>
                        <div style={{ padding: "0 10px 8px", "border-top": "1px solid var(--border-subtle)" }}>
                          <div style={{ "font-family": "var(--font-mono)", "font-size": "8px", "text-transform": "uppercase", color: "var(--text-muted)", "letter-spacing": "0.06em", "margin": "8px 0 6px" }}>
                            Specification
                          </div>
                          <SpecKV label="Contract Size" value={String(spec()!.contract_size ?? "—")} />
                          <SpecKV label="Tick Size" value={String(spec()!.tick_size ?? "—")} />
                          <SpecKV label="Tick Value" value={String(spec()!.tick_value ?? "—")} />
                          <SpecKV label="Point" value={String(spec()!.point ?? "—")} />
                          <SpecKV label="Spread (pts)" value={String(spec()!.spread_points ?? "—")} />
                          <SpecKV label="Spread Float" value={spec()!.spread_float ? "Yes" : "No"} />
                          <SpecKV label="Stops Level" value={String(spec()!.stops_level_points ?? "—")} />
                          <SpecKV label="Vol Min" value={String(spec()!.volume_min ?? "—")} />
                          <SpecKV label="Vol Max" value={String(spec()!.volume_max ?? "—")} />
                          <SpecKV label="Vol Step" value={String(spec()!.volume_step ?? "—")} />
                          <SpecKV label="Swap Long" value={String(spec()!.swap_long ?? "—")} />
                          <SpecKV label="Swap Short" value={String(spec()!.swap_short ?? "—")} />
                          <SpecKV label="Margin Initial" value={String(spec()!.margin_initial ?? "—")} />
                          <SpecKV label="Margin Maintenance" value={String(spec()!.margin_maintenance ?? "—")} />
                          <SpecKV label="Margin Hedged" value={String(spec()!.margin_hedged ?? "—")} />
                        </div>
                      </Show>
                      <Show when={!spec() && !specLoading() && isSub()}>
                        <div style={{ padding: "6px 10px", "font-size": "8px", color: "var(--text-muted)", "font-family": "var(--font-mono)" }}>
                          Spec not available yet — will load on next refresh cycle.
                        </div>
                      </Show>
                      <Show when={!isSub() && !specLoading()}>
                        <div style={{ padding: "6px 10px", "font-size": "8px", color: "var(--amber)", "font-family": "var(--font-mono)" }}>
                          ⚠ Subscribe to load full specification and enable trading.
                        </div>
                      </Show>

                      {/* EA warning for subscribed but no indicator data */}
                      <Show when={isSub()}>
                        <div style={{
                          margin: "6px 10px 10px",
                          padding: "8px",
                          background: "var(--amber-dim)",
                          border: "1px solid rgba(245,166,35,0.2)",
                          "border-radius": "4px",
                          "font-family": "var(--font-mono)",
                          "font-size": "8px",
                          color: "var(--amber)",
                          "line-height": "1.5",
                        }}>
                          <div style={{ "font-weight": "700", "margin-bottom": "3px" }}>
                            ⚠ EA Required — LLMIndicatorServiceEA
                          </div>
                          <div style={{ color: "var(--text-secondary)" }}>
                            For this symbol to be fully operational, attach the Expert Advisor
                            <strong style={{ color: "var(--text-primary)" }}> LLMIndicatorServiceEA</strong> in
                            MetaTrader 5 on timeframes <strong style={{ color: "var(--text-primary)" }}>M1</strong>,
                            <strong style={{ color: "var(--text-primary)" }}> M5</strong> and
                            <strong style={{ color: "var(--text-primary)" }}> H1</strong> for {sym}.
                          </div>
                          <div style={{ "margin-top": "4px", color: "var(--text-muted)" }}>
                            Without the EA active, the system will not generate trading signals for this symbol.
                          </div>
                        </div>
                      </Show>
                    </div>
                  );
                }}
              </Show>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div class="footer-bar">
        <span>
          Catalog: {catalogStatus()?.status ?? "…"} · {catalogEntries().length} symbols
        </span>
        <span>
          Updated: {catalogStatus()?.updated_at ?? "—"}
        </span>
      </div>
    </>
  );
};

/* ── Small KV row component ────────────────────────────────────────────────── */
function SpecKV(props: { label: string; value: string; valueColor?: string }) {
  return (
    <div class="kv-row">
      <span class="k">{props.label}</span>
      <span class="v" style={{ color: props.valueColor ?? "var(--text-secondary)" }}>{props.value}</span>
    </div>
  );
}

/* ── Desk badge (compact, for tree rows) ──────────────────────────────────── */
function DeskBadge(props: { desk: string; sym: string; desks: string[]; onToggle: (sym: string, desk: string) => void }) {
  const active = () => props.desks.includes(props.desk);
  return (
    <span
      class={`desk-badge ${props.desk} ${active() ? "on" : "off"}`}
      onClick={(e) => { e.stopPropagation(); props.onToggle(props.sym, props.desk); }}
      title={`${active() ? "Disable" : "Enable"} ${props.desk.toUpperCase()} desk for ${props.sym}`}
    >
      {props.desk === "fast" ? "⚡ FAST" : "◆ SMC"}
    </span>
  );
}

/* ── Desk toggle (larger, for detail panel) ───────────────────────────────── */
function DeskToggle(props: { desk: string; label: string; sym: string; desks: string[]; onToggle: (sym: string, desk: string) => void }) {
  const active = () => props.desks.includes(props.desk);
  return (
    <button
      class={`desk-btn ${props.desk} ${active() ? "on" : "off"}`}
      onClick={() => props.onToggle(props.sym, props.desk)}
      title={`${active() ? "Disable" : "Enable"} ${props.desk.toUpperCase()} desk`}
    >
      {props.label}
    </button>
  );
}

export default Symbols;
