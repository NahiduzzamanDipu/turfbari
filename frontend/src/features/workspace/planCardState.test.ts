import { describe, expect, it } from "vitest";
import { resolvePlanCardState } from "./planCardState";

describe("resolvePlanCardState", () => {
  it.each(["active", "expiring", "grace", "expired", "none"] as const)(
    "keeps the actual %s subscription state",
    (standingState) => {
      expect(resolvePlanCardState({
        turfStatus: "active", standingState, hasCurrent: standingState === "active" || standingState === "expiring",
        invoiceStatus: null,
      })).toBe(standingState);
    },
  );

  it("shows pending approval only when there is no current plan", () => {
    expect(resolvePlanCardState({ turfStatus: "active", standingState: "none", hasCurrent: false, invoiceStatus: "pending_verification" })).toBe("pending");
    expect(resolvePlanCardState({ turfStatus: "active", standingState: "active", hasCurrent: true, invoiceStatus: "pending_verification" })).toBe("active");
  });

  it("prioritizes the actual suspended account state", () => {
    expect(resolvePlanCardState({ turfStatus: "suspended", standingState: "active", hasCurrent: true, invoiceStatus: null })).toBe("suspended");
  });
});
