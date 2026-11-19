import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarPlus, CheckCircle2, ChevronLeft, ChevronRight, History, Loader2, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Dialog, EmptyState, ErrorState, FormField, Input, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { fmtPlainDate } from "@/features/workspace/SubscriptionBanner";
import { ApiError, api } from "@/lib/api";
import type { Paginated } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";

type SubState = "active" | "expiring" | "grace" | "expired" | "none";
interface SubRow {
  turf: { id: string; name: string; slug: string; status: string };
  owner: { name: string; email: string; phone: string } | null;
  state: SubState;
  plan: string | null;
  paid_until: string | null;
  days_left: number | null;
  grace_until: string | null;
}

const STATE: Record<SubState, { label: string; tone: BadgeTone }> = {
  active: { label: "Active", tone: "green" },
  expiring: { label: "Ending soon", tone: "amber" },
  grace: { label: "Grace period", tone: "red" },
  expired: { label: "Expired", tone: "neutral" },
  none: { label: "No plan", tone: "neutral" },
};
const FILTERS: { key: string; label: string; params: Record<string, string> }[] = [
  { key: "all", label: "All turfs", params: {} },
  { key: "soon", label: "Ending in 10 days", params: { ending_within: "10" } },
  { key: "grace", label: "Grace period", params: { state: "grace" } },
  { key: "expired", label: "Expired", params: { state: "expired" } },
  { key: "none", label: "No plan", params: { state: "none" } },
];

export function AdminSubscriptionsPage() {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [acting, setActing] = useState<{ row: SubRow; kind: "extend" | "end" | "history" } | null>(null);
  const params = FILTERS.find((f) => f.key === filter)!.params;
  const list = useQuery({
    queryKey: ["admin", "subscriptions", filter, q, page],
    queryFn: () =>
      api<Paginated<SubRow> & { counts: Partial<Record<SubState, number>>; grace_days: number }>(
        `/admin/subscriptions/?${new URLSearchParams({ ...params, q, page: String(page) })}`,
      ),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader
        title="Subscriptions"
        description="Every turf's paid time. Extend or end a plan with a reason (audited). To sell or renew a plan, use Assign plan on the Turfs page."
        actions={
          <Button asChild variant="outline">
            <Link to="/admin/turfs">Turfs &amp; plans</Link>
          </Button>
        }
      />
      {list.data && (
        <div className="mb-4 grid gap-3 sm:grid-cols-5">
          {(Object.keys(STATE) as SubState[]).map((s) => (
            <div key={s} className="rounded-xl border p-3">
              <p className="text-xs text-muted-foreground">{STATE[s].label}</p>
              <p className="tabular font-display text-2xl font-bold">{list.data.counts[s] ?? 0}</p>
            </div>
          ))}
        </div>
      )}
      <div className="mb-4 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2" role="tablist">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => {
                setFilter(f.key);
                setPage(1);
              }}
              className={cn("rounded-full border px-3 py-1.5 text-sm font-medium", filter === f.key ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
            >
              {f.label}
            </button>
          ))}
        </div>
        <Input
          className="lg:max-w-72"
          placeholder="Search turf or owner"
          aria-label="Search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-40" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.results.length === 0 && <EmptyState title="No turfs here" />}
          {list.data && list.data.results.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Turf</th>
                  <th>Owner</th>
                  <th>Plan</th>
                  <th>Paid until</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((r) => (
                  <tr key={r.turf.id}>
                    <td className="font-medium">
                      {r.turf.name}
                      {r.turf.status !== "active" && <span className="block text-xs text-destructive">Turf {r.turf.status}</span>}
                    </td>
                    <td className="text-sm">
                      {r.owner ? (
                        <>
                          {r.owner.name || r.owner.email}
                          <span className="block text-xs text-muted-foreground">{r.owner.phone || r.owner.email}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="text-sm">{r.plan ?? "—"}</td>
                    <td className="text-sm">
                      {r.paid_until ? fmtPlainDate(r.paid_until) : "—"}
                      {r.days_left !== null && (
                        <span className="block text-xs text-muted-foreground">
                          {r.days_left >= 0 ? `${r.days_left} days left` : `${-r.days_left} days ago`}
                        </span>
                      )}
                    </td>
                    <td>
                      <Badge tone={STATE[r.state].tone}>{STATE[r.state].label}</Badge>
                    </td>
                    <td className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="outline" onClick={() => setActing({ row: r, kind: "extend" })}>
                          <CalendarPlus /> Extend
                        </Button>
                        {(r.state === "active" || r.state === "expiring" || r.state === "grace") && (
                          <Button size="sm" variant="ghost" onClick={() => setActing({ row: r, kind: "end" })}>
                            <XCircle /> End
                          </Button>
                        )}
                        <Button size="icon" variant="ghost" aria-label={`History of ${r.turf.name}`} onClick={() => setActing({ row: r, kind: "history" })}>
                          <History />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {list.data && list.data.count > 20 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-sm">
              <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft />
              </Button>
              <span className="tabular">Page {page}</span>
              <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      {acting?.kind === "history" && <HistoryDialog row={acting.row} onClose={() => setActing(null)} />}
      {acting && acting.kind !== "history" && <ChangeDialog row={acting.row} kind={acting.kind} onClose={() => setActing(null)} />}
    </>
  );
}

function ChangeDialog({ row, kind, onClose }: { row: SubRow; kind: "extend" | "end"; onClose: () => void }) {
  const qc = useQueryClient();
  const [days, setDays] = useState("7");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api<SubRow>(`/admin/turfs/${row.turf.id}/${kind === "extend" ? "extend" : "end"}-subscription/`, {
        method: "POST",
        json: kind === "extend" ? { days: Number(days), reason } : { reason },
      }),
    onSuccess: (r) => {
      toast.success(kind === "extend" ? `${r.turf.name} now paid until ${r.paid_until ? fmtPlainDate(r.paid_until) : "—"}` : `${r.turf.name}'s plan has ended`);
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  return (
    <Dialog
      open
      onClose={onClose}
      title={kind === "extend" ? `Extend ${row.turf.name}` : `End ${row.turf.name}'s plan now?`}
      description={
        kind === "extend"
          ? "Adds free days to the current paid time (or starts complimentary days if the plan has ended)."
          : "Paid time stops today with no grace period: the booking page closes and the workspace becomes read-only until a plan is assigned."
      }
    >
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {kind === "extend" && (
          <FormField label="Days to add" error={fields?.days}>
            {(id) => <Input id={id} type="number" min={1} max={366} step={1} required value={days} onChange={(e) => setDays(e.target.value)} />}
          </FormField>
        )}
        <FormField label="Reason (kept in the audit log)" error={fields?.reason}>
          {(id) => <Input id={id} required minLength={5} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </FormField>
        {save.error && !fields && <p className="text-sm text-destructive">{errorText(save.error)}</p>}
        <Button type="submit" variant={kind === "end" ? "destructive" : "default"} disabled={save.isPending}>
          {save.isPending && <Loader2 className="animate-spin" />} {kind === "extend" ? `Add ${days || 0} days` : "End plan now"}
        </Button>
      </form>
    </Dialog>
  );
}

interface History {
  periods: { id: string; plan: string; status_label: string; starts_on: string | null; ends_on: string | null; price: string; note: string; by: string | null }[];
  invoices: { id: string; number: string; status: string; amount: string; discount: string; promo_code: string | null; created_at: string }[];
  events: { at: string; summary: string; by: string }[];
}

function HistoryDialog({ row, onClose }: { row: SubRow; onClose: () => void }) {
  const h = useQuery({ queryKey: ["admin", "sub-history", row.turf.id], queryFn: () => api<History>(`/admin/turfs/${row.turf.id}/subscription-history/`) });
  return (
    <Dialog open onClose={onClose} title={`${row.turf.name} — plan history`} wide>
      {h.isPending && <Skeleton className="h-40" />}
      {h.data && (
        <div className="flex flex-col gap-4 text-sm">
          <section>
            <h3 className="mb-2 font-semibold">Paid periods</h3>
            <Table>
              <tbody>
                {h.data.periods.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {p.plan} <span className="text-xs text-muted-foreground">({p.status_label})</span>
                      {p.note && <span className="block text-xs text-muted-foreground">{p.note}</span>}
                    </td>
                    <td className="whitespace-nowrap">
                      {p.starts_on ? fmtPlainDate(p.starts_on) : "—"} – {p.ends_on ? fmtPlainDate(p.ends_on) : "—"}
                    </td>
                    <td className="tabular text-right">{formatBDT(p.price)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </section>
          <section>
            <h3 className="mb-2 font-semibold">Invoices</h3>
            <ul className="divide-y rounded-md border">
              {h.data.invoices.map((i) => (
                <li key={i.id} className="flex justify-between gap-2 px-3 py-2">
                  <span>
                    {i.number} · {i.status}
                    {i.promo_code && <span className="text-muted-foreground"> · {i.promo_code}</span>}
                  </span>
                  <span className="tabular">{formatBDT(i.amount)}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 font-semibold">Changes</h3>
            <ul className="max-h-48 divide-y overflow-y-auto rounded-md border">
              {h.data.events.map((e, i) => (
                <li key={i} className="px-3 py-2">
                  {e.summary} <span className="text-xs text-muted-foreground">· {e.by} · {new Date(e.at).toLocaleString("en-GB")}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Dialog>
  );
}

// ------------------------------------------------------------------ health
interface Health {
  ok: boolean;
  problems: string[];
  database: boolean;
  cache: boolean;
  tick: { last_run: string | null; minutes_ago: number | null; errors: string[] };
  sms_24h: { failed: number; unknown: number; waiting: number; sent: number };
  sms_errors: { provider_code: string; provider_message: string; n: number }[];
  accounts_24h: { failed_logins: number; resets: number; locked_now: number };
  bookings: { awaiting_verification: number; expired_unverified_24h: number; requests_24h: number };
  subscriptions: { email_reminders_failed_7d: number; payments_awaiting_check: number };
  config: { sms_provider: string; tick_endpoint: boolean; email_backend: string; online_payments: boolean };
  events: { at: string; category: string; summary: string; by: string; turf: string }[];
}

function Metric({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <div className={cn("rounded-lg border p-3", warn && "border-amber-500/50 bg-amber-500/5")}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="tabular text-xl font-bold">{value}</p>
    </div>
  );
}

export function AdminHealthPage() {
  const health = useQuery({ queryKey: ["admin", "health"], queryFn: () => api<Health>("/admin/health/"), refetchInterval: 30_000 });
  const h = health.data;
  return (
    <>
      <PageHeader
        title="Platform health"
        description="Is everything running? Background tasks, SMS, sign-ins, bookings and billing at a glance."
        actions={
          <Button variant="outline" onClick={() => health.refetch()} disabled={health.isFetching}>
            {health.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh
          </Button>
        }
      />
      {health.isPending && <Skeleton className="h-64" />}
      {health.isError && <ErrorState error={health.error} onRetry={() => health.refetch()} />}
      {h && (
        <div className="flex flex-col gap-6">
          {h.ok ? (
            <p className="flex items-center gap-2 rounded-xl border border-green-500/40 bg-green-500/10 p-4 text-sm font-medium">
              <CheckCircle2 className="size-5 text-green-600" /> All systems normal.
            </p>
          ) : (
            <div className="rounded-xl border border-amber-500/50 bg-amber-500/10 p-4 text-sm">
              <p className="mb-2 flex items-center gap-2 font-semibold">
                <AlertTriangle className="size-5 text-amber-600" /> Needs attention
              </p>
              <ul className="list-disc space-y-1 pl-6">
                {h.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Core</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-3">
                <Metric label="Database" value={h.database ? "OK" : "Down"} warn={!h.database} />
                <Metric label="Cache" value={h.cache ? "OK" : "Down"} warn={!h.cache} />
                <Metric
                  label="Background tasks"
                  value={h.tick.minutes_ago === null ? "Never ran" : h.tick.minutes_ago === 0 ? "Just now" : `${h.tick.minutes_ago} min ago`}
                  warn={h.tick.minutes_ago === null || h.tick.minutes_ago > 30 || h.tick.errors.length > 0}
                />
                <Metric label="SMS provider" value={h.config.sms_provider} warn={h.config.sms_provider === "disabled"} />
                <Metric label="Email" value={h.config.email_backend || "—"} />
                <Metric label="Online plan payments" value={h.config.online_payments ? "On" : "Off"} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Last 24 hours</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="SMS sent" value={h.sms_24h.sent} />
                <Metric label="SMS failed / check" value={h.sms_24h.failed + h.sms_24h.unknown} warn={h.sms_24h.failed + h.sms_24h.unknown > 0} />
                <Metric label="SMS waiting" value={h.sms_24h.waiting} />
                <Metric label="Failed sign-ins" value={h.accounts_24h.failed_logins} warn={h.accounts_24h.failed_logins > 20} />
                <Metric label="Locked accounts now" value={h.accounts_24h.locked_now} warn={h.accounts_24h.locked_now > 0} />
                <Metric label="Password resets" value={h.accounts_24h.resets} />
                <Metric label="bKash requests" value={h.bookings.requests_24h} />
                <Metric label="Awaiting verification" value={h.bookings.awaiting_verification} />
                <Metric label="Expired unverified" value={h.bookings.expired_unverified_24h} warn={h.bookings.expired_unverified_24h > 0} />
                <Metric label="Plan payments to check" value={h.subscriptions.payments_awaiting_check} warn={h.subscriptions.payments_awaiting_check > 0} />
                <Metric label="Reminder emails failed (7 d)" value={h.subscriptions.email_reminders_failed_7d} warn={h.subscriptions.email_reminders_failed_7d > 0} />
              </CardContent>
            </Card>
          </div>
          {h.sms_errors.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Most common SMS errors (24 h)</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y text-sm">
                  {h.sms_errors.map((e) => (
                    <li key={`${e.provider_code}-${e.provider_message}`} className="flex justify-between gap-2 py-2">
                      <span>
                        <span className="font-mono">{e.provider_code}</span> {e.provider_message}
                      </span>
                      <span className="tabular">{e.n}×</span>
                    </li>
                  ))}
                </ul>
                <Button asChild variant="link" className="px-0">
                  <Link to="/admin/sms">Open the SMS log</Link>
                </Button>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Recent platform &amp; account events</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                {h.events.map((e, i) => (
                  <li key={i} className="flex flex-wrap justify-between gap-2 py-2">
                    <span>
                      {e.summary}
                      {e.turf && <span className="text-muted-foreground"> · {e.turf}</span>}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {e.by && `${e.by} · `}
                      {new Date(e.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
