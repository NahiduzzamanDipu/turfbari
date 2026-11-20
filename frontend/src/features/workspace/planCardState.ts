import type { SubscriptionStanding, SubscriptionOverview } from "@/lib/types";

export type PlanCardState = SubscriptionStanding["state"] | "pending" | "suspended";

export function resolvePlanCardState(input: {
  turfStatus: SubscriptionOverview["turf_status"];
  standingState: SubscriptionStanding["state"];
  hasCurrent: boolean;
  invoiceStatus: string | null;
}): PlanCardState {
  if (input.turfStatus === "suspended") return "suspended";
  if (!input.hasCurrent && input.invoiceStatus === "pending_verification") return "pending";
  return input.standingState;
}
