import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Link } from "react-router";
import type { BadgeTone } from "@/components/ui/form";
import { api } from "@/lib/api";
import type { SubscriptionOverview, SubscriptionStanding } from "@/lib/types";
import { cn } from "@/lib/utils";

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
export const fmtPlainDate = (d: string | null) => (d ? dateFmt.format(new Date(`${d}T00:00:00`)) : "—");

export const STANDING_TONE: Record<SubscriptionStanding["state"], BadgeTone> = {
  active: "green",
  expiring: "amber",
  grace: "red",
  expired: "red",
  none: "neutral",
};
export const STANDING_LABEL: Record<SubscriptionStanding["state"], string> = {
  active: "Active",
  expiring: "Ending soon",
  grace: "Ended — grace period",
  expired: "Expired",
  none: "No plan",
};

export function useSubscription() {
  return useQuery({
    queryKey: ["ws", "subscription"],
    queryFn: () => api<SubscriptionOverview>("/workspace/subscription/"),
  });
}

/** Thin banner for the workspace shell when the plan is ending or has ended. */
export function SubscriptionBanner() {
  const sub = useSubscription();
  const s = sub.data?.standing;
  if (!s || s.state === "active") return null;
  if (sub.data?.periods.some((p) => p.state === "scheduled") && s.state === "expiring") return null;
  const urgent = s.state !== "expiring";
  const text =
    s.state === "expiring"
      ? `Your ${s.plan?.name ?? ""} plan ends in ${s.days_left} day${s.days_left === 1 ? "" : "s"}. It does not renew automatically.`
      : s.state === "grace"
        ? `Your plan has ended. Renew by ${fmtPlainDate(s.grace_until)} to keep taking bookings.`
        : "No active plan: your turf is hidden and new bookings are paused.";
  return (
    <div
      role="status"
      className={cn(
        "mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg px-4 py-2 text-sm",
        urgent ? "bg-destructive/10 text-destructive" : "bg-amber-400/15 text-amber-800 dark:text-amber-200",
      )}
    >
      <span className="flex items-center gap-2">
        {urgent ? <AlertTriangle className="size-4" /> : <CheckCircle2 className="size-4" />}
        {text}
      </span>
      <Link to="/workspace/subscription" className="font-semibold underline">
        Renew now
      </Link>
    </div>
  );
}
