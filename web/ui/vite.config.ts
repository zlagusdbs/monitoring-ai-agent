import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 빌드 결과는 FastAPI 가 그대로 서빙한다.
export default defineConfig({
  plugins: [react()],
  // FastAPI 가 /static 에 붙여 서빙한다.
  base: "/static/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8787",
      "/ws": { target: "ws://127.0.0.1:8787", ws: true },
    },
  },
});
