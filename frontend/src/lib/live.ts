import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { api } from "@/lib/api";

/** What GET /api/live/ returns: a change "version" plus counts of work waiting for someone. */
export interface LiveState {
  version: string;
  scope: "workspace" | "admin" | "none";
  turf_id?: string;
  pending_requests?: number;
  latest_request?: {
    id: string;
    reference: string;
    name: string;
    field: string;
    start: string;
    created_at: string;
  } | null;
  pending_applications?: number;
  pending_payments?: number;
}

export const LIVE_POLL_MS = 5_000;
export const liveKey = (area: string) => ["live", area] as const;

const slotTime = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "Asia/Dhaka",
});

/**
 * Keeps every open screen up to date without reloading: polls the change version, refetches all
 * loaded data when it moves, and pops a notification when new work arrives.
 */
export function useLiveSync(area: "admin" | "workspace") {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const live = useQuery({
    queryKey: liveKey(area),
    queryFn: () => api<LiveState>(`/live/?area=${area}`),
    refetchInterval: LIVE_POLL_MS,
    staleTime: 0,
    retry: false,
  });
  const previous = useRef<LiveState | null>(null);

  useEffect(() => {
    const now = live.data;
    if (!now) return;
    const before = previous.current;
    previous.current = now;
    if (!before || before.version === now.version || before.turf_id !== now.turf_id) return;

    // Something changed (here or on another device): refresh everything that's loaded.
    void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "live" });

    if (area === "workspace") {
      const req = now.latest_request;
      if (req && req.id !== before.latest_request?.id && (now.pending_requests ?? 0) > (before.pending_requests ?? 0)) {
        toast.info(`New booking request from ${req.name}`, {
          description: `${req.field} · ${slotTime.format(new Date(req.start))} · ${req.reference}`,
          duration: 15_000,
          action: { label: "Review", onClick: () => navigate("/workspace/bookings?status=pending") },
        });
      }
    } else {
      if ((now.pending_applications ?? 0) > (before.pending_applications ?? 0)) {
        toast.info("New turf application", {
          duration: 15_000,
          action: { label: "Open", onClick: () => navigate("/admin/applications") },
        });
      }
      if ((now.pending_payments ?? 0) > (before.pending_payments ?? 0)) {
        toast.info("New payment to verify", {
          duration: 15_000,
          action: { label: "Open", onClick: () => navigate("/admin/billing") },
        });
      }
    }
  }, [live.data, area, qc, navigate]);

  // Unread count in the browser tab title, so it's visible from other tabs too.
  const waiting =
    area === "workspace"
      ? (live.data?.pending_requests ?? 0)
      : (live.data?.pending_applications ?? 0) + (live.data?.pending_payments ?? 0);
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, "");
    document.title = waiting > 0 ? `(${waiting}) ${base}` : base;
    return () => {
      document.title = document.title.replace(/^\(\d+\) /, "");
    };
  }, [waiting]);

  return live.data;
}
