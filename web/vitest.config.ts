import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Mirrors tsconfig.json's "@/*": ["./*"] - middleware.ts (and anything
    // else under test) imports via this alias, which tsc/eslint already
    // resolve from tsconfig but Vitest needs told separately.
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
