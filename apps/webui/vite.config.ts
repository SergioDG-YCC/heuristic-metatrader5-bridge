import { defineConfig } from "vite";
import solidPlugin from "vite-plugin-solid";

export default defineConfig({
  plugins: [solidPlugin()],
  server: {
    host: "0.0.0.0", // Expose on LAN
    port: 5173,
    proxy: {
      // Legacy endpoints (no prefix)
      "/status": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/chart": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/specs": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/account": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/positions": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/exposure": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/catalog": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/subscribe": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/unsubscribe": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/events": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        ws: false,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache";
          });
        },
      },
      // Ownership endpoints
      "/ownership": { target: "http://127.0.0.1:8765", changeOrigin: true },
      // Risk endpoints
      "/risk": { target: "http://127.0.0.1:8765", changeOrigin: true },
      // Phase 2+ API v1 endpoints
      "/api/v1/llm": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/config": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/feed-health": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/desk-status": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/fast": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/smc": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/symbols": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/v1/correlation": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache, no-store, max-age=0";
            proxyRes.headers.pragma = "no-cache";
            proxyRes.headers.expires = "0";
          });
        },
      },
    },
  },
  build: {
    target: "esnext",
  },
});
