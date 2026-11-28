import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Watchlist from "./Watchlist";
import { priceUpdate, watchItem } from "@/test/fixtures";
import type { PriceMap } from "@/lib/types";

function setup(prices: PriceMap = {}, overrides: Partial<React.ComponentProps<typeof Watchlist>> = {}) {
  const props: React.ComponentProps<typeof Watchlist> = {
    items: [watchItem("AAPL", 190), watchItem("MSFT", 420), watchItem("TSLA", 250)],
    prices,
    history: {},
    selected: "AAPL",
    onSelect: vi.fn(),
    onAdd: vi.fn(() => Promise.resolve()),
    onRemove: vi.fn(() => Promise.resolve()),
    ...overrides,
  };
  const utils = render(<Watchlist {...props} />);
  return { ...utils, props };
}

describe("Watchlist", () => {
  it("renders rows with live price and daily change", () => {
    setup({ AAPL: priceUpdate("AAPL", { price: 191.5, day_change_percent: 0.79 }) });
    expect(screen.getByTestId("watchlist-row-AAPL")).toHaveAttribute("data-selected", "true");
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("191.50");
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent("+0.79%");
    // Falls back to the REST price when no SSE price arrived yet
    expect(screen.getByTestId("watchlist-price-MSFT")).toHaveTextContent("420.00");
    expect(screen.getByTestId("sparkline-TSLA")).toBeInTheDocument();
  });

  it("flashes only on up/down ticks, never on flat", () => {
    setup({
      AAPL: priceUpdate("AAPL", { direction: "up", price: 191 }),
      MSFT: priceUpdate("MSFT", { direction: "flat" }),
      TSLA: priceUpdate("TSLA", { direction: "down", price: 249 }),
    });
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveClass("flash-up");
    expect(screen.getByTestId("watchlist-price-TSLA")).toHaveClass("flash-down");
    const msft = screen.getByTestId("watchlist-price-MSFT");
    expect(msft).not.toHaveClass("flash-up");
    expect(msft).not.toHaveClass("flash-down");
  });

  it("removes the flash class after the fade and re-applies it on the next tick", () => {
    const { rerender, props } = setup({ AAPL: priceUpdate("AAPL", { direction: "up", timestamp: 1 }) });
    const el = screen.getByTestId("watchlist-price-AAPL");
    // jsdom has no AnimationEvent, so React may listen for the webkit-prefixed name.
    fireEvent.animationEnd(el);
    fireEvent(el, new Event("webkitAnimationEnd", { bubbles: true }));
    expect(screen.getByTestId("watchlist-price-AAPL")).not.toHaveClass("flash-up");

    rerender(<Watchlist {...props} prices={{ AAPL: priceUpdate("AAPL", { direction: "down", timestamp: 2 }) }} />);
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveClass("flash-down");

    rerender(<Watchlist {...props} prices={{ AAPL: priceUpdate("AAPL", { direction: "flat", timestamp: 3 }) }} />);
    expect(screen.getByTestId("watchlist-price-AAPL")).not.toHaveClass("flash-down");
  });

  it("selects a ticker on click", async () => {
    const { props } = setup();
    await userEvent.click(screen.getByTestId("watchlist-row-MSFT"));
    expect(props.onSelect).toHaveBeenCalledWith("MSFT");
  });

  it("adds a ticker (upper-cased) and clears the input", async () => {
    const { props } = setup();
    const input = screen.getByTestId("watchlist-add-input");
    await userEvent.type(input, "pypl");
    await userEvent.click(screen.getByTestId("watchlist-add-button"));
    expect(props.onAdd).toHaveBeenCalledWith("PYPL");
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("shows the server error when adding fails", async () => {
    setup({}, { onAdd: vi.fn(() => Promise.reject(new Error("AAPL is already on the watchlist"))) });
    await userEvent.type(screen.getByTestId("watchlist-add-input"), "aapl{enter}");
    expect(await screen.findByTestId("watchlist-error")).toHaveTextContent("AAPL is already on the watchlist");
  });

  it("removes a ticker without selecting it", async () => {
    const { props } = setup();
    await userEvent.click(screen.getByTestId("watchlist-remove-TSLA"));
    expect(props.onRemove).toHaveBeenCalledWith("TSLA");
    expect(props.onSelect).not.toHaveBeenCalled();
  });
});
