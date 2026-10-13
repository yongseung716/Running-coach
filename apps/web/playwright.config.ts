import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure" },
  projects: [{ name: "mobile-chromium", use: { ...devices["Pixel 7"] } }, { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "python ../../scripts/serve-api.py", url: "http://127.0.0.1:8000/health", timeout: 60000, reuseExistingServer: !process.env.CI,
      env: { MODE: "test", DATABASE_URL: "sqlite:///./data/e2e/coach.db", DATA_DIR: "./data/e2e", ALLOWED_ORIGINS: "http://localhost:3000" } },
    { command: "npm run dev", url: "http://localhost:3000", timeout: 60000, reuseExistingServer: !process.env.CI,
      env: { API_INTERNAL_URL: "http://127.0.0.1:8000" } }
  ]
});
