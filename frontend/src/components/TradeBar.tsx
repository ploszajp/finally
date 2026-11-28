"use client";

import { useState } from "react";
import type { TradeResponse } from "@/lib/types";
import { formatQuantity, formatUsd } from "@/lib/format";

interface Props {
  ticker: string;
  onTickerChange: (ticker: string) => void;
  onTrade: (ticker: string, quantity: number, side: "buy" | "sell") => Promise<TradeResponse>;
}

export default function TradeBar({ ticker, onTickerChange, onTrade }: Props) {
  const [quantity, setQuantity] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const submit = async (side: "buy" | "sell") => {
    const t = ticker.trim().toUpperCase();
    const q = Number(quantity);
    setSuccess(null);
    if (!t) {
      setError("Enter a ticker.");
      return;
    }
    if (!Number.isFinite(q) || q <= 0) {
      setError("Quantity must be greater than 0.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { trade } = await onTrade(t, q, side);
      setSuccess(
        `${trade.side === "buy" ? "Bought" : "Sold"} ${formatQuantity(trade.quantity)} ${trade.ticker} at ${formatUsd(trade.price)}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      aria-label="Trade"
      onSubmit={(e) => {
        e.preventDefault();
        submit("buy");
      }}
      className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2"
    >
      <label className="flex items-center gap-1.5 text-[11px] text-muted">
        Ticker
        <input
          data-testid="trade-ticker"
          value={ticker}
          onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
          maxLength={10}
          className="num w-20 rounded-sm border border-line bg-ink px-2 py-1 text-[12px] uppercase text-text focus:border-primary focus:outline-none"
        />
      </label>
      <label className="flex items-center gap-1.5 text-[11px] text-muted">
        Qty
        <input
          data-testid="trade-quantity"
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className="num w-20 rounded-sm border border-line bg-ink px-2 py-1 text-[12px] text-text focus:border-primary focus:outline-none"
        />
      </label>
      <button
        type="button"
        data-testid="trade-buy"
        disabled={busy}
        onClick={() => submit("buy")}
        className="rounded-sm bg-submit px-3 py-1 text-[12px] font-medium text-white hover:bg-submit-hover disabled:opacity-40"
      >
        Buy
      </button>
      <button
        type="button"
        data-testid="trade-sell"
        disabled={busy}
        onClick={() => submit("sell")}
        className="rounded-sm border border-submit px-3 py-1 text-[12px] font-medium text-text hover:bg-submit/30 disabled:opacity-40"
      >
        Sell
      </button>
      <span className="text-[11px] text-faint">Market order, fills instantly</span>
      <div className="ml-auto min-w-0 text-[12px]" aria-live="polite">
        {error && (
          <span data-testid="trade-error" role="alert" className="text-down">
            {error}
          </span>
        )}
        {success && !error && (
          <span data-testid="trade-success" className="text-up">
            {success}
          </span>
        )}
      </div>
    </form>
  );
}
