import { expect, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
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

test("user dashboard shows the signal and its execution status", async ({ page, request }) => {
  // 1. Seed one signal through the real webhook ingress.
  const post = await request.post(`${API_URL}/webhook/tradingview`, {
    headers: { "X-Webhook-Token": WEBHOOK_TOKEN, "Content-Type": "application/json" },
    data: SAMPLE_SIGNAL,
  });
  expect(post.ok()).toBeTruthy();

  // 2. Sign in as a USER.
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in as USER" }).click();
  await page.waitForURL("**/dashboard");

  await expect(page.getByTestId("identity-role")).toHaveText("USER");

  // 3. The signal appears (poll: the worker fan-out is async).
  const signalCell = page.getByRole("cell", { name: SAMPLE_SIGNAL.signal_id });
  await expect(signalCell).toBeVisible({ timeout: 20_000 });

  // 4. An execution row reaches a terminal-ish state.
  await expect
    .poll(
      async () => {
        await page.reload();
        return page.getByTestId("execution-state").first().textContent();
      },
      { timeout: 20_000, intervals: [1000] },
    )
    .toMatch(/FILLED|ACKNOWLEDGED|RECONCILED/);
});

test("a USER cannot reach the super-admin dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in as USER" }).click();
  await page.waitForURL("**/dashboard");

  await page.goto("/admin");
  // middleware bounces the USER back to /dashboard.
  await page.waitForURL("**/dashboard");
  await expect(page.getByRole("heading", { name: "User dashboard" })).toBeVisible();
});
