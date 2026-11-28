/**
 * Fresh start (PLAN.md §12): default watchlist, $10,000, prices streaming.
 * Must run first, against a brand-new database.
 */
import { expect, test } from '@playwright/test';
import {
  DEFAULT_TICKERS,
  T,
  TT,
  expectMoney,
  getPortfolio,
  openApp,
  parseNumber,
  positionRows,
  watchlistPrices,
  watchlistRow,
  watchlistRows,
} from './selectors';

test.describe('fresh start', () => {
  test.beforeEach(async ({ page }) => {
    await openApp(page);
  });

  test('shows the ten default tickers in seed order', async ({ page }) => {
    const rows = watchlistRows(page);
    await expect(rows).toHaveCount(DEFAULT_TICKERS.length);
    const tickers = await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-ticker')));
    expect(tickers).toEqual(DEFAULT_TICKERS);
  });

  test('shows $10,000 cash and total value with no positions', async ({ page, request }) => {
    const p = await getPortfolio(request);
    expect(p.cash_balance).toBe(10000);
    expect(p.positions).toEqual([]);

    await expect(page.getByTestId(T.cash)).toHaveText('$10,000.00');
    await expectMoney(page.getByTestId(T.totalValue), 10000);
    await expect(positionRows(page)).toHaveCount(0);
    await expect(page.getByTestId(T.positionsEmpty)).toBeVisible();
  });

  test('every ticker has a price and a daily change', async ({ page }) => {
    for (const ticker of DEFAULT_TICKERS) {
      await expect
        .poll(async () => parseNumber(await page.getByTestId(TT.watchlistPrice(ticker)).textContent()))
        .toBeGreaterThan(0);
      await expect(page.getByTestId(TT.watchlistChange(ticker))).toHaveText(/\d/);
    }
  });

  test('prices stream: displayed prices change without a reload', async ({ page }) => {
    const prices = watchlistPrices(page);
    await expect(prices).toHaveCount(DEFAULT_TICKERS.length);
    const before = await prices.allTextContents();
    // ~500ms ticks across ten tickers: at least one price moves within seconds.
    await expect
      .poll(async () => (await prices.allTextContents()).some((text, i) => text !== before[i]), { timeout: 15_000 })
      .toBe(true);
  });

  test('clicking a ticker selects it in the main chart', async ({ page }) => {
    const row = watchlistRow(page, 'MSFT');
    await row.click();
    await expect(row).toHaveAttribute('data-selected', 'true');
    await expect(page.getByTestId(T.mainChartTicker)).toContainText('MSFT');
    await expect(page.getByTestId(T.mainChart)).toBeVisible();
  });
});
