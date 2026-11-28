import { useMemo } from "react";
import type { PricePoint, Snapshot } from "@/lib/types";
import TimeSeriesChart from "./TimeSeriesChart";

/** Snapshots → strictly ascending whole-second points (last value per second wins). */
export function snapshotsToPoints(snapshots: Snapshot[]): PricePoint[] {
  const out: PricePoint[] = [];
  for (const s of snapshots) {
    const ms = Date.parse(s.recorded_at);
    if (Number.isNaN(ms)) continue;
    const time = Math.floor(ms / 1000);
    const last = out[out.length - 1];
    if (last && last.time === time) last.value = s.total_value;
    else if (!last || time > last.time) out.push({ time, value: s.total_value });
  }
  return out;
}

export default function PnlChart({ snapshots }: { snapshots: Snapshot[] }) {
  const points = useMemo(() => snapshotsToPoints(snapshots), [snapshots]);
  const first = points[0]?.value ?? null;
  const last = points[points.length - 1]?.value ?? null;
  const rising = first == null || last == null || last >= first;
  return (
    <section
      data-testid="pnl-chart"
      data-points={snapshots.length}
      aria-label="Portfolio value over time"
      className="flex h-full min-h-0 flex-col"
    >
      <div className="flex items-baseline justify-between px-3 pb-1 pt-2.5">
        <h2 className="text-[12px] font-medium text-muted">Portfolio value</h2>
        <span className="text-[11px] text-faint">Snapshots every 30s and after trades</span>
      </div>
      <div className="relative min-h-0 flex-1">
        <TimeSeriesChart
          data={points}
          color={rising ? "#2ebd85" : "#ef5350"}
          secondsVisible={false}
          baseline={first}
        />
        {points.length === 0 && (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-[12px] text-muted">
            No snapshots yet.
          </p>
        )}
      </div>
    </section>
  );
}
