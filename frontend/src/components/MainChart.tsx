import type { PricePoint, PriceUpdate } from "@/lib/types";
import { formatPercent, formatPrice, signClass } from "@/lib/format";
import TimeSeriesChart from "./TimeSeriesChart";

interface Props {
  ticker: string | null;
  live?: PriceUpdate;
  points: PricePoint[];
}

export default function MainChart({ ticker, live, points }: Props) {
  return (
    <section data-testid="main-chart" aria-label="Price chart" className="flex h-full min-h-0 flex-col">
      <div className="flex items-baseline gap-3 px-3 pb-1 pt-2.5">
        <h2 data-testid="main-chart-ticker" className="text-[16px] font-semibold text-accent">
          {ticker ?? "—"}
        </h2>
        {live && (
          <>
            <span className="num text-[16px] text-text">{formatPrice(live.price)}</span>
            <span className={`num text-[12px] ${signClass(live.day_change_percent)}`}>
              {formatPercent(live.day_change_percent)} today
            </span>
          </>
        )}
        <span className="ml-auto text-[11px] text-faint">Since page load</span>
      </div>
      <div className="relative min-h-0 flex-1">
        {ticker ? (
          <TimeSeriesChart key={ticker} data={points} color="#209dd7" />
        ) : (
          <p className="p-4 text-muted">Select a ticker in the watchlist to chart it.</p>
        )}
        {ticker && points.length < 2 && (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-[12px] text-muted">
            Collecting prices for {ticker}…
          </p>
        )}
      </div>
    </section>
  );
}
