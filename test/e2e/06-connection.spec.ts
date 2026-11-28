/**
 * Connection status indicator. Replaces the fragile "SSE resilience" scenario
 * (PLAN.md §13 "Uproszczenia"): no server restart, the stream is blocked in
 * the browser instead.
 */
import { expect, test } from '@playwright/test';
import { T, openApp } from './selectors';

test.describe('connection indicator', () => {
  test('is green while the price stream is connected', async ({ page }) => {
    await openApp(page); // waits for data-status="connected"
    const dot = page.getByTestId(T.connection);
    await expect(dot).toBeVisible();
    // The coloured dot is the indicator's first (decorative) child.
    const color = await dot.locator('span').first().evaluate((el) => {
      const m = getComputedStyle(el).backgroundColor.match(/\d+(\.\d+)?/g) ?? [];
      return m.slice(0, 3).map(Number);
    });
    const [r, g, b] = color;
    expect(g, `connected dot should be green, got rgb(${color})`).toBeGreaterThan(r);
    expect(g).toBeGreaterThan(b);
  });

  test('is not "connected" when the price stream cannot be reached', async ({ page }) => {
    await page.route('**/api/stream/prices', (route) => route.abort('connectionrefused'));
    await page.goto('/');
    const dot = page.getByTestId(T.connection);
    await expect(dot).toBeVisible();
    await expect(dot).toHaveAttribute('data-status', /^(reconnecting|disconnected)$/);
    // EventSource keeps retrying; it must never claim to be connected.
    await page.waitForTimeout(3000);
    await expect(dot).not.toHaveAttribute('data-status', 'connected');
  });

  test('recovers to "connected" once the stream is reachable again', async ({ page }) => {
    await page.route('**/api/stream/prices', (route) => route.abort('connectionrefused'));
    await page.goto('/');
    await expect(page.getByTestId(T.connection)).toHaveAttribute('data-status', /^(reconnecting|disconnected)$/);
    await page.unroute('**/api/stream/prices');
    // Native EventSource retry (or the app's own reconnect) brings it back.
    await expect(page.getByTestId(T.connection)).toHaveAttribute('data-status', 'connected', { timeout: 20_000 });
  });
});
