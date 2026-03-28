import { createStore } from "solid-js/store";
import { onCleanup } from "solid-js";
import type {
  AccountPayload,
  CatalogEntry,
  SymbolSpec,
} from "../types/api";
import { api } from "../api/client";

interface TerminalStore {
  account: AccountPayload | null;
  catalog: CatalogEntry[];
  specs: Record<string, SymbolSpec>;
  selectedSpec: SymbolSpec | null;
  loading: boolean;
  error: string | null;
}

const [state, setState] = createStore<TerminalStore>({
  account: null,
  catalog: [],
  specs: {},
  selectedSpec: null,
  loading: false,
  error: null,
});

export { state as terminalStore };

let _pollId: ReturnType<typeof setInterval> | null = null;

async function loadCatalog() {
  try {
    const resp = await api.catalog();
    setState("catalog", resp.symbols ?? []);
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "catalog load failed");
  }
}

async function loadSpecs() {
  try {
    const resp = await api.specs();
    setState("specs", resp ?? {});
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "specs load failed");
  }
}

async function pollAccount() {
  try {
    const payload = await api.account();
    setState("account", payload);
    setState("error", null);
  } catch (e) {
    setState("error", e instanceof Error ? e.message : "account poll failed");
  }
}

export async function loadSpec(symbol: string): Promise<void> {
  try {
    const spec = await api.spec(symbol);
    setState("selectedSpec", spec);
  } catch (e) {
    setState("error", e instanceof Error ? e.message : `spec load failed: ${symbol}`);
  }
}

export function initTerminalStore() {
  setState("loading", true);
  Promise.all([loadCatalog(), loadSpecs(), pollAccount()]).finally(() => {
    setState("loading", false);
  });

  _pollId = setInterval(pollAccount, 10_000);

  onCleanup(() => {
    if (_pollId !== null) clearInterval(_pollId);
  });
}
