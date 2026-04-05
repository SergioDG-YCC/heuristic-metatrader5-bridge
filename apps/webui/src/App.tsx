import type { Component, JSXElement } from "solid-js";
import { Show } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { GlobalStatusStrip } from "./components/GlobalStatusStrip";
import { AppNav } from "./components/AppNav";
import { BootOverlay } from "./components/BootOverlay";
import { runtimeStore, initRuntimeStore } from "./stores/runtimeStore";

// Screen imports
import RuntimeOverview from "./routes/RuntimeOverview";
import Operations from "./routes/Operations";
import Terminal from "./routes/Terminal";
import Alerts from "./routes/Alerts";
import Risk from "./routes/Risk";
import FastDesk from "./routes/FastDesk";
import FastPipeline from "./routes/FastPipeline";
import SmcDesk from "./routes/SmcDesk";
import Ownership from "./routes/Ownership";
import Mode from "./routes/Mode";
import Settings from "./routes/Settings";
import Symbols from "./routes/Symbols";
import Correlation from "./routes/Correlation";

import "./styles/global.css";

// Root layout component — receives the active route content as props.children
// This is the correct @solidjs/router v0.15 pattern using the `root` prop
function AppLayout(props: { children?: JSXElement }) {
  // Initialize global stores once at app root
  initRuntimeStore();

  return (
    <>
      {/* Boot overlay — shown until /status responds and bootState = "ready" */}
      <Show when={runtimeStore.bootState !== "ready"}>
        <BootOverlay bootState={runtimeStore.bootState} />
      </Show>

      <div
        style={{
          display: "flex",
          "flex-direction": "column",
          height: "100%",
          width: "100%",
          overflow: "hidden",
        }}
      >
        <GlobalStatusStrip />
        <div
          style={{
            display: "flex",
            flex: "1",
            overflow: "hidden",
          }}
        >
          <AppNav />
          <main
            style={{
              flex: "1",
              display: "flex",
              "flex-direction": "column",
              overflow: "hidden",
              background: "var(--bg-base)",
            }}
          >
            {/* Route outlet — rendered by @solidjs/router via root prop */}
            {props.children}
          </main>
        </div>
      </div>
    </>
  );
}

// Routes are flat children of Router; AppLayout wraps the active route outlet
const App: Component = () => (
  <Router root={AppLayout}>
    <Route path="/" component={RuntimeOverview} />
    <Route path="/operations" component={Operations} />
    <Route path="/operations/symbol/:symbol" component={Operations} />
    <Route
      path="/operations/symbol/:symbol/chart/:timeframe"
      component={Operations}
    />
    <Route path="/terminal" component={Terminal} />
    <Route path="/terminal/spec/:symbol" component={Terminal} />
    <Route path="/alerts" component={Alerts} />
    <Route path="/risk" component={Risk} />
    <Route path="/fast" component={FastDesk} />
    <Route path="/fast/pipeline" component={FastPipeline} />
    <Route path="/smc" component={SmcDesk} />
    <Route path="/ownership" component={Ownership} />
    <Route path="/mode" component={Mode} />
    <Route path="/symbols" component={Symbols} />
    <Route path="/settings" component={Settings} />
    <Route path="/correlation" component={Correlation} />
  </Router>
);

export default App;
