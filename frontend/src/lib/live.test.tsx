import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type * as React from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveState } from "./live";

const apiMock = vi.fn();
vi.mock("@/lib/api", () => ({ api: (...args: unknown[]) => apiMock(...args) }));
const toastInfo = vi.fn();
vi.mock("sonner", () => ({ toast: { info: (...args: unknown[]) => toastInfo(...args) } }));

const { useLiveSync } = await import("./live");

function state(version: string, pending: number, id?: string): LiveState {
  return {
    version,
    scope: "workspace",
    turf_id: "t1",
    pending_requests: pending,
    latest_request: id
      ? { id, reference: "TB-1", name: "Rangers", field: "Field A", start: "2026-11-19T12:00:00Z", created_at: "" }
      : null,
  };
}

describe("useLiveSync", () => {
  beforeEach(() => {
    apiMock.mockReset();
    toastInfo.mockReset();
  });

  it("refetches loaded data and notifies when a new booking request arrives", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
    apiMock.mockResolvedValueOnce(state("v1", 0));
    const { result } = renderHook(() => useLiveSync("workspace"), { wrapper });
    await waitFor(() => expect(result.current?.version).toBe("v1"));
    expect(invalidate).not.toHaveBeenCalled();

    apiMock.mockResolvedValueOnce(state("v2", 1, "b1"));
    await act(() => client.refetchQueries({ queryKey: ["live", "workspace"] }));
    await waitFor(() => expect(result.current?.version).toBe("v2"));
    expect(invalidate).toHaveBeenCalled();
    expect(toastInfo).toHaveBeenCalledWith("New booking request from Rangers", expect.anything());
    await waitFor(() => expect(document.title.startsWith("(1)")).toBe(true));

    // Same version again: nothing to do.
    invalidate.mockClear();
    apiMock.mockResolvedValueOnce(state("v2", 1, "b1"));
    await act(() => client.refetchQueries({ queryKey: ["live", "workspace"] }));
    expect(invalidate).not.toHaveBeenCalled();
    expect(toastInfo).toHaveBeenCalledTimes(1);
  });
});
