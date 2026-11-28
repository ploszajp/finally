import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatPanel from "./ChatPanel";
import { chatMessage, jsonResponse } from "@/test/fixtures";
import type { ChatResponse } from "@/lib/types";

function mockFetch(handler: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(handler);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("ChatPanel", () => {
  it("restores history and renders inline action results", async () => {
    mockFetch(() =>
      jsonResponse({
        messages: [
          chatMessage({ role: "user", content: "Buy AAPL and TSLA", actions: null }),
          chatMessage({
            content: "Done.",
            actions: {
              watchlist_changes: [{ ticker: "PYPL", action: "add", status: "executed", error: null }],
              trades: [
                { ticker: "AAPL", side: "buy", quantity: 5, status: "executed", price: 191.23, error: null },
                { ticker: "TSLA", side: "buy", quantity: 1000, status: "rejected", price: null, error: "Insufficient cash" },
              ],
              error: null,
            },
          }),
        ],
      }),
    );
    render(<ChatPanel open onToggle={vi.fn()} />);
    const actions = await screen.findAllByTestId("chat-action");
    expect(screen.getAllByTestId("chat-message")).toHaveLength(2);
    expect(actions).toHaveLength(3);
    expect(actions[0]).toHaveAttribute("data-kind", "watchlist");
    expect(actions[0]).toHaveTextContent("Added PYPL to watchlist");
    expect(actions[1]).toHaveAttribute("data-status", "executed");
    expect(actions[1]).toHaveTextContent("Bought 5 AAPL at $191.23");
    expect(actions[2]).toHaveAttribute("data-status", "rejected");
    expect(actions[2]).toHaveTextContent("Insufficient cash");
  });

  it("shows a loading indicator while waiting and refreshes after executed actions", async () => {
    let resolveChat!: (r: Response) => void;
    mockFetch((url) => {
      if (url === "/api/chat/history") return jsonResponse({ messages: [] });
      return new Promise<Response>((r) => (resolveChat = r));
    });
    const onActionsExecuted = vi.fn();
    render(<ChatPanel open onToggle={vi.fn()} onActionsExecuted={onActionsExecuted} />);

    await userEvent.type(screen.getByTestId("chat-input"), "buy");
    await userEvent.click(screen.getByTestId("chat-send"));
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-send")).toBeDisabled();
    expect(screen.getByText("buy")).toBeInTheDocument(); // optimistic user message

    const body: ChatResponse = {
      user_message: chatMessage({ id: "u1", role: "user", content: "buy", actions: null }),
      assistant_message: chatMessage({
        id: "a1",
        content: "Mock mode: processing your request. Buying 1 share of AAPL.",
        actions: {
          watchlist_changes: [],
          trades: [{ ticker: "AAPL", side: "buy", quantity: 1, status: "executed", price: 190, error: null }],
          error: null,
        },
      }),
    };
    resolveChat(await jsonResponse(body));

    await waitFor(() => expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument());
    expect(screen.getAllByTestId("chat-message")).toHaveLength(2);
    expect(screen.getByText(/Buying 1 share of AAPL/)).toBeInTheDocument();
    expect(onActionsExecuted).toHaveBeenCalledTimes(1);
  });

  it("marks LLM failures as errors without action lists", async () => {
    mockFetch(() =>
      jsonResponse({
        messages: [
          chatMessage({
            content: "The AI assistant is unavailable right now. Please try again in a moment.",
            actions: { watchlist_changes: [], trades: [], error: "llm_unavailable" },
          }),
        ],
      }),
    );
    render(<ChatPanel open onToggle={vi.fn()} />);
    const msg = await screen.findByTestId("chat-message");
    expect(msg).toHaveAttribute("data-error", "true");
    expect(screen.queryByTestId("chat-action")).not.toBeInTheDocument();
  });

  it("shows a friendly error and restores the draft when the request fails", async () => {
    mockFetch((url) =>
      url === "/api/chat/history" ? jsonResponse({ messages: [] }) : Promise.reject(new TypeError("Failed to fetch")),
    );
    render(<ChatPanel open onToggle={vi.fn()} />);
    await userEvent.type(screen.getByTestId("chat-input"), "hello{enter}");
    expect(await screen.findByTestId("chat-error")).toHaveTextContent("Cannot reach the server");
    expect(screen.getByTestId("chat-input")).toHaveValue("hello");
    expect(screen.queryByTestId("chat-message")).not.toBeInTheDocument();
  });

  it("collapses to a toggle", async () => {
    mockFetch(() => jsonResponse({ messages: [] }));
    const onToggle = vi.fn();
    render(<ChatPanel open={false} onToggle={onToggle} />);
    expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("chat-toggle"));
    expect(onToggle).toHaveBeenCalled();
  });
});
