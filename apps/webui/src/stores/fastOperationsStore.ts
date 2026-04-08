/**
 * Fast Desk operations store — authoritative source for FAST desk positions and orders.
 *
 * Polls /api/v1/fast/operations which returns only desk_owner=="fast" and
 * inherited_fast tickets.  SMC tickets are never included.
 *
 * Use operationsStore (global) only for audit / ownership console views.
 */
import { createStore } from "solid-js/store";
import { onCleanup } from "solid-js";
import type { PositionRow, OrderRow } from "../types/api";
import { api } from "../api/client";

interface FastOperationsStore {
  positions: PositionRow[];
  orders: OrderRow[];
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

const [state, setState] = createStore<FastOperationsStore>({
  positions: [],
  orders: [],
  loading: false,
  error: null,
  lastUpdated: null,
});

export { state as fastOperationsStore };

let _pollId: ReturnType<typeof setInterval> | null = null;

async function pollFastOperations() {
  try {
    const { positions, orders, updated_at } = await api.fastOperations();
    setState("positions", positions ?? []);
    setState("orders", orders ?? []);
    setState("error", null);
    setState("lastUpdated", updated_at ?? new Date().toISOString());
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "fast operations poll failed");
  }
}

export function initFastOperationsStore() {
  setState("loading", true);
  void pollFastOperations().finally(() => setState("loading", false));
  _pollId = setInterval(pollFastOperations, 3_000);
  onCleanup(() => {
    if (_pollId !== null) clearInterval(_pollId);
  });
}
