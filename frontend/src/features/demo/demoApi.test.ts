import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ api: apiMock }));

import { demoApi } from "./demoApi";

describe("demoApi", () => {
  beforeEach(() => apiMock.mockReset().mockResolvedValue({ ok: true }));

  it("routes public demo reads through the public API namespace", async () => {
    await demoApi("/workspace/");
    expect(apiMock).toHaveBeenCalledWith("/public/demo/workspace/", {});
  });

  it("routes interactive booking and owner mutations through that same public namespace", async () => {
    const init = { method: "POST", json: { name: "Demo" } };
    await demoApi("/bookings/", init);
    expect(apiMock).toHaveBeenCalledWith("/public/demo/bookings/", init);
    await demoApi("/bookings/booking-id/", { method: "PATCH", json: { action: "approve" } });
    expect(apiMock).toHaveBeenLastCalledWith("/public/demo/bookings/booking-id/", {
      method: "PATCH",
      json: { action: "approve" },
    });
  });
});
