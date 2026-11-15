import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../filebridge/web",
    emptyOutDir: true,
    rollupOptions: { output: { entryFileNames: "assets/app.js", chunkFileNames: "assets/[name]-[hash].js", assetFileNames: "assets/styles.css" } },
  },
  server: { port: 5173, strictPort: true },
});