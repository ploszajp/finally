import { defineConfig, devices } from '@playwright/test';

/**
 * FinAlly E2E configuration.
 *
 * BASE_URL points at a running app (default http://localhost:8000).
 * In docker-compose.test.yml it is http://finally-app:8000.
 *
 * The app is single-user with shared server state, so tests run serially
 * in one worker, in file-name order (01-, 02-, ...). 01-fresh-start must
 * run against a fresh database.
 */
const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    viewport: { width: 1600, height: 1000 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } } }],
});
