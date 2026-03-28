import { createStore } from "solid-js/store";
import { onCleanup } from "solid-js";
import type {
  PositionRow,
  OrderRow,
  ExposureState,
  AccountPayload,
} from "../types/api";
import { api } from "../api/client";

interface OperationsStore {
  positions: PositionRow[];
  orders: OrderRow[];
  exposure: ExposureState | null;
  account: AccountPayload | null;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

const [state, setState] = createStore<OperationsStore>({
  positions: [],
  orders: [],
  exposure: null,
  account: null,
  loading: false,
  error: null,
  lastUpdated: null,
});

export { state as operationsStore };

let _positionsPollId: ReturnType<typeof setInterval> | null = null;
let _accountPollId: ReturnType<typeof setInterval> | null = null;

async function pollPositions() {
  try {
    const { positions, orders } = await api.positions();
    setState("positions", positions ?? []);
    setState("orders", orders ?? []);
    setState("error", null);
    setState("lastUpdated", new Date().toISOString());
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "positions poll failed");
  }
}

async function pollAccount() {
  try {
    const payload = await api.account();
    setState("account", payload);
    setState("exposure", (payload.exposure_state as ExposureState) ?? null);
    setState("error", null);
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "account poll failed");
  }
}

export function initOperationsStore() {
  void pollPositions();
  void pollAccount();

  _positionsPollId = setInterval(pollPositions, 3_000);
  _accountPollId = setInterval(pollAccount, 5_000);

  onCleanup(() => {
    if (_positionsPollId !== null) clearInterval(_positionsPollId);
    if (_accountPollId !== null) clearInterval(_accountPollId);
  });
}
