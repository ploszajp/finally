import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { appendHistory, MAX_HISTORY_POINTS, usePriceStream } from "./usePriceStream";
import { priceUpdate } from "@/test/fixtures";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent<string>);
  }
  fail(state: number) {
    this.readyState = state;
    this.onerror?.();
  }
}

describe("appendHistory", () => {
  it("appends one point per second and replaces within the same second", () => {
    let h = appendHistory({}, { AAPL: priceUpdate("AAPL", { price: 1, timestamp: 10.1 }) });
    h = appendHistory(h, { AAPL: priceUpdate("AAPL", { price: 2, timestamp: 10.6 }) });
    h = appendHistory(h, { AAPL: priceUpdate("AAPL", { price: 3, timestamp: 11.1 }) });
    expect(h.AAPL).toEqual([
      { time: 10, value: 2 },
      { time: 11, value: 3 },
    ]);
  });

  it("drops tickers missing from the latest event and caps length", () => {
    let h = appendHistory({}, { AAPL: priceUpdate("AAPL"), MSFT: priceUpdate("MSFT") });
    h = appendHistory(h, { AAPL: priceUpdate("AAPL", { timestamp: 1_800_000_001 }) });
    expect(Object.keys(h)).toEqual(["AAPL"]);

    const long = { AAPL: Array.from({ length: MAX_HISTORY_POINTS }, (_, i) => ({ time: i, value: i })) };
    const next = appendHistory(long, { AAPL: priceUpdate("AAPL", { timestamp: MAX_HISTORY_POINTS + 5 }) });
    expect(next.AAPL).toHaveLength(MAX_HISTORY_POINTS);
  });
});

describe("usePriceStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("tracks connection status and prices", () => {
    const { result, unmount } = renderHook(() => usePriceStream());
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe("/api/stream/prices");
    expect(result.current.status).toBe("reconnecting");

    act(() => es.open());
    expect(result.current.status).toBe("connected");

    act(() => es.emit({ AAPL: priceUpdate("AAPL", { price: 191 }) }));
    expect(result.current.prices.AAPL.price).toBe(191);
    expect(result.current.history.AAPL).toHaveLength(1);

    act(() => es.fail(FakeEventSource.CONNECTING));
    expect(result.current.status).toBe("reconnecting");

    unmount();
    expect(es.closed).toBe(true);
  });

  it("shows disconnected when the browser gives up, then reconnects", () => {
    const { result } = renderHook(() => usePriceStream());
    const es = FakeEventSource.instances[0];
    act(() => es.fail(FakeEventSource.CLOSED));
    expect(result.current.status).toBe("disconnected");
    act(() => vi.advanceTimersByTime(3000));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => FakeEventSource.instances[1].open());
    expect(result.current.status).toBe("connected");
  });
});
