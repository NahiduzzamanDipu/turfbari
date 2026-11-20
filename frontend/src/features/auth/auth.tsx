import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import type * as React from "react";
import { Navigate, useLocation } from "react-router";
import { api } from "@/lib/api";
import type { ManagerPermissions, Me } from "@/lib/types";

export const meKey = ["auth", "me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: () => api<Me>("/auth/me/"), staleTime: 60_000 });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout/", { method: "POST" }),
    onSuccess: () => {
      qc.clear();
      window.location.assign("/login");
    },
  });
}

/** The active workspace membership (role + manager permissions), if any. */
export function useActiveMembership() {
  const me = useMe();
  const data = me.data;
  return data?.memberships.find((m) => m.turf_id === data.active_turf_id) ?? data?.memberships[0];
}

/** Owners can do everything; managers only what their owner switched on. UX only — the API enforces it. */
export function useCan(permission: keyof ManagerPermissions) {
  const membership = useActiveMembership();
  return membership?.role === "owner" || Boolean(membership?.permissions?.[permission]);
}

export function useSwitchTurf() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (turfId: string) => api<Me>("/auth/switch-turf/", { method: "POST", json: { turf_id: turfId } }),
    onSuccess: (me) => {
      qc.clear();
      qc.setQueryData(meKey, me);
    },
  });
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <Loader2 className="size-8 animate-spin text-primary" />
    </div>
  );
}

/** Client-side routing guard only. The API enforces every permission server-side. */
export function RequireRole({ role, children }: { role: "admin" | "workspace"; children: React.ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <FullPageSpinner />;
  if (!me.data?.authenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (me.data.user?.must_change_password) return <Navigate to="/set-password" replace />;
  if (role === "workspace" && me.data.user?.legal_pending) {
    return <Navigate to={`/accept-terms?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  const allowed =
    role === "admin" ? me.data.user?.is_platform_admin : me.data.memberships.length > 0;
  if (!allowed) return <Navigate to={me.data.home === location.pathname ? "/" : me.data.home} replace />;
  return <>{children}</>;
}
