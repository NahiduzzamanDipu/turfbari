import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CalendarDays, Clock, Coins, Plus, TrendingUp, Users } from "lucide-react";
import { Link } from "react-router";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, EmptyState, ErrorState, STATUS_TONE } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/auth";
import { api } from "@/lib/api";
import { fmtDay, fmtRange } from "@/lib/format";
import type { Dashboard } from "@/lib/types";
import { formatBDT } from "@/lib/utils";

export function DashboardPage() {
  const data = useQuery({ queryKey: ["ws", "dashboard"], queryFn: () => api<Dashboard>("/workspace/dashboard/") });

  if (data.isPending) return <Skeleton className="h-64" />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  const d = data.data;
  const series = d.revenue_series.map((p) => ({
    day: new Date(`${p.date}T12:00:00+06:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" }),
    revenue: Number(p.revenue),
  }));

  return (
    <>
      <PageHeader
        title={d.turf.name}
        description={d.turf.status !== "active" ? "This turf is suspended — view-only until TurfBari reactivates it." : "Today at a glance."}
        actions={
          <Button asChild>
            <Link to="/workspace/bookings?new=1">
              <Plus /> New booking
            </Link>
          </Button>
        }
      />
      {d.pending_requests > 0 && (
        <Link
          to="/workspace/payments"
          className="mb-4 flex items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        >
          <AlertCircle className="size-5 shrink-0" />
          <span>
            <strong>{d.pending_requests}</strong> bKash payment{d.pending_requests === 1 ? "" : "s"} waiting for
            verification. Review now →
          </span>
        </Link>
      )}
      {!d.turf.is_listed && d.role === "owner" && (
        <Link to="/workspace/settings" className="mb-4 block rounded-xl border p-4 text-sm hover:bg-secondary">
          Your booking page isn't published yet, so its link and QR code don't open. <strong className="text-primary">Publish it in Settings →</strong>
        </Link>
      )}
      <DashboardSmsLine />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Today's bookings" icon={<CalendarDays />} value={d.today.bookings} hint={`${d.today.hours_booked} hours booked`} />
        <StatCard label="Collected today" icon={<Coins />} value={formatBDT(d.today.revenue)} />
        <StatCard
          label="This month"
          icon={<TrendingUp />}
          value={formatBDT(d.month.revenue)}
          hint={d.month.net !== null ? `Net after expenses ${formatBDT(d.month.net)}` : `${d.month.bookings} bookings`}
        />
        <StatCard label="Dues outstanding" icon={<Users />} value={formatBDT(d.outstanding_due)} hint={`${d.customers} customers`} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_24rem]">
        <Card>
          <CardHeader>
            <CardTitle>Collections, last 14 days</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ left: 0, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} width={56} tickFormatter={(v: number) => `৳${v >= 1000 ? `${v / 1000}k` : v}`} />
                <Tooltip formatter={(v) => formatBDT(Number(v))} contentStyle={{ borderRadius: 8, border: "1px solid var(--border)" }} />
                <Area type="monotone" dataKey="revenue" name="Collected" stroke="var(--chart-1)" strokeWidth={2} fill="url(#rev)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="size-4" /> Coming up
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {d.upcoming.length === 0 && <EmptyState title="Nothing booked ahead" />}
            {d.upcoming.map((b) => (
              <Link key={b.id} to={`/workspace/bookings?open=${b.id}`} className="flex items-start justify-between gap-3 rounded-lg p-2 hover:bg-secondary">
                <div className="min-w-0">
                  <p className="truncate font-medium">{b.team_name || b.customer.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {fmtDay(b.start)} · {fmtRange(b.start, b.end)} · {b.field_name}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[b.status]}>{b.status_label}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

/** One line of this turf's SMS usage (owners and managers allowed to see SMS). */
function DashboardSmsLine() {
  const can = useCan("view_sms");
  const usage = useQuery({
    queryKey: ["ws", "sms", "usage"],
    queryFn: () =>
      api<{ this_month: { sent: number; failed: number; pending: number }; all_time: { sent: number } }>("/workspace/sms/usage/"),
    enabled: can,
  });
  if (!can || !usage.data) return null;
  const m = usage.data.this_month;
  return (
    <Link to="/workspace/sms" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border p-3 text-sm hover:bg-secondary">
      <span>
        SMS this month: <strong className="tabular">{m.sent}</strong> sent
        {m.failed > 0 && <span className="text-destructive"> · {m.failed} failed</span>}
        {m.pending > 0 && <span className="text-muted-foreground"> · {m.pending} waiting</span>}
        <span className="text-muted-foreground"> · {usage.data.all_time.sent} all time</span>
      </span>
      <span className="font-semibold text-primary">SMS usage →</span>
    </Link>
  );
}
