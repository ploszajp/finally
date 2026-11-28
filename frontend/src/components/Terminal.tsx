"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { revaluePortfolio } from "@/lib/portfolio";
import type { Portfolio, Snapshot, WatchlistItem } from "@/lib/types";
import { usePriceStream } from "@/hooks/usePriceStream";
import Header from "./Header";
import Watchlist from "./Watchlist";
import MainChart from "./MainChart";
import PnlChart from "./PnlChart";
import Heatmap from "./Heatmap";
import PositionsTable from "./PositionsTable";
import TradeBar from "./TradeBar";
import ChatPanel from "./ChatPanel";

const PORTFOLIO_REFRESH_MS = 15_000;
const HISTORY_REFRESH_MS = 30_000;

export default function Terminal() {
  const { prices, history, status } = usePriceStream();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tradeTicker, setTradeTicker] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);

  const loadWatchlist = useCallback(() => api.watchlist().then(setWatchlist).catch(() => {}), []);
  const loadPortfolio = useCallback(() => api.portfolio().then(setPortfolio).catch(() => {}), []);
  const loadHistory = useCallback(() => api.history().then(setSnapshots).catch(() => {}), []);

  useEffect(() => {
    loadWatchlist();
    loadPortfolio();
    loadHistory();
    const p = setInterval(loadPortfolio, PORTFOLIO_REFRESH_MS);
    const h = setInterval(loadHistory, HISTORY_REFRESH_MS);
    return () => {
      clearInterval(p);
      clearInterval(h);
    };
  }, [loadWatchlist, loadPortfolio, loadHistory]);

  const live = useMemo(() => (portfolio ? revaluePortfolio(portfolio, prices) : null), [portfolio, prices]);

  const selectedTicker = selected ?? watchlist[0]?.ticker ?? null;
  const tradeValue = tradeTicker ?? selectedTicker ?? "";

  const select = useCallback((ticker: string) => {
    setSelected(ticker);
    setTradeTicker(ticker);
  }, []);

  const addTicker = useCallback(async (ticker: string) => {
    const item = await api.addTicker(ticker);
    setWatchlist((w) => (w.some((i) => i.ticker === item.ticker) ? w : [...w, item]));
  }, []);

  const removeTicker = useCallback(
    async (ticker: string) => {
      await api.removeTicker(ticker);
      setWatchlist((w) => w.filter((i) => i.ticker !== ticker));
      if (selected === ticker) setSelected(null);
    },
    [selected],
  );

  const trade = useCallback(
    async (ticker: string, quantity: number, side: "buy" | "sell") => {
      const res = await api.trade(ticker, quantity, side);
      setPortfolio(res.portfolio);
      loadHistory();
      return res;
    },
    [loadHistory],
  );

  const afterChatActions = useCallback(() => {
    loadPortfolio();
    loadWatchlist();
    loadHistory();
  }, [loadPortfolio, loadWatchlist, loadHistory]);

  return (
    <div className="flex min-h-screen flex-col bg-ink lg:h-screen lg:min-h-0 lg:overflow-hidden">
      <Header
        totalValue={live?.total_value ?? null}
        cash={live?.cash_balance ?? null}
        pnl={live?.unrealized_pnl ?? null}
        pnlPercent={live?.unrealized_pnl_percent ?? null}
        status={status}
      />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex h-[420px] shrink-0 flex-col border-b border-line bg-panel lg:h-auto lg:w-[272px] lg:border-b-0 lg:border-r">
          <Watchlist
            items={watchlist}
            prices={prices}
            history={history}
            selected={selectedTicker}
            onSelect={select}
            onAdd={addTicker}
            onRemove={removeTicker}
          />
        </aside>

        <main className="grid min-w-0 flex-1 grid-cols-1 lg:grid-rows-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <div className="grid min-h-0 grid-cols-1 border-b border-line md:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
            <div className="h-[340px] min-h-0 border-b border-line md:border-b-0 md:border-r lg:h-auto">
              <MainChart
                ticker={selectedTicker}
                live={selectedTicker ? prices[selectedTicker] : undefined}
                points={selectedTicker ? (history[selectedTicker] ?? []) : []}
              />
            </div>
            <div className="h-[340px] min-h-0 lg:h-auto">
              <PnlChart snapshots={snapshots} />
            </div>
          </div>
          <div className="grid min-h-0 grid-cols-1 md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <div className="flex min-h-[300px] flex-col border-b border-line md:border-b-0 md:border-r lg:min-h-0">
              <TradeBar ticker={tradeValue} onTickerChange={setTradeTicker} onTrade={trade} />
              <div className="min-h-0 flex-1">
                <PositionsTable positions={live?.positions ?? []} onSelect={select} />
              </div>
            </div>
            <div className="h-[300px] min-h-0 lg:h-auto">
              <Heatmap positions={live?.positions ?? []} onSelect={select} />
            </div>
          </div>
        </main>

        <ChatPanel open={chatOpen} onToggle={() => setChatOpen((o) => !o)} onActionsExecuted={afterChatActions} />
      </div>
    </div>
  );
}
