/**
 * AI chat with LLM_MOCK=true (PLAN.md §12). Mock replies are exact, see
 * planning/API_CHAT.md "Mock mode".
 */
import { expect, test, type Page } from '@playwright/test';
import {
  MOCK_GREETING,
  MOCK_UNAVAILABLE,
  T,
  closeAllPositions,
  ensureNotOnWatchlist,
  getPortfolio,
  getWatchlist,
  openApp,
  parseNumber,
  positionQuantity,
  positionRow,
  watchlistRow,
} from './selectors';

async function send(page: Page, message: string) {
  const response = page.waitForResponse((r) => r.url().endsWith('/api/chat') && r.request().method() === 'POST');
  await page.getByTestId(T.chatInput).fill(message);
  await page.getByTestId(T.chatSend).click();
  expect((await response).status()).toBe(200);
  return page.locator(`[data-testid="${T.chatMessage}"][data-role="assistant"]`).last();
}

test.describe('AI chat (mock)', () => {
  test.beforeEach(async ({ page, request }) => {
    await closeAllPositions(request);
    await openApp(page);
  });

  test('message gets a reply, with a loading indicator while waiting', async ({ page }) => {
    // Hold the request briefly so the loading state is observable.
    await page.route('**/api/chat', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await route.continue();
    });
    await page.getByTestId(T.chatInput).fill('hello');
    await page.getByTestId(T.chatSend).click();

    await expect(page.getByTestId(T.chatLoading)).toBeVisible();
    await expect(page.locator(`[data-testid="${T.chatMessage}"][data-role="user"]`).last()).toHaveText(/hello/);
    const reply = page.locator(`[data-testid="${T.chatMessage}"][data-role="assistant"]`).last();
    await expect(reply).toContainText(MOCK_GREETING);
    await expect(page.getByTestId(T.chatLoading)).toBeHidden();
    await expect(reply.getByTestId(T.chatAction)).toHaveCount(0);
  });

  test('buy via chat: inline trade confirmation and the position appears', async ({ page, request }) => {
    const cashBefore = (await getPortfolio(request)).cash_balance;
    const reply = await send(page, 'Buy some apple');

    await expect(reply).toContainText('Mock mode: processing your request. Buying 1 share of AAPL.');
    const action = reply.getByTestId(T.chatAction);
    await expect(action).toHaveCount(1);
    await expect(action).toHaveAttribute('data-kind', 'trade');
    await expect(action).toHaveAttribute('data-status', 'executed');
    await expect(action).toContainText('AAPL');

    // The UI refreshes the portfolio after an executed chat action.
    const row = positionRow(page, 'AAPL');
    await expect(row).toBeVisible();
    await expect.poll(() => positionQuantity(page, 'AAPL')).toBe(1);
    const p = await getPortfolio(request);
    expect(p.cash_balance).toBeLessThan(cashBefore);
    await expect.poll(async () => parseNumber(await page.getByTestId(T.cash).textContent())).toBeCloseTo(p.cash_balance, 2);
  });

  test('rejected trade is shown inline with its reason', async ({ page }) => {
    const reply = await send(page, 'sell'); // nothing held
    const action = reply.getByTestId(T.chatAction);
    await expect(action).toHaveAttribute('data-status', 'rejected');
    await expect(action).toContainText(/insufficient shares/i);
  });

  test('watchlist add and remove via chat update the watchlist panel', async ({ page, request }) => {
    await ensureNotOnWatchlist(request, 'PYPL');

    let reply = await send(page, 'add PYPL');
    await expect(reply).toContainText('Adding PYPL to your watchlist.');
    let action = reply.getByTestId(T.chatAction);
    await expect(action).toHaveAttribute('data-kind', 'watchlist');
    await expect(action).toHaveAttribute('data-status', 'executed');
    await expect(watchlistRow(page, 'PYPL')).toBeVisible();

    reply = await send(page, 'remove PYPL');
    await expect(reply).toContainText('Removing PYPL from your watchlist.');
    action = reply.getByTestId(T.chatAction);
    await expect(action).toHaveAttribute('data-status', 'executed');
    await expect(watchlistRow(page, 'PYPL')).toHaveCount(0);
    expect(await getWatchlist(request)).not.toContain('PYPL');
  });

  test('LLM failure shows a friendly error message', async ({ page }) => {
    const reply = await send(page, 'mock error');
    await expect(reply).toContainText(MOCK_UNAVAILABLE);
    await expect(reply).toHaveAttribute('data-error', 'true');
  });

  test('conversation is restored after a reload', async ({ page }) => {
    await send(page, 'hello again');
    await page.reload();
    await expect(page.locator(`[data-testid="${T.chatMessage}"][data-role="user"]`).last()).toHaveText(/hello again/);
    await expect(page.locator(`[data-testid="${T.chatMessage}"][data-role="assistant"]`).last()).toContainText(
      MOCK_GREETING,
    );
  });
});
