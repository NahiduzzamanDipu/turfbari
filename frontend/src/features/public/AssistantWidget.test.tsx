import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantWidget } from "./AssistantWidget";

const mocks = vi.hoisted(() => ({ api: vi.fn(), language: "en" as "en" | "bn" }));
vi.mock("@/lib/api", () => ({ api: mocks.api }));
vi.mock("@/lib/i18n", () => ({ useLanguage: () => ({ language: mocks.language, t: (value: string) => value }) }));

beforeEach(() => {
  mocks.language = "en";
  mocks.api.mockReset();
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe("homepage AI assistant", () => {
  it("does not appear when the platform disables it", async () => {
    mocks.api.mockResolvedValue({ enabled: false });
    render(<MemoryRouter><AssistantWidget /></MemoryRouter>);
    await waitFor(() => expect(mocks.api).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Ask TURFBARI Assistant" })).not.toBeInTheDocument();
  });

  it("opens in the selected language and submits a real backend conversation", async () => {
    mocks.language = "bn";
    mocks.api.mockImplementation((path: string) => {
      if (path === "/public/assistant/status/") return Promise.resolve({
        enabled: true,
        available: true,
        service_state: "ready",
        service_mode: "local_knowledge",
        display_name: "TURFBARI Assistant",
        welcome: { en: "Hello", bn: "বাংলায় স্বাগতম" },
        suggested_questions: [{ en: "What is TURFBARI?", bn: "TURFBARI কী?" }],
        privacy_note: "Do not share private information.",
      });
      if (path === "/public/assistant/conversations/") return Promise.resolve({ conversation_id: "conversation-1", conversation_token: "secure-token" });
      if (path === "/public/assistant/messages/") return Promise.resolve({ message: { id: 12, content: "TURFBARI manages turf bookings." }, links: [], sources: [] });
      return Promise.resolve({});
    });
    render(<MemoryRouter><AssistantWidget /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Ask TURFBARI Assistant" }));
    expect(await screen.findByText("বাংলায় স্বাগতম")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "TURFBARI কী?" }));
    expect(await screen.findByText("TURFBARI manages turf bookings.")).toBeInTheDocument();
    const request = mocks.api.mock.calls.find(([path]) => path === "/public/assistant/messages/");
    expect(request?.[1].json).toMatchObject({ language: "bn", conversation_token: "secure-token", message: "TURFBARI কী?" });
  });
});
