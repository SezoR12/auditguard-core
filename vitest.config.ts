/// <reference types="vitest" />
// Standalone Vitest config for component/hook tests.
//
// Intentionally NOT extending vite.config.ts: that file wraps the Lovable
// TanStack Start config (nitro/SSR/cloudflare plugins) which conflicts with the
// jsdom unit-test runner. We only need React + the "@/" alias here.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/components/**", "src/hooks/**", "src/lib/**"],
    },
  },
});
