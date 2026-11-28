import type { Position } from "@/lib/types";
import { formatPercent, formatPrice, formatQuantity, formatSignedUsd, signClass } from "@/lib/format";

interface Props {
  positions: Position[];
  onSelect?: (ticker: string) => void;
}

export default function PositionsTable({ positions, onSelect }: Props) {
  return (
    <section aria-label="Positions" className="flex h-full min-h-0 flex-col">
      <div className="flex items-baseline justify-between px-3 pb-1 pt-2.5">
        <h2 className="text-[12px] font-medium text-muted">Positions</h2>
        <span className="num text-[11px] text-faint">{positions.length}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table data-testid="positions-table" className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-panel text-[11px] text-muted">
            <tr className="border-b border-line">
              <th className="px-3 py-1 text-left font-normal">Ticker</th>
              <th className="px-2 py-1 text-right font-normal">Qty</th>
              <th className="px-2 py-1 text-right font-normal">Avg cost</th>
              <th className="px-2 py-1 text-right font-normal">Price</th>
              <th className="px-2 py-1 text-right font-normal">Unrealized P&L</th>
              <th className="px-3 py-1 text-right font-normal">% change</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr
                key={p.ticker}
                data-testid={`position-row-${p.ticker}`}
                onClick={() => onSelect?.(p.ticker)}
                className="cursor-pointer border-b border-line/50 hover:bg-raised"
              >
                <td className="px-3 py-1 font-medium text-text">{p.ticker}</td>
                <td data-testid={`position-quantity-${p.ticker}`} className="num px-2 py-1 text-right">
                  {formatQuantity(p.quantity)}
                </td>
                <td className="num px-2 py-1 text-right">{formatPrice(p.avg_cost)}</td>
                <td className="num px-2 py-1 text-right">{formatPrice(p.current_price)}</td>
                <td className={`num px-2 py-1 text-right ${signClass(p.unrealized_pnl)}`}>
                  {formatSignedUsd(p.unrealized_pnl)}
                </td>
                <td className={`num px-3 py-1 text-right ${signClass(p.pnl_percent)}`}>
                  {formatPercent(p.pnl_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {positions.length === 0 && (
          <p data-testid="positions-empty" className="px-3 py-3 text-[12px] text-muted">
            You have no open positions. Use the trade bar to buy your first shares.
          </p>
        )}
      </div>
    </section>
  );
}
