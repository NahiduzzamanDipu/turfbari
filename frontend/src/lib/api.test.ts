import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";
import { formatBDT } from "./utils";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("api()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "turfbari_csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("prefixes /api and returns parsed JSON", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { status: "ok" }));
    await expect(api("/health/")).resolves.toEqual({ status: "ok" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/health/");
  });

  it("sends the CSRF cookie value on unsafe methods", async () => {
    document.cookie = "turfbari_csrftoken=abc123";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(201, { id: 1 }));
    await api("/things/", { method: "POST", json: { a: 1 } });
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("X-CSRFToken")).toBe("abc123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("does not send CSRF on GET", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, {}));
    await api("/things/");
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.has("X-CSRFToken")).toBe(false);
  });

  it("throws ApiError carrying the backend envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(400, { error: { code: "validation_error", message: "Fix fields", fields: { phone: ["Bad"] } } }),
    );
    const error = await api("/x/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, code: "validation_error", fields: { phone: ["Bad"] } });
  });
});

describe("formatBDT", () => {
  it("formats taka amounts", () => {
    expect(formatBDT("1200.00")).toContain("1,200");
  });
});
