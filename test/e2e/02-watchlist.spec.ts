/** Add and remove a watchlist ticker through the UI (PLAN.md §12). */
import { expect, test } from '@playwright/test';
import { T, TT, ensureNotOnWatchlist, getWatchlist, openApp, parseNumber, watchlistRow, watchlistRows } from './selectors';

const NEW_TICKER = 'PYPL';

test.describe('watchlist', () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureNotOnWatchlist(request, NEW_TICKER);
    await openApp(page);
  });

  test('add a ticker: it appears last, gets a live price, and is persisted', async ({ page, request }) => {
    const rows = watchlistRows(page);
    await expect(rows.first()).toBeVisible();
    const countBefore = await rows.count();

    // Lower case on purpose: the backend normalises.
    await page.getByTestId(T.watchlistAddInput).fill('pypl');
    await page.getByTestId(T.watchlistAddButton).click();

    await expect(watchlistRow(page, NEW_TICKER)).toBeVisible();
    await expect(rows).toHaveCount(countBefore + 1);
    await expect(rows.last()).toHaveAttribute('data-ticker', NEW_TICKER);
    await expect
      .poll(async () => parseNumber(await page.getByTestId(TT.watchlistPrice(NEW_TICKER)).textContent()))
      .toBeGreaterThan(0);

    expect(await getWatchlist(request)).toContain(NEW_TICKER);
    await page.reload();
    await expect(watchlistRow(page, NEW_TICKER)).toBeVisible();
  });

  test('remove a ticker: the row disappears and stays gone after reload', async ({ page, request }) => {
    const r = await request.post('/api/watchlist', { data: { ticker: NEW_TICKER } });
    expect(r.status()).toBe(201);
    await page.reload();

    const row = watchlistRow(page, NEW_TICKER);
    await expect(row).toBeVisible();
    await row.hover(); // the remove button is revealed on hover/focus
    await page.getByTestId(TT.watchlistRemove(NEW_TICKER)).click();
    await expect(row).toHaveCount(0);

    expect(await getWatchlist(request)).not.toContain(NEW_TICKER);
    await page.reload();
    await expect(watchlistRows(page).first()).toBeVisible();
    await expect(watchlistRow(page, NEW_TICKER)).toHaveCount(0);
  });

  test('adding a duplicate shows the error and does not create a second row', async ({ page }) => {
    const rows = watchlistRows(page);
    await expect(rows.first()).toBeVisible();
    const countBefore = await rows.count();
    await page.getByTestId(T.watchlistAddInput).fill('AAPL');
    await page.getByTestId(T.watchlistAddButton).click();
    await expect(page.getByTestId(T.watchlistError)).toContainText(/already on the watchlist/i);
    await expect(rows).toHaveCount(countBefore);
    await expect(watchlistRow(page, 'AAPL')).toHaveCount(1);
  });
});
