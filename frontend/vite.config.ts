import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Proxy /api to Django so the browser sees one origin (localhost:5173) and
// session + CSRF cookies work without cross-site issues. Override the
// target when the backend isn't reachable at localhost -- e.g. the
// docker-compose frontend service points this at the `backend` container.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

// Only set inside the docker-compose frontend container (see
// docker-compose.yml). Docker Desktop's bind mount from a Windows host
// doesn't forward real filesystem-change events into the container, so Vite
// never notices an edit without polling -- HMR silently keeps serving stale
// content otherwise. Host-side `npm run dev` doesn't need this at all.
const usePolling = process.env.VITE_WATCH_POLL === "true";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
});
