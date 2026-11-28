"use client";

import { useState } from "react";
import type { PriceMap, PricePoint, PriceUpdate, WatchlistItem } from "@/lib/types";
import { formatPercent, formatPrice, signClass } from "@/lib/format";
import Sparkline from "./Sparkline";

interface Props {
  items: WatchlistItem[];
  prices: PriceMap;
  history: Record<string, PricePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
}

export function PriceCell({ ticker, live, fallback }: { ticker: string; live?: PriceUpdate; fallback: number | null }) {
  // Timestamp of the tick whose flash animation already finished; the class is
  // removed once the ~500ms fade ends and re-applied on the next up/down tick.
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const direction = live?.direction ?? "flat";
  const flashing =
    live !== undefined && (direction === "up" || direction === "down") && live.timestamp !== finishedAt;
  return (
    <span
      // Remount on each up/down tick so the CSS fade animation replays.
      key={flashing ? `${live.timestamp}` : "steady"}
      onAnimationEnd={() => live && setFinishedAt(live.timestamp)}
      data-testid={`watchlist-price-${ticker}`}
      data-direction={direction}
      className={`num rounded-sm px-1 text-[13px] text-text ${
        flashing ? (direction === "up" ? "flash-up" : "flash-down") : ""
      }`}
    >
      {formatPrice(live?.price ?? fallback)}
    </span>
  );
}

function Row({
  item,
  live,
  points,
  selected,
  onSelect,
  onRemove,
}: {
  item: WatchlistItem;
  live?: PriceUpdate;
  points: PricePoint[];
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const t = item.ticker;
  const day = live?.day_change_percent ?? item.day_change_percent;
  return (
    <li
      data-testid={`watchlist-row-${t}`}
      data-ticker={t}
      data-selected={selected ? "true" : "false"}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      className={`group relative grid cursor-pointer grid-cols-[1fr_auto] items-center gap-x-2 border-b border-line/60 py-1.5 pl-3 pr-2 outline-none hover:bg-raised focus-visible:bg-raised ${
        selected ? "bg-raised" : ""
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden />}
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className={`font-medium ${selected ? "text-accent" : "text-text"}`}>{t}</span>
        <Sparkline points={points} testId={`sparkline-${t}`} />
      </div>
      <div className="flex flex-col items-end leading-tight">
        <PriceCell ticker={t} live={live} fallback={item.price} />
        <span data-testid={`watchlist-change-${t}`} className={`num px-1 text-[11px] ${signClass(day)}`}>
          {formatPercent(day)}
        </span>
      </div>
      <button
        type="button"
        data-testid={`watchlist-remove-${t}`}
        aria-label={`Remove ${t} from watchlist`}
        title={`Remove ${t}`}
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        className="absolute right-1 top-1 hidden h-4 w-4 items-center justify-center rounded-sm text-[12px] leading-none text-muted hover:bg-down/20 hover:text-down focus-visible:flex group-hover:flex group-focus-within:flex"
      >
        ×
      </button>
    </li>
  );
}

export default function Watchlist({ items, prices, history, selected, onSelect, onAdd, onRemove }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(ticker);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the ticker");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (ticker: string) => {
    setError(null);
    try {
      await onRemove(ticker);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the ticker");
    }
  };

  return (
    <section data-testid="watchlist" aria-label="Watchlist" className="flex min-h-0 flex-col">
      <div className="flex items-center justify-between px-3 pb-1.5 pt-2.5">
        <h2 className="text-[12px] font-medium text-muted">Watchlist</h2>
        <span className="num text-[11px] text-faint">{items.length}</span>
      </div>
      <form onSubmit={submit} className="flex gap-1 px-3 pb-2">
        <input
          data-testid="watchlist-add-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add ticker"
          aria-label="Ticker to add"
          maxLength={10}
          className="num min-w-0 flex-1 rounded-sm border border-line bg-ink px-2 py-1 text-[12px] uppercase text-text placeholder:normal-case placeholder:text-faint focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          data-testid="watchlist-add-button"
          disabled={busy || !draft.trim()}
          className="rounded-sm bg-submit px-2.5 py-1 text-[12px] font-medium text-white hover:bg-submit-hover disabled:opacity-40"
        >
          Add
        </button>
      </form>
      {error && (
        <p data-testid="watchlist-error" role="alert" className="px-3 pb-2 text-[11px] text-down">
          {error}
        </p>
      )}
      <ul className="min-h-0 flex-1 overflow-y-auto border-t border-line">
        {items.map((item) => (
          <Row
            key={item.ticker}
            item={item}
            live={prices[item.ticker]}
            points={history[item.ticker] ?? []}
            selected={selected === item.ticker}
            onSelect={() => onSelect(item.ticker)}
            onRemove={() => remove(item.ticker)}
          />
        ))}
        {items.length === 0 && (
          <li className="px-3 py-4 text-[12px] text-muted">Your watchlist is empty. Add a ticker above.</li>
        )}
      </ul>
    </section>
  );
}
