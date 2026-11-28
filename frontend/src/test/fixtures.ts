import type { ChatMessage, Portfolio, PriceUpdate, WatchlistItem } from "@/lib/types";

export function priceUpdate(ticker: string, overrides: Partial<PriceUpdate> = {}): PriceUpdate {
  return {
    ticker,
    price: 100,
    previous_price: 100,
    timestamp: 1_800_000_000.25,
    change: 0,
    change_percent: 0,
    direction: "flat",
    reference_price: 100,
    day_change_percent: 0,
    ...overrides,
  };
}

export function watchItem(ticker: string, price: number | null = 100): WatchlistItem {
  return {
    ticker,
    price,
    previous_price: price,
    change_percent: 0,
    day_change_percent: 0,
    direction: "flat",
    added_at: "2026-11-28T10:00:00+00:00",
  };
}

export const portfolio: Portfolio = {
  cash_balance: 8000,
  positions_value: 2000,
  total_value: 10000,
  unrealized_pnl: 0,
  unrealized_pnl_percent: 0,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 100,
      current_price: 100,
      market_value: 1000,
      unrealized_pnl: 0,
      pnl_percent: 0,
      weight_percent: 10,
    },
    {
      ticker: "TSLA",
      quantity: 4,
      avg_cost: 250,
      current_price: 250,
      market_value: 1000,
      unrealized_pnl: 0,
      pnl_percent: 0,
      weight_percent: 10,
    },
  ],
};

export function chatMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: Math.random().toString(36).slice(2),
    role: "assistant",
    content: "Hello",
    actions: { watchlist_changes: [], trades: [], error: null },
    created_at: "2026-11-28T10:00:00+00:00",
    ...overrides,
  };
}

/** Minimal fetch Response stand-in. */
export function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}
