import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Proxy /api to Django so the browser sees one origin (localhost:5173) and
// session + CSRF cookies work without cross-site issues. Override the
// target when the backend isn't reachable at localhost -- e.g. the
// docker-compose frontend service points this at the `backend` container.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

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
  },
});
