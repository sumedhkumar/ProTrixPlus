import { expect, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const WEBHOOK_TOKEN = process.env.PROTRIX_WEBHOOK_SHARED_SECRET ?? "dev-webhook-token-change-me";

const SAMPLE_SIGNAL = {
  schema_version: "1.0",
  strategy_key: "trend-rider",
  strategy_version: "2025.09",
  signal_id: `e2e-${Date.now()}`,
  event_time_utc: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  action: "BUY",
  symbol: "EURUSD",
  timeframe: "15m",
  stop_loss: "1.07500",
  take_profit: "1.09000",
};

const SETUP_SIGNAL = {
  ...SAMPLE_SIGNAL,
  signal_id: `e2e-setup-${Date.now()}`,
  action: "SELL",
  stop_loss: "1.09000",
  take_profit: "1.07500",
};

test("user dashboard shows the signal and its execution status", async ({ page, request }) => {
  // 1. Normalize the mock position direction so this test stays repeatable
  // after another local integration run has left a position open.
  const setup = await request.post(`${API_URL}/webhook/tradingview`, {
    headers: { "X-Webhook-Token": WEBHOOK_TOKEN, "Content-Type": "application/json" },
    data: SETUP_SIGNAL,
  });
  expect(setup.ok()).toBeTruthy();

  // 2. Seed the signal under test through the real webhook ingress.
  const post = await request.post(`${API_URL}/webhook/tradingview`, {
    headers: { "X-Webhook-Token": WEBHOOK_TOKEN, "Content-Type": "application/json" },
    data: SAMPLE_SIGNAL,
  });
  expect(post.ok()).toBeTruthy();

  // 3. Sign in as a USER.
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in as Alice Trader" }).click();
  await page.waitForURL("**/dashboard");

  await expect(page.getByTestId("identity-role")).toHaveText("USER");

  // 4. The signal appears in the signals table (worker fan-out is async).
  await expect
    .poll(
      async () => {
        await page.reload();
        return page
          .getByTestId("signals-table")
          .getByRole("cell", { name: SAMPLE_SIGNAL.signal_id })
          .count();
      },
      { timeout: 20_000, intervals: [1000] },
    )
    .toBeGreaterThan(0);

  // 5. Its execution row reaches a terminal-ish state.
  await expect
    .poll(
      async () => {
        await page.reload();
        return page
          .getByTestId("executions-table")
          .locator('[data-testid="execution-state"]')
          .first()
          .textContent();
      },
      { timeout: 20_000, intervals: [1000] },
    )
    .toMatch(/FILLED|ACKNOWLEDGED|RECONCILED/);
});

test("a USER cannot reach the super-admin dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in as Alice Trader" }).click();
  await page.waitForURL("**/dashboard");

  await page.goto("/admin");
  // middleware bounces the USER back to /dashboard.
  await page.waitForURL("**/dashboard");
  await expect(page.getByRole("heading", { name: "User dashboard" })).toBeVisible();
});
