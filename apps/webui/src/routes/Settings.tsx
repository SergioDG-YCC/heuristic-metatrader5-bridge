import type { Component } from "solid-js";
import { Show, For, onMount, createSignal } from "solid-js";
import { api } from "../api/client";

const Settings: Component = () => {
  const [llmModels, setLlmModels] = createSignal<any[]>([]);
  const [llmStatus, setLlmStatus] = createSignal<any>(null);
  const [smcConfig, setSmcConfig] = createSignal<any>(null);
  const [fastConfig, setFastConfig] = createSignal<any>(null);
  const [ownershipConfig, setOwnershipConfig] = createSignal<any>(null);
  const [riskConfig, setRiskConfig] = createSignal<any>(null);
  const [deskStatus, setDeskStatus] = createSignal<any>(null);
  const [saving, setSaving] = createSignal<string | null>(null);
  const [error, setError] = createSignal<string | null>(null);
  const [success, setSuccess] = createSignal<string | null>(null);

  onMount(async () => {
    await loadAllConfigs();
  });

  async function loadAllConfigs() {
    console.log("[Settings] Loading all configs...");
    setError(null);
    setSuccess(null);
    
    // Use Promise.allSettled to load all configs independently
    // If one endpoint fails (e.g., LLM 500), others still load
    const results = await Promise.allSettled([
      api.getLlmModels(),
      api.getLlmStatus(),
      api.getSmcConfig(),
      api.getFastConfig(),
      api.getOwnershipConfig(),
      api.getRiskConfig(),
      api.deskStatus(),
    ]);

    console.log("[Settings] Promise.allSettled results:", results);

    const [llmModelsRes, llmStatusRes, smc, fast, ownership, risk, deskSt] = results.map(r =>
      r.status === "fulfilled" ? r.value : null
    );

    console.log("[Settings] Extracted values:", {
      llmModels: llmModelsRes?.status,
      llmStatus: llmStatusRes?.status,
      smc: smc?.status,
      fast: fast?.status,
      ownership: ownership?.status,
      risk: risk?.status,
    });

    // Load each config independently
    if (llmModelsRes?.status === "success" && "models" in llmModelsRes) {
      console.log("[Settings] Setting LLM models:", llmModelsRes.models?.length);
      setLlmModels(llmModelsRes.models || []);
    }
    if (llmStatusRes) {
      console.log("[Settings] Setting LLM status:", llmStatusRes);
      setLlmStatus(llmStatusRes);
    }
    if (smc?.status === "success" && "config" in smc) {
      console.log("[Settings] Setting SMC config:", smc.config);
      setSmcConfig((smc as any).config);
    } else {
      console.warn("[Settings] SMC config failed:", smc);
    }
    if (fast?.status === "success" && "config" in fast) {
      console.log("[Settings] Setting Fast config:", fast.config);
      setFastConfig((fast as any).config);
    } else {
      console.warn("[Settings] Fast config failed:", fast);
    }
    if (ownership?.status === "success" && "config" in ownership) {
      console.log("[Settings] Setting Ownership config:", ownership.config);
      setOwnershipConfig((ownership as any).config);
    }
    if (risk?.status === "success" && "config" in risk) {
      console.log("[Settings] Setting Risk config:", risk.config);
      setRiskConfig((risk as any).config);
    }
    if (deskSt?.status === "success") {
      setDeskStatus(deskSt);
    }

    // Report errors for failed loads
    const failedIndexes = results
      .map((r, i) => r.status === "rejected" ? i : -1)
      .filter(i => i !== -1);
    
    if (failedIndexes.length > 0) {
      const failedNames = failedIndexes.map(i => {
        const names = ["LLM Models", "LLM Status", "SMC Config", "Fast Config", "Ownership Config", "Risk Config"];
        return names[i];
      }).join(", ");
      setError(`Failed to load ${failedIndexes.length} config(s): ${failedNames}. Retrying...`);
      console.error("[Settings] Failed to load configs:", failedIndexes.map(i => results[i]));
      
      // Auto-retry after 3 seconds
      setTimeout(() => {
        console.log("[Settings] Auto-retrying config load...");
        loadAllConfigs();
      }, 3000);
    } else {
      console.log("[Settings] All configs loaded successfully");
    }
  }

  async function saveConfig(section: string, data: any) {
    setSaving(section);
    setError(null);
    setSuccess(null);
    try {
      let result;
      switch (section) {
        case "llm":
          result = await api.setLlmDefaultModel(data.model_id);
          break;
        case "smc":
          result = await api.updateSmcConfig(data);
          break;
        case "smc_enabled":
          result = await api.setSmcDeskEnabled(data.enabled);
          break;
        case "fast":
          result = await api.updateFastConfig(data);
          break;
        case "fast_enabled":
          result = await api.setFastDeskEnabled(data.enabled);
          break;
        case "ownership":
          result = await api.updateOwnershipConfig(data);
          break;
        case "risk":
          result = await api.updateRiskConfig(data);
          break;
        default:
          throw new Error(`Unknown section: ${section}`);
      }

      // Handle different response statuses
      if (result.status === "success") {
        setSuccess(`${section.toUpperCase()} configuration updated (runtime only)`);
        await loadAllConfigs(); // Reload to confirm
      } else if (result.status === "warning") {
        // Warning - operation partially succeeded
        setSuccess(`${section.toUpperCase()} update: ${result.message || "Check logs for details"}`);
        await loadAllConfigs();
      } else if (result.status === "error") {
        // Error - but non-critical, show as warning
        const errorMsg = (result as any).error || result.message || "Unknown error";
        setError(`${section.toUpperCase()} update failed: ${errorMsg}. This is non-critical.`);
      } else {
        throw new Error(`Unexpected response status: ${result.status}`);
      }
    } catch (e) {
      setError(`Failed to save ${section} config: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div style={{ padding: "20px", "overflow-y": "auto", "max-width": "1200px", margin: "0 auto" }}>
      <h1 style={{ "font-size": "20px", "margin-bottom": "20px", color: "var(--text-primary)" }}>
        ⚙️ Settings
      </h1>
      
      {/* Error/Success Messages */}
      <Show when={error()}>
        <div class="alert alert-error" style={{ margin: "10px 0", padding: "10px", background: "rgba(248, 81, 73, 0.1)", border: "1px solid var(--red)", "border-radius": "6px", color: "var(--red)" }}>
          ❌ {error()}
        </div>
      </Show>
      
      <Show when={success()}>
        <div class="alert alert-success" style={{ margin: "10px 0", padding: "10px", background: "rgba(63, 185, 80, 0.1)", border: "1px solid var(--green)", "border-radius": "6px", color: "var(--green)" }}>
          ✅ {success()}
        </div>
      </Show>

      {/* LLM Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">
            <span class="panel-dot" style={{ background: "var(--purple)" }} />
            LLM Configuration
          </div>
          <Show when={llmStatus()?.available}>
            <span class="cap-badge live">Live</span>
          </Show>
        </div>
        <div class="panel-body">
          <Show when={llmStatus()?.available} fallback={
            <div style={{ "font-size": "9px", color: "var(--amber)", padding: "10px" }}>
              ⚠️ LocalAI is not available. LLM features will be disabled.
            </div>
          }>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Current Model
              </label>
              <div style={{ "font-size": "12px", color: "var(--text-primary)", "margin-bottom": "10px" }}>
                {llmStatus()?.current_model || "—"}
              </div>
              
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Available Models ({llmModels().length})
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                onChange={(e) => saveConfig("llm", { model_id: e.currentTarget.value })}
                value={llmStatus()?.current_model || ""}
                disabled={saving() === "llm"}
              >
                <For each={llmModels()}>
                  {(model) => (
                    <option value={model.id}>
                      {model.name} {model.parameter_size ? `(${model.parameter_size})` : ""}
                    </option>
                  )}
                </For>
              </select>
              <Show when={saving() === "llm"}>
                <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "5px" }}>
                  Saving...
                </div>
              </Show>
            </div>
            
            <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "10px", padding: "8px", background: "var(--bg-tertiary)", "border-radius": "4px" }}>
              ℹ️ Changes update the SMC runtime model on the backend. To persist across restarts, update <code>SMC_LLM_MODEL</code> in <code>.env</code>.
            </div>
          </Show>
        </div>
      </div>

      {/* SMC Desk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">
            <span class="panel-dot" style={{ background: "var(--blue)" }} />
            SMC Desk Configuration
          </div>
          <div style={{ display: "flex", "align-items": "center", gap: "10px" }}>
            <Show when={deskStatus()?.smc_desk?.enabled}>
              <span class="cap-badge live">Active</span>
            </Show>
            <Show when={deskStatus() && !deskStatus()?.smc_desk?.enabled}>
              <span class="cap-badge" style={{ background: "var(--bg-tertiary)", color: "var(--text-muted)" }}>Inactive</span>
            </Show>
            <label style={{ display: "flex", "align-items": "center", gap: "5px", "font-size": "10px", color: "var(--text-secondary)", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={deskStatus()?.smc_desk?.enabled ?? true}
                disabled={saving() === "smc_enabled"}
                onChange={(e) => saveConfig("smc_enabled", { enabled: e.currentTarget.checked })}
              />
              Enabled
            </label>
          </div>
        </div>
        <div class="panel-body">
          <Show when={smcConfig()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading SMC config…</div>}>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Max Candidates: {smcConfig()?.max_candidates ?? "—"}
              </label>
              <input
                type="range"
                min="1"
                max="10"
                value={smcConfig()?.max_candidates || 3}
                onChange={(e) => saveConfig("smc", { max_candidates: Number(e.currentTarget.value) })}
                style={{ width: "100%" }}
                disabled={saving() === "smc"}
              />
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Min R:R: {smcConfig()?.min_rr ?? "—"}
              </label>
              <input
                type="number"
                min="1"
                max="10"
                step="0.5"
                value={smcConfig()?.min_rr || 2.0}
                onChange={(e) => saveConfig("smc", { min_rr: Number(e.currentTarget.value) })}
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                disabled={saving() === "smc"}
              />
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "flex", "align-items": "center", gap: "8px", "font-size": "11px", color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={smcConfig()?.llm_enabled ?? false}
                  onChange={(e) => saveConfig("smc", { llm_enabled: e.currentTarget.checked })}
                  disabled={saving() === "smc"}
                />
                LLM Validator Enabled
              </label>
            </div>
            
            {/* --- SMC Spread Tolerance --- */}
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Spread Tolerance: {smcConfig()?.spread_tolerance ?? "high"}
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                value={smcConfig()?.spread_tolerance || "high"}
                onChange={(e) => saveConfig("smc", { spread_tolerance: e.currentTarget.value })}
                disabled={saving() === "smc"}
              >
                <option value="low">Low (Conservative)</option>
                <option value="medium">Medium (Normal)</option>
                <option value="high">High (Permissive — default for SMC)</option>
              </select>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "4px" }}>
                SMC Desk uses high tolerance by default — long-term trades tolerate wider spreads at entry.
              </div>
            </div>

            {/* --- SMC Spread Thresholds Editor --- */}
            <Show when={smcConfig()?.spread_thresholds}>
              <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
                Spread Thresholds (% of mid price)
              </div>
              {(() => {
                const thresholds = smcConfig()?.spread_thresholds;
                if (!thresholds) return null;
                const levels = ["low", "medium", "high"];
                const classes = ["forex_major", "forex_minor", "metals", "indices", "crypto", "other"];
                return (
                  <div style={{ "overflow-x": "auto", "margin-bottom": "15px" }}>
                    <table style={{ width: "100%", "border-collapse": "collapse", "font-size": "10px" }}>
                      <thead>
                        <tr>
                          <th style={{ padding: "4px 6px", "text-align": "left", color: "var(--text-muted)", "border-bottom": "1px solid var(--border-default)" }}>Level</th>
                          {classes.map(c => <th style={{ padding: "4px 6px", "text-align": "center", color: "var(--text-muted)", "border-bottom": "1px solid var(--border-default)" }}>{c.replace("_", " ")}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {levels.map(level => (
                          <tr>
                            <td style={{ padding: "4px 6px", color: "var(--text-secondary)", "font-weight": "600" }}>{level}</td>
                            {classes.map(cls => (
                              <td style={{ padding: "2px 3px" }}>
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0.001"
                                  value={thresholds[level]?.[cls] ?? 0.10}
                                  onChange={(e) => {
                                    const updated = JSON.parse(JSON.stringify(thresholds));
                                    updated[level][cls] = Number(e.currentTarget.value);
                                    saveConfig("smc", { spread_thresholds: updated });
                                  }}
                                  style={{ width: "60px", padding: "3px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "3px", "font-size": "9px", "text-align": "center" }}
                                  disabled={saving() === "smc"}
                                />
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </Show>

            <Show when={saving() === "smc"}>
              <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                Saving...
              </div>
            </Show>
          </Show>
        </div>
      </div>

      {/* Fast Desk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">
            <span class="panel-dot" style={{ background: "var(--teal)" }} />
            Fast Desk Configuration
          </div>
          <div style={{ display: "flex", "align-items": "center", gap: "10px" }}>
            <Show when={deskStatus()?.fast_desk?.enabled}>
              <span class="cap-badge live">Active</span>
            </Show>
            <Show when={deskStatus() && !deskStatus()?.fast_desk?.enabled}>
              <span class="cap-badge" style={{ background: "var(--bg-tertiary)", color: "var(--text-muted)" }}>Inactive</span>
            </Show>
            <label style={{ display: "flex", "align-items": "center", gap: "5px", "font-size": "10px", color: "var(--text-secondary)", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={deskStatus()?.fast_desk?.enabled ?? true}
                disabled={saving() === "fast_enabled"}
                onChange={(e) => saveConfig("fast_enabled", { enabled: e.currentTarget.checked })}
              />
              Enabled
            </label>
          </div>
        </div>
        <div class="panel-body">
          <Show when={fastConfig()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading Fast config…</div>}>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Scan Interval: {fastConfig()?.scan_interval ?? "—"}s
              </label>
              <input
                type="range"
                min="1"
                max="60"
                step="1"
                value={fastConfig()?.scan_interval || 5}
                onChange={(e) => saveConfig("fast", { scan_interval: Number(e.currentTarget.value) })}
                style={{ width: "100%" }}
                disabled={saving() === "fast"}
              />
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Risk % per Trade: {fastConfig()?.risk_per_trade_percent ?? "—"}%
              </label>
              <input
                type="range"
                min="0.1"
                max="5"
                step="0.1"
                value={fastConfig()?.risk_per_trade_percent || 1.0}
                onChange={(e) => saveConfig("fast", { risk_per_trade_percent: Number(e.currentTarget.value) })}
                style={{ width: "100%" }}
                disabled={saving() === "fast"}
              />
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Max Positions Total: {fastConfig()?.max_positions_total ?? "—"}
              </label>
              <input
                type="number"
                min="1"
                max="20"
                value={fastConfig()?.max_positions_total || 4}
                onChange={(e) => saveConfig("fast", { max_positions_total: Number(e.currentTarget.value) })}
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                disabled={saving() === "fast"}
              />
            </div>

            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Desk RR Ratio: {fastConfig()?.rr_ratio ?? "—"}
              </label>
              <input
                type="range"
                min="1"
                max="6"
                step="0.1"
                value={fastConfig()?.rr_ratio || 3.0}
                onChange={(e) => saveConfig("fast", { rr_ratio: Number(e.currentTarget.value) })}
                style={{ width: "100%" }}
                disabled={saving() === "fast"}
              />
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "4px" }}>
                Single RR source of truth for the entire Fast Desk. This same value governs target multiple and minimum accepted RR, so the desk never runs with conflicting RR thresholds.
              </div>
            </div>
            
            {/* --- Spread Tolerance --- */}
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Spread Tolerance: {fastConfig()?.spread_tolerance ?? "medium"}
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                value={fastConfig()?.spread_tolerance || "medium"}
                onChange={(e) => saveConfig("fast", { spread_tolerance: e.currentTarget.value })}
                disabled={saving() === "fast"}
              >
                <option value="low">Low (Conservative)</option>
                <option value="medium">Medium (Normal)</option>
                <option value="high">High (Aggressive)</option>
              </select>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "4px" }}>
                Per-asset-class spread filtering. Low rejects wider spreads, High allows operation with wider spreads.
              </div>
            </div>

            {/* --- Fast Spread Thresholds Editor --- */}
            <Show when={fastConfig()?.spread_thresholds}>
              <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
                Spread Thresholds (% of mid price)
              </div>
              {(() => {
                const thresholds = fastConfig()?.spread_thresholds;
                if (!thresholds) return null;
                const levels = ["low", "medium", "high"];
                const classes = ["forex_major", "forex_minor", "metals", "indices", "crypto", "other"];
                return (
                  <div style={{ "overflow-x": "auto", "margin-bottom": "15px" }}>
                    <table style={{ width: "100%", "border-collapse": "collapse", "font-size": "10px" }}>
                      <thead>
                        <tr>
                          <th style={{ padding: "4px 6px", "text-align": "left", color: "var(--text-muted)", "border-bottom": "1px solid var(--border-default)" }}>Level</th>
                          {classes.map(c => <th style={{ padding: "4px 6px", "text-align": "center", color: "var(--text-muted)", "border-bottom": "1px solid var(--border-default)" }}>{c.replace("_", " ")}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {levels.map(level => (
                          <tr>
                            <td style={{ padding: "4px 6px", color: "var(--text-secondary)", "font-weight": "600" }}>{level}</td>
                            {classes.map(cls => (
                              <td style={{ padding: "2px 3px" }}>
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0.001"
                                  value={thresholds[level]?.[cls] ?? 0.10}
                                  onChange={(e) => {
                                    const updated = JSON.parse(JSON.stringify(thresholds));
                                    updated[level][cls] = Number(e.currentTarget.value);
                                    saveConfig("fast", { spread_thresholds: updated });
                                  }}
                                  style={{ width: "60px", padding: "3px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "3px", "font-size": "9px", "text-align": "center" }}
                                  disabled={saving() === "fast"}
                                />
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </Show>

            {/* --- Allowed Sessions --- */}
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Allowed Market Sessions
              </label>
              <div style={{ display: "flex", "flex-wrap": "wrap", gap: "8px" }}>
                {(() => {
                  const sessions = fastConfig()?.allowed_sessions || ["london", "overlap", "new_york"];
                  const isGlobal = sessions.includes("global");
                  const options = [
                    { value: "global", label: "Global (24h)" },
                    { value: "all_markets", label: "All Markets" },
                    { value: "tokyo", label: "Tokyo" },
                    { value: "london", label: "London" },
                    { value: "overlap", label: "Overlap" },
                    { value: "new_york", label: "New York" },
                  ];
                  return options.map((opt) => (
                    <label style={{ display: "flex", "align-items": "center", gap: "4px", "font-size": "10px", color: "var(--text-primary)", opacity: isGlobal && opt.value !== "global" ? "0.4" : "1" }}>
                      <input
                        type="checkbox"
                        checked={sessions.includes(opt.value)}
                        disabled={saving() === "fast" || (isGlobal && opt.value !== "global")}
                        onChange={(e) => {
                          let next: string[];
                          if (opt.value === "global") {
                            next = e.currentTarget.checked ? ["global"] : ["london", "overlap", "new_york"];
                          } else if (opt.value === "all_markets") {
                            next = e.currentTarget.checked
                              ? ["all_markets", "tokyo", "london", "overlap", "new_york"]
                              : sessions.filter((s: string) => s !== "all_markets");
                          } else {
                            const cur = new Set<string>(sessions.filter((s: string) => s !== "all_markets"));
                            if (e.currentTarget.checked) cur.add(opt.value); else cur.delete(opt.value);
                            next = Array.from(cur);
                          }
                          if (next.length === 0) next = ["london", "overlap", "new_york"];
                          saveConfig("fast", { allowed_sessions: next });
                        }}
                      />
                      {opt.label}
                    </label>
                  ));
                })()}
              </div>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "6px", padding: "6px 8px", background: "var(--bg-tertiary)", "border-radius": "4px" }}>
                ℹ️ Session filtering applies to Fast Desk only. SMC Desk operates globally — only restricted by symbol trading hours.
              </div>
            </div>

            <Show when={saving() === "fast"}>
              <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                Saving...
              </div>
            </Show>
          </Show>
        </div>
      </div>

      {/* Ownership Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">
            <span class="panel-dot" style={{ background: "var(--green)" }} />
            Ownership Configuration
          </div>
          <Show when={ownershipConfig()}>
            <span class="cap-badge live">Live</span>
          </Show>
        </div>
        <div class="panel-body">
          <Show when={ownershipConfig()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading Ownership config…</div>}>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "flex", "align-items": "center", gap: "8px", "font-size": "11px", color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={ownershipConfig()?.auto_adopt_foreign ?? true}
                  onChange={(e) => saveConfig("ownership", { auto_adopt_foreign: e.currentTarget.checked })}
                  disabled={saving() === "ownership"}
                />
                Auto-adopt Foreign Positions
              </label>
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                History Retention (days): {ownershipConfig()?.history_retention_days ?? "—"}
              </label>
              <input
                type="number"
                min="7"
                max="365"
                value={ownershipConfig()?.history_retention_days || 30}
                onChange={(e) => saveConfig("ownership", { history_retention_days: Number(e.currentTarget.value) })}
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                disabled={saving() === "ownership"}
              />
            </div>
            
            <Show when={saving() === "ownership"}>
              <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                Saving...
              </div>
            </Show>
          </Show>
        </div>
      </div>

      {/* Risk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">
            <span class="panel-dot" style={{ background: "var(--amber)" }} />
            Risk Configuration
          </div>
          <Show when={riskConfig()}>
            <span class="cap-badge live">Live</span>
          </Show>
        </div>
        <div class="panel-body">
          <Show when={riskConfig()} fallback={<div style={{ "font-size": "9px", color: "var(--text-muted)" }}>Loading Risk config…</div>}>
            {/* --- Profiles --- */}
            <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
              Profiles
            </div>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Global Profile: {riskConfig()?.profile_global ?? "—"}
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                value={riskConfig()?.profile_global || 2}
                onChange={(e) => saveConfig("risk", { profile_global: Number(e.currentTarget.value) })}
                disabled={saving() === "risk"}
              >
                <option value="1">1 - Low</option>
                <option value="2">2 - Medium</option>
                <option value="3">3 - High</option>
                <option value="4">4 - Chaos</option>
              </select>
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Fast Desk Profile: {riskConfig()?.profile_fast ?? "—"}
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                value={riskConfig()?.profile_fast || 2}
                onChange={(e) => saveConfig("risk", { profile_fast: Number(e.currentTarget.value) })}
                disabled={saving() === "risk"}
              >
                <option value="1">1 - Low</option>
                <option value="2">2 - Medium</option>
                <option value="3">3 - High</option>
                <option value="4">4 - Chaos</option>
              </select>
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                SMC Desk Profile: {riskConfig()?.profile_smc ?? "—"}
              </label>
              <select
                style={{ width: "100%", padding: "8px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "4px" }}
                value={riskConfig()?.profile_smc || 2}
                onChange={(e) => saveConfig("risk", { profile_smc: Number(e.currentTarget.value) })}
                disabled={saving() === "risk"}
              >
                <option value="1">1 - Low</option>
                <option value="2">2 - Medium</option>
                <option value="3">3 - High</option>
                <option value="4">4 - Chaos</option>
              </select>
            </div>

            {/* --- Budget Allocation — Dynamic Sliders --- */}
            <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "margin-top": "10px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
              Budget Allocation
            </div>
            
            {/* Quick Mode — Single Percentage Slider */}
            <div class="form-group" style={{ "margin-bottom": "20px", padding: "12px", background: "var(--bg-tertiary)", "border-radius": "6px" }}>
              <label style={{ display: "block", "margin-bottom": "8px", "font-size": "11px", color: "var(--text-secondary)", "font-weight": "600" }}>
                Quick Mode — Budget Split (Fast ←→ SMC)
              </label>
              <div style={{ display: "flex", "align-items": "center", gap: "12px" }}>
                <span style={{ "font-size": "10px", color: "var(--teal)", "min-width": "80px", "text-align": "right" }}>
                  Fast: {((riskConfig()?.allocator?.share_fast ?? 0) * 100).toFixed(0)}%
                </span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={Math.round((riskConfig()?.allocator?.share_fast ?? 0.6) * 100)}
                  onChange={(e) => {
                    const fastPercent = Number(e.currentTarget.value) / 100;
                    const smcPercent = 1 - fastPercent;
                    // Convert percentage to weights (range 0.1-3.0)
                    const fastWeight = 0.1 + (fastPercent * 2.9);
                    const smcWeight = 0.1 + (smcPercent * 2.9);
                    saveConfig("risk", { 
                      fast_budget_weight: fastWeight, 
                      smc_budget_weight: smcWeight
                    });
                  }}
                  style={{ flex: "1", height: "6px" }}
                  disabled={saving() === "risk"}
                />
                <span style={{ "font-size": "10px", color: "var(--blue)", "min-width": "80px" }}>
                  SMC: {((riskConfig()?.allocator?.share_smc ?? 0) * 100).toFixed(0)}%
                </span>
              </div>
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "6px", "text-align": "center" }}>
                Drag to adjust budget split — affects both desks dynamically
              </div>
            </div>
            
            {/* Advanced Mode — Individual Weight Sliders */}
            <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px" }}>
              Advanced Mode — Individual Weights
            </div>
            
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                Fast Budget Weight: {(riskConfig()?.fast_budget_weight ?? 1.2).toFixed(2)}
              </label>
              <input
                type="range"
                min="0.1"
                max="3.0"
                step="0.1"
                value={riskConfig()?.fast_budget_weight ?? 1.2}
                onChange={(e) => {
                  const fastWeight = Number(e.currentTarget.value);
                  const smcWeight = riskConfig()?.smc_budget_weight ?? 0.8;
                  // Calculate percentage from weights
                  const total = fastWeight + smcWeight;
                  const fastPercent = Math.round((fastWeight / total) * 100);
                  saveConfig("risk", { fast_budget_weight: fastWeight });
                }}
                style={{ width: "100%" }}
                disabled={saving() === "risk"}
              />
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "4px" }}>
                Range: 0.1 (minimum) to 3.0 (maximum weight)
              </div>
            </div>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "block", "margin-bottom": "5px", "font-size": "11px", color: "var(--text-secondary)" }}>
                SMC Budget Weight: {(riskConfig()?.smc_budget_weight ?? 0.8).toFixed(2)}
              </label>
              <input
                type="range"
                min="0.1"
                max="3.0"
                step="0.1"
                value={riskConfig()?.smc_budget_weight ?? 0.8}
                onChange={(e) => {
                  const smcWeight = Number(e.currentTarget.value);
                  const fastWeight = riskConfig()?.fast_budget_weight ?? 1.2;
                  // Calculate percentage from weights
                  const total = fastWeight + smcWeight;
                  const fastPercent = Math.round((fastWeight / total) * 100);
                  saveConfig("risk", { smc_budget_weight: smcWeight });
                }}
                style={{ width: "100%" }}
                disabled={saving() === "risk"}
              />
              <div style={{ "font-size": "9px", color: "var(--text-muted)", "margin-top": "4px" }}>
                Range: 0.1 (minimum) to 3.0 (maximum weight)
              </div>
            </div>
            <Show when={riskConfig()?.allocator}>
              <div style={{ padding: "8px", background: "var(--bg-tertiary)", "border-radius": "4px", "margin-bottom": "15px" }}>
                <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-secondary)", "margin-bottom": "4px" }}>Computed Allocation</div>
                <div style={{ display: "flex", gap: "20px", "font-size": "11px", color: "var(--text-primary)" }}>
                  <span>Fast Share: {((riskConfig()?.allocator?.share_fast ?? 0) * 100).toFixed(1)}%</span>
                  <span>SMC Share: {((riskConfig()?.allocator?.share_smc ?? 0) * 100).toFixed(1)}%</span>
                </div>
              </div>
            </Show>

            {/* --- Effective Limits + Overrides --- */}
            <Show when={riskConfig()?.effective_limits}>
              <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "margin-top": "10px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
                Effective Limits <span style={{ "font-weight": "normal", color: "var(--text-muted)" }}>(Global overrides editable)</span>
              </div>
              {(() => {
                const limits = riskConfig()?.effective_limits;
                const overrides = riskConfig()?.overrides || {};
                if (!limits) return null;
                const overrideFields = [
                  { key: "max_drawdown_pct", label: "Max Drawdown %", step: 0.5 },
                  { key: "max_risk_per_trade_pct", label: "Max Risk/Trade %", step: 0.05 },
                  { key: "max_positions_total", label: "Max Positions", step: 1 },
                  { key: "max_positions_per_symbol", label: "Max Per Symbol", step: 1 },
                  { key: "max_pending_orders_total", label: "Max Pending", step: 1 },
                  { key: "max_gross_exposure", label: "Max Gross Exp", step: 0.5 },
                ];
                const renderLimits = (label: string, data: any, color: string) => (
                  <div style={{ padding: "8px", background: "var(--bg-tertiary)", "border-radius": "4px", "margin-bottom": "8px", "border-left": `3px solid ${color}` }}>
                    <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-secondary)", "margin-bottom": "4px" }}>{label}</div>
                    <div style={{ display: "grid", "grid-template-columns": "1fr 1fr", gap: "2px 12px", "font-size": "10px", color: "var(--text-primary)" }}>
                      <span>Max Drawdown: {data?.max_drawdown_pct ?? "—"}%</span>
                      <span>Max Risk/Trade: {data?.max_risk_per_trade_pct ?? "—"}%</span>
                      <span>Max Positions: {data?.max_positions_total ?? "—"}</span>
                      <span>Max Per Symbol: {data?.max_positions_per_symbol ?? "—"}</span>
                      <span>Max Pending: {data?.max_pending_orders_total ?? "—"}</span>
                      <span>Max Gross Exp: {data?.max_gross_exposure ?? "—"}</span>
                    </div>
                  </div>
                );
                return (
                  <>
                    {/* Global overrides — editable */}
                    <div style={{ padding: "8px", background: "var(--bg-tertiary)", "border-radius": "4px", "margin-bottom": "8px", "border-left": "3px solid var(--amber)" }}>
                      <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-secondary)", "margin-bottom": "6px" }}>Global Overrides</div>
                      <div style={{ display: "grid", "grid-template-columns": "1fr 1fr", gap: "6px 12px" }}>
                        {overrideFields.map(f => (
                          <div>
                            <label style={{ "font-size": "9px", color: "var(--text-muted)", display: "block", "margin-bottom": "2px" }}>{f.label}</label>
                            <input
                              type="number"
                              step={f.step}
                              min="0"
                              value={overrides[f.key] ?? limits.global?.[f.key] ?? ""}
                              onChange={(e) => {
                                const val = Number(e.currentTarget.value);
                                if (val > 0) saveConfig("risk", { overrides: { [f.key]: val } });
                              }}
                              style={{ width: "100%", padding: "4px 6px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", "border-radius": "3px", "font-size": "10px" }}
                              disabled={saving() === "risk"}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                    {/* Desk limits — computed, read-only */}
                    {renderLimits("Fast Desk (computed)", limits.desks?.fast, "var(--teal)")}
                    {renderLimits("SMC Desk (computed)", limits.desks?.smc, "var(--blue)")}
                  </>
                );
              })()}
            </Show>

            {/* --- Safety --- */}
            <div style={{ "font-size": "10px", "font-weight": "600", color: "var(--text-primary)", "margin-bottom": "8px", "margin-top": "10px", "border-bottom": "1px solid var(--border-default)", "padding-bottom": "4px" }}>
              Safety
            </div>
            <div class="form-group" style={{ "margin-bottom": "15px" }}>
              <label style={{ display: "flex", "align-items": "center", gap: "8px", "font-size": "11px", color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={riskConfig()?.kill_switch_enabled ?? true}
                  onChange={(e) => saveConfig("risk", { kill_switch_enabled: e.currentTarget.checked })}
                  disabled={saving() === "risk"}
                />
                Kill Switch Enabled
              </label>
            </div>
            
            <Show when={saving() === "risk"}>
              <div style={{ "font-size": "9px", color: "var(--text-muted)" }}>
                Saving...
              </div>
            </Show>
          </Show>
        </div>
      </div>

      {/* Persistence Notice */}
      <div style={{ margin: "20px 0", padding: "15px", background: "rgba(210, 153, 34, 0.1)", border: "1px solid var(--amber)", "border-radius": "6px" }}>
        <p style={{ "font-size": "11px", color: "var(--amber)", "line-height": "1.5", margin: 0 }}>
          ⚠️ <strong>Note:</strong> Changes are persisted to the database and survive restarts. 
          The <code style={{ background: "var(--bg-tertiary)", padding: "2px 6px", "border-radius": "3px" }}>.env</code> file values are used only as initial defaults when no database state exists.
        </p>
      </div>
    </div>
  );
};

export default Settings;
