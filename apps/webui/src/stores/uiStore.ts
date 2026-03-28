import { createStore } from "solid-js/store";

interface UiStore {
  selectedSymbol: string | null;
  selectedTimeframe: string;
  navOpen: boolean;
}

const [state, setState] = createStore<UiStore>({
  selectedSymbol: null,
  selectedTimeframe: "H1",
  navOpen: false,
});

export { state as uiStore };

export function setSelectedSymbol(symbol: string | null) {
  setState("selectedSymbol", symbol);
}

export function setSelectedTimeframe(tf: string) {
  setState("selectedTimeframe", tf);
}

export function toggleNav() {
  setState("navOpen", (prev) => !prev);
}
