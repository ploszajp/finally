import type { ConnectionStatus } from "@/lib/types";
import { formatPercent, formatSignedUsd, formatUsd, signClass } from "@/lib/format";

const STATUS: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: "bg-up", label: "Live" },
  reconnecting: { color: "bg-accent dot-pulse", label: "Reconnecting" },
  disconnected: { color: "bg-down", label: "Disconnected" },
};

interface Props {
  totalValue: number | null;
  cash: number | null;
  pnl: number | null;
  pnlPercent: number | null;
  status: ConnectionStatus;
}

function Stat({
  label,
  children,
  testId,
}: {
  label: string;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[11px] text-muted">{label}</span>
      <span data-testid={testId} className="num text-[15px] text-text">
        {children}
      </span>
    </div>
  );
}

export default function Header({ totalValue, cash, pnl, pnlPercent, status }: Props) {
  const s = STATUS[status];
  return (
    <header
      data-testid="header"
      className="flex h-12 shrink-0 items-center gap-6 border-b border-line bg-panel px-4"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-[17px] font-semibold tracking-tight text-text">
          Fin<span className="text-accent">Ally</span>
        </span>
        <span className="hidden text-[11px] text-muted sm:inline">AI trading workstation</span>
      </div>

      <div className="ml-auto flex items-center gap-6">
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[11px] text-muted">Portfolio value</span>
          <span data-testid="total-value" className="num text-[19px] font-medium text-accent">
            {formatUsd(totalValue)}
          </span>
        </div>
        <Stat label="Cash" testId="cash-balance">
          {formatUsd(cash)}
        </Stat>
        <Stat label="Unrealized P&L" testId="unrealized-pnl">
          <span className={signClass(pnl)}>
            {formatSignedUsd(pnl)}{" "}
            <span className="text-[12px]">({formatPercent(pnlPercent)})</span>
          </span>
        </Stat>
        <div
          data-testid="connection-status"
          data-status={status}
          title={`Price stream: ${s.label}`}
          className="flex items-center gap-2 border-l border-line pl-4 text-[11px] text-muted"
        >
          <span className={`inline-block h-2 w-2 rounded-full ${s.color}`} aria-hidden />
          <span>{s.label}</span>
        </div>
      </div>
    </header>
  );
}
