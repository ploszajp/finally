import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Header from "./Header";
import Heatmap, { pnlBucket, pnlColor } from "./Heatmap";
import PositionsTable from "./PositionsTable";
import TradeBar from "./TradeBar";
import { snapshotsToPoints } from "./PnlChart";
import { revaluePortfolio } from "@/lib/portfolio";
import { portfolio, priceUpdate } from "@/test/fixtures";
import type { TradeResponse } from "@/lib/types";

const live = revaluePortfolio(portfolio, {
  AAPL: priceUpdate("AAPL", { price: 110 }),
  TSLA: priceUpdate("TSLA", { price: 200 }),
});

describe("Header", () => {
  it("shows values and the connection state", () => {
    render(<Header totalValue={10000} cash={8000.5} pnl={-12.3} pnlPercent={-0.5} status="connected" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,000.00");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,000.50");
    expect(screen.getByTestId("unrealized-pnl")).toHaveTextContent("-$12.30");
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  });

  it.each(["reconnecting", "disconnected"] as const)("shows %s status", (status) => {
    render(<Header totalValue={null} cash={null} pnl={null} pnlPercent={null} status={status} />);
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", status);
    expect(screen.getByTestId("total-value")).toHaveTextContent("—");
  });
});

describe("PositionsTable", () => {
  it("renders a row per position with P&L and % change vs avg cost", () => {
    render(<PositionsTable positions={live.positions} />);
    const aapl = screen.getByTestId("position-row-AAPL");
    expect(aapl).toHaveTextContent("10");
    expect(aapl).toHaveTextContent("100.00");
    expect(aapl).toHaveTextContent("110.00");
    expect(aapl).toHaveTextContent("+$100.00");
    expect(aapl).toHaveTextContent("+10.00%");
    expect(screen.getByTestId("position-row-TSLA")).toHaveTextContent("-20.00%");
  });

  it("shows an empty state", () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
  });
});

describe("Heatmap", () => {
  it("renders one cell per position colored by P&L", () => {
    render(<Heatmap positions={live.positions} />);
    expect(screen.getByTestId("heatmap-cell-AAPL")).toHaveAttribute("data-pnl", "positive");
    expect(screen.getByTestId("heatmap-cell-TSLA")).toHaveAttribute("data-pnl", "negative");
  });

  it("shows an empty state without positions", () => {
    render(<Heatmap positions={[]} />);
    expect(screen.getByTestId("heatmap-empty")).toBeInTheDocument();
  });

  it("maps P&L to color buckets", () => {
    expect(pnlBucket(0)).toBe("flat");
    expect(pnlColor(2)).toContain("46, 189, 133");
    expect(pnlColor(-2)).toContain("239, 83, 80");
  });
});

describe("snapshotsToPoints", () => {
  it("converts ISO timestamps to ascending unique seconds", () => {
    const pts = snapshotsToPoints([
      { total_value: 10000, recorded_at: "2026-11-28T14:00:00.100000+00:00" },
      { total_value: 10010, recorded_at: "2026-11-28T14:00:00.900000+00:00" },
      { total_value: 10020, recorded_at: "2026-11-28T14:00:30.000000+00:00" },
    ]);
    expect(pts).toHaveLength(2);
    expect(pts[0].value).toBe(10010);
    expect(pts[1].time - pts[0].time).toBe(30);
  });
});

describe("TradeBar", () => {
  const trade: TradeResponse = {
    trade: { id: "1", ticker: "AAPL", side: "buy", quantity: 2, price: 190, total: 380, executed_at: "" },
    portfolio,
  };

  it("submits buy and sell with ticker and quantity, showing confirmation", async () => {
    const onTrade = vi.fn(() => Promise.resolve(trade));
    render(<TradeBar ticker="AAPL" onTickerChange={vi.fn()} onTrade={onTrade} />);
    const qty = screen.getByTestId("trade-quantity");
    await userEvent.clear(qty);
    await userEvent.type(qty, "2");
    await userEvent.click(screen.getByTestId("trade-buy"));
    expect(onTrade).toHaveBeenCalledWith("AAPL", 2, "buy");
    expect(await screen.findByTestId("trade-success")).toHaveTextContent("Bought 2 AAPL at $190.00");
    await userEvent.click(screen.getByTestId("trade-sell"));
    expect(onTrade).toHaveBeenLastCalledWith("AAPL", 2, "sell");
  });

  it("shows server errors", async () => {
    const onTrade = vi.fn(() => Promise.reject(new Error("Insufficient cash: need $1,905.00, have $1,200.00")));
    render(<TradeBar ticker="AAPL" onTickerChange={vi.fn()} onTrade={onTrade} />);
    await userEvent.click(screen.getByTestId("trade-buy"));
    expect(await screen.findByTestId("trade-error")).toHaveTextContent("Insufficient cash");
  });

  it("validates quantity before calling the server", async () => {
    const onTrade = vi.fn();
    render(<TradeBar ticker="AAPL" onTickerChange={vi.fn()} onTrade={onTrade} />);
    await userEvent.clear(screen.getByTestId("trade-quantity"));
    await userEvent.click(screen.getByTestId("trade-sell"));
    expect(screen.getByTestId("trade-error")).toHaveTextContent("Quantity must be greater than 0");
    expect(onTrade).not.toHaveBeenCalled();
  });
});
