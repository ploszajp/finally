/** Buy and sell through the trade bar (PLAN.md §12). */
import { expect, test, type Page } from '@playwright/test';
import { T, closeAllPositions, expectMoney, getPortfolio, openApp, positionQuantity, positionRow } from './selectors';

async function submitTrade(page: Page, ticker: string, quantity: number, side: 'buy' | 'sell') {
  await page.getByTestId(T.tradeTicker).fill(ticker);
  await page.getByTestId(T.tradeQuantity).fill(String(quantity));
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/api/portfolio/trade') && r.request().method() === 'POST',
  );
  await page.getByTestId(side === 'buy' ? T.tradeBuy : T.tradeSell).click();
  return response;
}

test.describe('trading', () => {
  test.beforeEach(async ({ page, request }) => {
    await closeAllPositions(request);
    await openApp(page);
  });

  test('buy: cash decreases and the position appears', async ({ page, request }) => {
    const cashBefore = (await getPortfolio(request)).cash_balance;
    await expectMoney(page.getByTestId(T.cash), cashBefore);

    const response = await submitTrade(page, 'aapl', 5, 'buy');
    expect(response.status()).toBe(200);
    const { trade } = await response.json();
    expect(trade).toMatchObject({ ticker: 'AAPL', side: 'buy', quantity: 5 });

    const cashAfter = Math.round((cashBefore - trade.total) * 100) / 100;
    expect((await getPortfolio(request)).cash_balance).toBeCloseTo(cashAfter, 2);
    await expectMoney(page.getByTestId(T.cash), cashAfter);

    const row = positionRow(page, 'AAPL');
    await expect(row).toBeVisible();
    await expect.poll(() => positionQuantity(page, 'AAPL')).toBe(5);
    await expect(row).toContainText(trade.price.toFixed(2)); // avg cost == fill price
  });

  test('sell: cash increases, the position shrinks, then disappears', async ({ page, request }) => {
    let response = await submitTrade(page, 'AAPL', 5, 'buy');
    expect(response.status()).toBe(200);
    const row = positionRow(page, 'AAPL');
    await expect(row).toBeVisible();

    // Partial sell.
    const cashBefore = (await getPortfolio(request)).cash_balance;
    response = await submitTrade(page, 'AAPL', 2, 'sell');
    expect(response.status()).toBe(200);
    let trade = (await response.json()).trade;
    const cashMid = Math.round((cashBefore + trade.total) * 100) / 100;
    expect(cashMid).toBeGreaterThan(cashBefore);
    await expectMoney(page.getByTestId(T.cash), cashMid);
    await expect.poll(() => positionQuantity(page, 'AAPL')).toBe(3);

    // Sell the rest: the row goes away.
    response = await submitTrade(page, 'AAPL', 3, 'sell');
    expect(response.status()).toBe(200);
    trade = (await response.json()).trade;
    await expectMoney(page.getByTestId(T.cash), Math.round((cashMid + trade.total) * 100) / 100);
    await expect(row).toHaveCount(0);
    expect((await getPortfolio(request)).positions).toEqual([]);
  });

  test('selling more than owned shows the error and changes nothing', async ({ page, request }) => {
    const before = await getPortfolio(request);
    const response = await submitTrade(page, 'AAPL', 1, 'sell');
    expect(response.status()).toBe(400);
    await expect(page.getByTestId(T.tradeError)).toContainText(/insufficient shares/i);
    expect(await getPortfolio(request)).toMatchObject({ cash_balance: before.cash_balance, positions: [] });
    await expect(positionRow(page, 'AAPL')).toHaveCount(0);
  });

  test('buying with insufficient cash shows the error', async ({ page }) => {
    const response = await submitTrade(page, 'AAPL', 100000, 'buy');
    expect(response.status()).toBe(400);
    await expect(page.getByTestId(T.tradeError)).toContainText(/insufficient cash/i);
    await expect(positionRow(page, 'AAPL')).toHaveCount(0);
  });
});
