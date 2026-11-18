import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SystemStatusPage } from "./SystemStatusPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SystemStatusPage />
    </QueryClientProvider>,
  );
}

function mockFetch(status: number, body: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

describe("SystemStatusPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows each service as up", async () => {
    mockFetch(200, { status: "ok", checks: { database: "up", cache: "up" } });
    renderPage();
    expect(await screen.findByText("MySQL database")).toBeInTheDocument();
    expect(screen.getAllByText("Up")).toHaveLength(2);
  });

  it("shows a down service when the backend is degraded", async () => {
    mockFetch(503, { status: "degraded", checks: { database: "down", cache: "up" } });
    renderPage();
    expect(await screen.findByText("Down")).toBeInTheDocument();
    expect(screen.getByText("Up")).toBeInTheDocument();
  });

  it("shows unreachable when the proxy cannot reach the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("API unreachable");
  });

  it("shows an error instead of crashing on an unexpected response shape", async () => {
    mockFetch(200, { status: "ok", service: "some-other-app" });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unexpected response");
  });
});
