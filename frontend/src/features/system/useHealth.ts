import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

const healthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  checks: z.record(z.string(), z.enum(["up", "down"])),
});

export type HealthResponse = z.infer<typeof healthSchema>;

/** Health returns 200 (ok) or 503 (degraded) — both carry per-service results we want to show. */
export function useHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: async () => {
      const response = await fetch("/api/health/", { headers: { Accept: "application/json" } });
      const parsed = healthSchema.safeParse(await response.json().catch(() => null));
      if (!parsed.success) {
        throw new Error(
          response.ok
            ? "Unexpected response — is another app running on the API port?"
            : `HTTP ${response.status}`,
        );
      }
      return parsed.data;
    },
    retry: false,
  });
}
