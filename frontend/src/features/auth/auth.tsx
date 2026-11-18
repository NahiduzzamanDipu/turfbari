import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import type * as React from "react";
import { Navigate, useLocation } from "react-router";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

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
  const allowed =
    role === "admin" ? me.data.user?.is_platform_admin : me.data.memberships.length > 0;
  if (!allowed) return <Navigate to={me.data.home === location.pathname ? "/" : me.data.home} replace />;
  return <>{children}</>;
}
