import { createStore } from "solid-js/store";
import { onCleanup } from "solid-js";
import type {
  PositionRow,
  OrderRow,
  ExposureState,
  AccountPayload,
  OwnershipItem,
} from "../types/api";
import { api } from "../api/client";

interface OperationsStore {
  positions: PositionRow[];
  orders: OrderRow[];
  exposure: ExposureState | null;
  account: AccountPayload | null;
  ownershipByPositionId: Record<number, OwnershipItem>;
  ownershipByOrderId: Record<number, OwnershipItem>;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

const [state, setState] = createStore<OperationsStore>({
  positions: [],
  orders: [],
  exposure: null,
  account: null,
  ownershipByPositionId: {},
  ownershipByOrderId: {},
  loading: false,
  error: null,
  lastUpdated: null,
});

export { state as operationsStore };

let _positionsPollId: ReturnType<typeof setInterval> | null = null;
let _accountPollId: ReturnType<typeof setInterval> | null = null;
let _ownershipPollId: ReturnType<typeof setInterval> | null = null;

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

async function pollOwnership() {
  try {
    // Merge open + history so that filled/closed orders (recent deals) are
    // also covered by the lookup maps.
    const [open, hist] = await Promise.all([api.ownershipOpen(), api.ownershipHistory()]);
    const byPos: Record<number, OwnershipItem> = {};
    const byOrd: Record<number, OwnershipItem> = {};
    for (const item of [...(open.items ?? []), ...(hist.items ?? [])]) {
      if (item.position_id != null) byPos[item.position_id] = item;
      if (item.order_id != null) byOrd[item.order_id] = item;
    }
    setState("ownershipByPositionId", byPos);
    setState("ownershipByOrderId", byOrd);
  } catch {
    // non-critical — ownership data is best-effort
  }
}

export function initOperationsStore() {
  void pollPositions();
  void pollAccount();
  void pollOwnership();

  _positionsPollId = setInterval(pollPositions, 3_000);
  _accountPollId = setInterval(pollAccount, 5_000);
  _ownershipPollId = setInterval(pollOwnership, 10_000);

  onCleanup(() => {
    if (_positionsPollId !== null) clearInterval(_positionsPollId);
    if (_accountPollId !== null) clearInterval(_accountPollId);
    if (_ownershipPollId !== null) clearInterval(_ownershipPollId);
  });
}
