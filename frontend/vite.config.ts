import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react()],
  server: {
    // API_PROXY points the dev server at another backend, e.g. a second local copy.
    proxy: { "/api": process.env.API_PROXY ?? "http://localhost:8000" },
  },
});
