import { defineConfig } from "@playwright/test";

const chromiumExecutablePath = process.env.E2E_CHROMIUM_EXECUTABLE_PATH;

/**
 * The e2e test runs against the composed stack (docker compose up). Point it
 * with E2E_BASE_URL / E2E_API_URL; defaults match the compose port mappings.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    launchOptions: chromiumExecutablePath
      ? { executablePath: chromiumExecutablePath }
      : undefined,
  },
});
