/** Heatmap and P&L chart (PLAN.md §12 "Portfolio visualization"). */
import { expect, test } from '@playwright/test';
import { T, apiTrade, closeAllPositions, ensureOnWatchlist, heatmapCell, heatmapCells, openApp } from './selectors';

test.describe('portfolio visualization', () => {
  test.beforeEach(async ({ request }) => {
    await closeAllPositions(request);
    await ensureOnWatchlist(request, 'AAPL');
    await ensureOnWatchlist(request, 'V');
    // Very different weights so tile sizes are clearly ordered.
    await apiTrade(request, 'AAPL', 10, 'buy');
    await apiTrade(request, 'V', 1, 'buy');
  });

  test('heatmap has one tile per position, sized by weight, coloured by P&L', async ({ page }) => {
    await openApp(page);
    const heatmap = page.getByTestId(T.heatmap);
    await expect(heatmap).toBeVisible();
    await expect(heatmapCells(page)).toHaveCount(2);
    await expect(page.getByTestId(T.heatmapEmpty)).toHaveCount(0);

    const aapl = heatmapCell(page, 'AAPL');
    const v = heatmapCell(page, 'V');
    await expect(aapl).toBeVisible();
    await expect(v).toBeVisible();

    const area = async (tile: typeof aapl) => {
      const box = await tile.boundingBox();
      expect(box).not.toBeNull();
      return box!.width * box!.height;
    };
    expect(await area(aapl)).toBeGreaterThan(await area(v));

    // Colour matches the tile's own P&L sign, read in one go so a live tick
    // cannot flip the sign between the two reads.
    for (const tile of [aapl, v]) {
      const { pnl, rgb } = await tile.evaluate((el) => {
        const m = getComputedStyle(el).backgroundColor.match(/\d+(\.\d+)?/g) ?? [];
        return { pnl: el.getAttribute('data-pnl'), rgb: m.slice(0, 3).map(Number) };
      });
      expect(['positive', 'negative', 'flat']).toContain(pnl);
      const [r, g] = rgb;
      if (pnl === 'positive') expect(g, `green tile for profit, got rgb(${rgb})`).toBeGreaterThan(r);
      if (pnl === 'negative') expect(r, `red tile for loss, got rgb(${rgb})`).toBeGreaterThan(g);
    }
  });

  test('heatmap is empty when nothing is held', async ({ page, request }) => {
    await closeAllPositions(request);
    await openApp(page);
    await expect(heatmapCells(page)).toHaveCount(0);
    await expect(page.getByTestId(T.heatmapEmpty)).toBeVisible();
  });

  test('P&L chart renders snapshot data', async ({ page, request }) => {
    const r = await request.get('/api/portfolio/history');
    expect(r.status()).toBe(200);
    const { snapshots } = await r.json();
    // Startup snapshot plus one per trade.
    expect(snapshots.length).toBeGreaterThanOrEqual(3);

    await openApp(page);
    const chart = page.getByTestId(T.pnlChart);
    await expect(chart).toBeVisible();
    await expect.poll(async () => Number(await chart.getAttribute('data-points'))).toBeGreaterThanOrEqual(3);
    await expect(chart.locator('canvas, svg').first()).toBeVisible();
    const box = await chart.boundingBox();
    expect(box!.width).toBeGreaterThan(100);
    expect(box!.height).toBeGreaterThan(50);
  });
});
