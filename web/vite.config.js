import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // 部署在阿里云 ECS nginx 的 /doc/ 子路径下（同机 80 端口还跑着 AIPM demo）
  base: process.env.NODE_ENV === "production" ? "/doc/" : "/",
  plugins: [react()],
  server: {
    port: 5175,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8540",
        changeOrigin: true,
        timeout: 180000,
      },
    },
  },
});
