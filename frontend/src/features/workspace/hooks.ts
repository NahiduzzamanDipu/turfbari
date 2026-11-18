import { useQuery } from "@tanstack/react-query";
import { useMe } from "@/features/auth/auth";
import { ApiError, api } from "@/lib/api";
import type { Field } from "@/lib/types";

export function useFields() {
  return useQuery({ queryKey: ["ws", "fields"], queryFn: () => api<Field[]>("/workspace/fields/") });
}

export function useIsOwner(): boolean {
  const me = useMe();
  const m = me.data?.memberships.find((x) => x.turf_id === me.data?.active_turf_id);
  return m?.role === "owner";
}

/** First readable message from an API error (field errors first). */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const first = error.fields ? Object.values(error.fields).flat()[0] : undefined;
    return typeof first === "string" ? first : error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}
