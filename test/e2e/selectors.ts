/**
 * Shared selectors and helpers for the FinAlly E2E specs.
 *
 * All data-testid names live here, so a rename in the frontend means one edit.
 * Server state is shared (single user, one database) and specs run serially in
 * file-name order, so every spec after 01 reads the current state through the
 * API instead of assuming a fresh database.
 */
import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';

export const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

export const MOCK_GREETING =
  'Hello from FinAlly (mock mode). I can buy or sell AAPL and add or remove watchlist tickers.';
export const MOCK_UNAVAILABLE = 'The AI assistant is unavailable right now. Please try again in a moment.';

export const T = {
  totalValue: 'total-value',
  cash: 'cash-balance',
  connection: 'connection-status',

  watchlistAddInput: 'watchlist-add-input',
  watchlistAddButton: 'watchlist-add-button',
  watchlistError: 'watchlist-error',

  mainChart: 'main-chart',
  mainChartTicker: 'main-chart-ticker',

  tradeTicker: 'trade-ticker',
  tradeQuantity: 'trade-quantity',
  tradeBuy: 'trade-buy',
  tradeSell: 'trade-sell',
  tradeError: 'trade-error',

  positionsTable: 'positions-table',
  positionsEmpty: 'positions-empty',

  heatmap: 'heatmap',
  heatmapEmpty: 'heatmap-empty',

  pnlChart: 'pnl-chart',

  chatInput: 'chat-input',
  chatSend: 'chat-send',
  chatLoading: 'chat-loading',
  chatMessage: 'chat-message',
  chatAction: 'chat-action',
} as const;

/** Per-ticker test ids ({T} = normalised ticker), see the frontend contract. */
export const TT = {
  watchlistRow: (t: string) => `watchlist-row-${t}`,
  watchlistPrice: (t: string) => `watchlist-price-${t}`,
  watchlistChange: (t: string) => `watchlist-change-${t}`,
  watchlistRemove: (t: string) => `watchlist-remove-${t}`,
  positionRow: (t: string) => `position-row-${t}`,
  heatmapCell: (t: string) => `heatmap-cell-${t}`,
};

/** "$10,000.00" / "-$12.50" / "1,234.5" -> number. */
export function parseNumber(text: string | null): number {
  const cleaned = (text ?? '').replace(/[$,\s%+]/g, '').replace(/[−–]/g, '-');
  const value = Number.parseFloat(cleaned);
  if (Number.isNaN(value)) throw new Error(`not a number: ${JSON.stringify(text)}`);
  return value;
}

/** All watchlist rows, in display order. */
export const watchlistRows = (page: Page) => page.locator('[data-testid^="watchlist-row-"]');
export const positionRows = (page: Page) => page.locator('[data-testid^="position-row-"]');
export const heatmapCells = (page: Page) => page.locator('[data-testid^="heatmap-cell-"]');
export const watchlistPrices = (page: Page) => page.locator('[data-testid^="watchlist-price-"]');

export const watchlistRow = (page: Page, ticker: string) => page.getByTestId(TT.watchlistRow(ticker));
export const positionRow = (page: Page, ticker: string) => page.getByTestId(TT.positionRow(ticker));
export const heatmapCell = (page: Page, ticker: string) => page.getByTestId(TT.heatmapCell(ticker));

/** Quantity shown in a positions-table row (column 2: ticker, quantity, avg cost, ...). */
export async function positionQuantity(page: Page, ticker: string): Promise<number> {
  return parseNumber(await positionRow(page, ticker).locator('td').nth(1).textContent());
}

/** Expect a money-like element to show `expected` (to the cent). */
export async function expectMoney(locator: Locator, expected: number) {
  await expect.poll(async () => parseNumber(await locator.textContent())).toBeCloseTo(expected, 2);
}

/** Open the app and wait until the live stream is up. */
export async function openApp(page: Page) {
  await page.goto('/');
  await expect(page.getByTestId(T.connection)).toHaveAttribute('data-status', 'connected', { timeout: 15_000 });
}

// ---- API helpers (state setup and ground truth) ---------------------------

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  positions: Position[];
}

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const r = await request.get('/api/portfolio');
  expect(r.status()).toBe(200);
  return r.json();
}

export async function getWatchlist(request: APIRequestContext): Promise<string[]> {
  const r = await request.get('/api/watchlist');
  expect(r.status()).toBe(200);
  return (await r.json()).watchlist.map((i: { ticker: string }) => i.ticker);
}

export async function apiTrade(request: APIRequestContext, ticker: string, quantity: number, side: 'buy' | 'sell') {
  const r = await request.post('/api/portfolio/trade', { data: { ticker, quantity, side } });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}

/** Sell everything held, so a spec starts with no positions. */
export async function closeAllPositions(request: APIRequestContext) {
  for (const p of (await getPortfolio(request)).positions) {
    await apiTrade(request, p.ticker, p.quantity, 'sell');
  }
}

export async function ensureOnWatchlist(request: APIRequestContext, ticker: string) {
  if (!(await getWatchlist(request)).includes(ticker)) {
    const r = await request.post('/api/watchlist', { data: { ticker } });
    expect(r.status()).toBe(201);
  }
}

export async function ensureNotOnWatchlist(request: APIRequestContext, ticker: string) {
  if ((await getWatchlist(request)).includes(ticker)) {
    const r = await request.delete(`/api/watchlist/${ticker}`);
    expect(r.status()).toBe(200);
  }
}
