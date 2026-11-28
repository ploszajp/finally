import type { Position } from "@/lib/types";
import { squarify } from "@/lib/treemap";
import { formatPercent, formatUsd } from "@/lib/format";

const SATURATE_AT = 5; // % P&L at which the color reaches full intensity

export function pnlColor(pnlPercent: number): string {
  if (pnlPercent === 0) return "rgba(79, 91, 107, 0.45)";
  const t = Math.min(Math.abs(pnlPercent) / SATURATE_AT, 1);
  const alpha = (0.22 + 0.6 * t).toFixed(2);
  return pnlPercent > 0 ? `rgba(46, 189, 133, ${alpha})` : `rgba(239, 83, 80, ${alpha})`;
}

export function pnlBucket(pnlPercent: number): "positive" | "negative" | "flat" {
  return pnlPercent > 0 ? "positive" : pnlPercent < 0 ? "negative" : "flat";
}

interface Props {
  positions: Position[];
  onSelect?: (ticker: string) => void;
}

export default function Heatmap({ positions, onSelect }: Props) {
  const rects = squarify(positions.map((p) => ({ value: p.market_value, item: p })));
  return (
    <section data-testid="heatmap" aria-label="Positions heatmap" className="flex h-full min-h-0 flex-col">
      <div className="flex items-baseline justify-between px-3 pb-1 pt-2.5">
        <h2 className="text-[12px] font-medium text-muted">Holdings</h2>
        <span className="text-[11px] text-faint">Sized by weight, colored by P&L</span>
      </div>
      <div className="relative mx-3 mb-3 min-h-0 flex-1">
        {rects.length === 0 ? (
          <div
            data-testid="heatmap-empty"
            className="flex h-full items-center justify-center rounded-sm border border-dashed border-line text-[12px] text-muted"
          >
            No positions yet. Buy shares to see them here.
          </div>
        ) : (
          rects.map(({ item: p, x, y, w, h }) => (
            <button
              type="button"
              key={p.ticker}
              data-testid={`heatmap-cell-${p.ticker}`}
              data-pnl={pnlBucket(p.pnl_percent)}
              onClick={() => onSelect?.(p.ticker)}
              title={`${p.ticker}: ${formatUsd(p.market_value)}, ${p.weight_percent.toFixed(1)}% of portfolio, ${formatPercent(p.pnl_percent)}`}
              className="absolute flex flex-col items-start justify-start overflow-hidden border border-ink p-1.5 text-left transition-[background-color] duration-500 hover:brightness-125"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                width: `${w}%`,
                height: `${h}%`,
                backgroundColor: pnlColor(p.pnl_percent),
              }}
            >
              <span className="text-[12px] font-semibold leading-tight text-white">{p.ticker}</span>
              {w > 12 && h > 18 && (
                <span className="num text-[11px] leading-tight text-white/80">{formatPercent(p.pnl_percent)}</span>
              )}
            </button>
          ))
        )}
      </div>
    </section>
  );
}
