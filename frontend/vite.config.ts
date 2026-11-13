import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({plugins:[react()],build:{outDir:"../filebridge/web/build",emptyOutDir:true,assetsDir:"assets"},server:{port:5173,strictPort:true}});