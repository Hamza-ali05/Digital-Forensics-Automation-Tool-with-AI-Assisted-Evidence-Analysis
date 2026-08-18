// @ts-check
const path = require("path");
const { defineConfig, devices } = require("@playwright/test");

const repoRoot = path.resolve(__dirname, "..");
const isCI = Boolean(process.env.CI);
// Allow reusing local servers unless explicitly disabled (Cursor shells often set CI=true).
const reuseServer = process.env.PW_NO_REUSE !== "1";

/**
 * Playwright E2E — critical DFAT workflows against live backend + frontend.
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: isCI,
  retries: 1,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: require.resolve("./e2e/global-setup.js"),
  use: {
    // 127.0.0.1 avoids Windows IPv6 `localhost` (::1) vs CRA IPv4 bind mismatch.
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000",
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: reuseServer,
      timeout: 120_000,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, "src"),
        DFAT_E2E_SOFT_ACQUIRE: "1",
      },
    },
    {
      command: "npm start",
      cwd: __dirname,
      url: "http://127.0.0.1:3000",
      reuseExistingServer: reuseServer,
      timeout: 300_000,
      env: {
        ...process.env,
        // CRA 3 exits on stdin EOF unless CI is exactly "true".
        CI: "true",
        BROWSER: "none",
        HOST: "127.0.0.1",
        PORT: "3000",
        SKIP_PREFLIGHT_CHECK: "true",
        NODE_OPTIONS: "--openssl-legacy-provider",
        REACT_APP_API_BASE_URL: "http://127.0.0.1:8000/api/v1",
      },
    },
  ],
});
