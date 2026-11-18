import { CheckCircle2, CircleAlert, RefreshCw, ServerCrash } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "./useHealth";

const LABELS: Record<string, string> = { database: "MySQL database", cache: "Cache" };

/**
 * Phase 2 landing: confirms the React app can reach the Django API and its services.
 * Replaced by the public homepage in Phase 5.
 */
export function SystemStatusPage() {
  const health = useHealth();

  return (
    <main className="relative min-h-dvh overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_10%_-10%,color-mix(in_oklch,var(--accent)_35%,transparent),transparent),radial-gradient(50rem_30rem_at_110%_10%,color-mix(in_oklch,var(--primary)_25%,transparent),transparent)]"
      />
      <div className="relative mx-auto flex max-w-xl flex-col gap-8 px-4 py-16 sm:py-24">
        <Logo />
        <div>
          <h1 className="font-display text-5xl font-extrabold uppercase leading-none tracking-tight sm:text-6xl">
            Smart turf management
          </h1>
          <p className="mt-3 text-muted-foreground">
            Development build. This page checks that the web app can reach the TurfBari API and its services.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>System status</CardTitle>
            <CardDescription>Live from GET /api/health/</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {health.isPending && (
              <>
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-6 w-1/2" />
              </>
            )}

            {health.isError && (
              <div role="alert" className="flex items-start gap-3 text-sm">
                <ServerCrash className="mt-0.5 size-5 text-destructive" />
                <div>
                  <p className="font-medium">API unreachable</p>
                  <p className="text-muted-foreground">
                    Start Docker services and the Django server, then retry. ({health.error.message})
                  </p>
                </div>
              </div>
            )}

            {health.isSuccess &&
              Object.entries(health.data.checks).map(([name, state]) => (
                <div key={name} className="flex items-center justify-between text-sm">
                  <span>{LABELS[name] ?? name}</span>
                  <span
                    className={
                      state === "up"
                        ? "inline-flex items-center gap-1.5 font-medium text-primary"
                        : "inline-flex items-center gap-1.5 font-medium text-destructive"
                    }
                  >
                    {state === "up" ? <CheckCircle2 className="size-4" /> : <CircleAlert className="size-4" />}
                    {state === "up" ? "Up" : "Down"}
                  </span>
                </div>
              ))}

            <Button
              variant="outline"
              size="sm"
              className="mt-2 self-start"
              onClick={() => void health.refetch()}
              disabled={health.isFetching}
            >
              <RefreshCw className={health.isFetching ? "animate-spin" : undefined} />
              Check again
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
