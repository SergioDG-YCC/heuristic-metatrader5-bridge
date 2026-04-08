/**
 * SMC Desk operations store — authoritative source for SMC desk positions and orders.
 *
 * Polls /api/v1/smc/operations which returns only desk_owner=="smc" and
 * smc_owned tickets.  FAST and inherited tickets are never included.
 *
 * Use operationsStore (global) only for audit / ownership console views.
 */
import { createStore } from "solid-js/store";
import { onCleanup } from "solid-js";
import type { PositionRow, OrderRow } from "../types/api";
import { api } from "../api/client";

interface SmcOperationsStore {
  positions: PositionRow[];
  orders: OrderRow[];
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

const [state, setState] = createStore<SmcOperationsStore>({
  positions: [],
  orders: [],
  loading: false,
  error: null,
  lastUpdated: null,
});

export { state as smcOperationsStore };

let _pollId: ReturnType<typeof setInterval> | null = null;

async function pollSmcOperations() {
  try {
    const { positions, orders, updated_at } = await api.smcOperations();
    setState("positions", positions ?? []);
    setState("orders", orders ?? []);
    setState("error", null);
    setState("lastUpdated", updated_at ?? new Date().toISOString());
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "smc operations poll failed");
  }
}

export function initSmcOperationsStore() {
  setState("loading", true);
  void pollSmcOperations().finally(() => setState("loading", false));
  _pollId = setInterval(pollSmcOperations, 3_000);
  onCleanup(() => {
    if (_pollId !== null) clearInterval(_pollId);
  });
}
