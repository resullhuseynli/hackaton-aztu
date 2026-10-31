import react from "@vitejs/plugin-react";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

/** Vite config shared by both apps: same backend proxy, each app on its own fixed port. */
export function transitConfig(port) {
  const server = {
    port,
    strictPort: true,
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  };
  return { plugins: [react()], server, preview: server };
}
