import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// La API se sirve en el mismo origen (/api). En local, Vite la reenvía a FastAPI,
// así que no hace falta abrir CORS; en Google Cloud lo resuelve el balanceador.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: env.API_PROXY_TARGET || "http://localhost:8000", changeOrigin: true },
      },
    },
    build: { sourcemap: false, chunkSizeWarningLimit: 1600 },
  };
});
