"use client";

import { useEffect, useRef, useState } from "react";
import type { ConnectionStatus, PriceMap, PricePoint } from "@/lib/types";

export const MAX_HISTORY_POINTS = 1500;
const MANUAL_RETRY_MS = 3000;
const DISCONNECTED_AFTER_FAILURES = 3;

export type PriceHistory = Record<string, PricePoint[]>;

/**
 * Append the latest price of every ticker in `prices` to `history`, one point per
 * whole second (a later tick in the same second replaces the earlier one, so the
 * series stays strictly ascending as Lightweight Charts requires). Tickers missing
 * from `prices` are dropped (each SSE event is the complete price set).
 */
export function appendHistory(history: PriceHistory, prices: PriceMap): PriceHistory {
  const next: PriceHistory = {};
  for (const [ticker, update] of Object.entries(prices)) {
    const series = history[ticker] ?? [];
    const time = Math.floor(update.timestamp);
    const last = series[series.length - 1];
    if (last && last.time === time) {
      next[ticker] =
        last.value === update.price
          ? series
          : [...series.slice(0, -1), { time, value: update.price }];
    } else if (last && last.time > time) {
      next[ticker] = series;
    } else {
      const appended = [...series, { time, value: update.price }];
      next[ticker] =
        appended.length > MAX_HISTORY_POINTS
          ? appended.slice(appended.length - MAX_HISTORY_POINTS)
          : appended;
    }
  }
  return next;
}

interface StreamState {
  prices: PriceMap;
  history: PriceHistory;
}

/** Subscribes to GET /api/stream/prices (PLAN.md §6) with the native EventSource. */
export function usePriceStream(url = "/api/stream/prices") {
  const [state, setState] = useState<StreamState>({ prices: {}, history: {} });
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let source: EventSource | null = null;
    let disposed = false;
    let failures = 0;

    const connect = () => {
      if (disposed) return;
      source = new EventSource(url);
      source.onopen = () => {
        failures = 0;
        setStatus("connected");
      };
      source.onmessage = (event: MessageEvent<string>) => {
        let prices: PriceMap;
        try {
          prices = JSON.parse(event.data) as PriceMap;
        } catch {
          return;
        }
        setStatus("connected");
        setState((prev) => ({ prices, history: appendHistory(prev.history, prices) }));
      };
      source.onerror = () => {
        if (!source) return;
        if (source.readyState === EventSource.CLOSED) {
          // The browser gave up (e.g. non-200 response); retry ourselves.
          setStatus("disconnected");
          source.close();
          retryTimer.current = setTimeout(connect, MANUAL_RETRY_MS);
        } else {
          // Browser retries automatically; after a few failures in a row, show red.
          failures += 1;
          setStatus(failures >= DISCONNECTED_AFTER_FAILURES ? "disconnected" : "reconnecting");
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      source?.close();
    };
  }, [url]);

  return { prices: state.prices, history: state.history, status };
}
