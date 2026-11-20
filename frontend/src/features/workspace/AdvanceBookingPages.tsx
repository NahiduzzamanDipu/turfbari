import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  CalendarCheck2,
  CalendarPlus,
  CheckCircle2,
  Clock,
  Loader2,
  Plus,
  Repeat,
  Search,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { addDays, fmtDateTime, fmtDay, fmtRange, todayISO } from "@/lib/format";
import { type SmsOutcome, showSmsOutcome } from "@/lib/smsOutcome";
import type { Customer, Paginated } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText, useFields } from "./hooks";

// ------------------------------------------------------------------ types
type Recurrence = "daily" | "weekdays" | "weekly" | "custom" | "once";
type SeriesStatus = "active" | "pending_payment" | "cancelled" | "expired" | "completed";

interface PreviewRow {
  date: string;
  weekday: string;
  start: string;
  end: string;
  available: boolean;
  reason: string;
  reason_label: string;
  detail: string;
  price: string;
  slots: number;
}
interface PreviewSummary {
  dates: number;
  available: number;
  unavailable: string[];
  booking: number;
  minutes_each: number;
  total: string;
  advance_required: string;
  advance_rule: string;
  remaining: string;
}
interface Preview {
  rows: PreviewRow[];
  summary: PreviewSummary;
}
interface Occurrence {
  id: string;
  reference: string;
  number: number;
  start: string;
  end: string;
  status: string;
  status_label: string;
  total: string;
  paid: string;
  payment_status: "unpaid" | "partial" | "paid";
  upcoming: boolean;
  can_cancel: boolean;
  hold_expires_at: string | null;
}
interface Series {
  id: string;
  reference: string;
  customer: { id: string; name: string; phone: string };
  field: { id: string; name: string };
  start_time: string;
  end_time: string;
  overnight: boolean;
  recurrence: Recurrence;
  recurrence_label: string;
  weekdays: number[];
  start_date: string;
  end_date: string;
  occurrences_count: number;
  total: string;
  status: SeriesStatus;
  team_name: string;
  notes: string;
  created_by: string | null;
  created_at: string;
  occurrences?: Occurrence[];
  live_total?: string;
  paid_total?: string;
  due_total?: string;
  advance_required?: string;
  hold_expires_at?: string | null;
  sms?: SmsOutcome | null;
  result?: { cancelled?: number; paid_on_cancelled?: string; changed?: number; added?: boolean; rows?: PreviewRow[]; row?: PreviewRow; sms?: SmsOutcome | null };
}

const STATUS: Record<SeriesStatus, { label: string; tone: BadgeTone }> = {
  active: { label: "Active", tone: "green" },
  pending_payment: { label: "Awaiting payment", tone: "amber" },
  cancelled: { label: "Cancelled", tone: "red" },
  expired: { label: "Payment not received", tone: "neutral" },
  completed: { label: "Completed", tone: "blue" },
};
const OCC_TONE: Record<string, BadgeTone> = {
  confirmed: "green",
  pending: "amber",
  completed: "blue",
  cancelled: "red",
  expired: "neutral",
  rejected: "red",
  no_show: "neutral",
};
// Monday-first, matching the server (0 = Monday … 6 = Sunday). Bangladesh weeks start on Saturday.
const WEEKDAYS = [
  { v: 5, label: "Sat" },
  { v: 6, label: "Sun" },
  { v: 0, label: "Mon" },
  { v: 1, label: "Tue" },
  { v: 2, label: "Wed" },
  { v: 3, label: "Thu" },
  { v: 4, label: "Fri" },
];
const RECURRENCES: { v: Recurrence; label: string; hint: string }[] = [
  { v: "daily", label: "Every day", hint: "Same time every day" },
  { v: "weekdays", label: "Selected days", hint: "e.g. Sun, Tue, Thu" },
  { v: "weekly", label: "Once a week", hint: "One weekday" },
  { v: "custom", label: "Custom dates", hint: "Pick exact dates" },
  { v: "once", label: "One date", hint: "Single advance booking" },
];
const PERIODS: { label: string; days?: number; months?: number }[] = [
  { label: "7 days", days: 7 },
  { label: "15 days", days: 15 },
  { label: "30 days", days: 30 },
  { label: "2 months", months: 2 },
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
];
const SERIES_KEY = ["ws", "booking-series"] as const;

function endFor(start: string, p: { days?: number; months?: number }): string {
  if (p.days) return addDays(start, p.days - 1);
  const [y, m, d] = start.split("-").map(Number);
  const dt = new Date(Date.UTC(y!, m! - 1 + (p.months ?? 0), d!));
  dt.setUTCDate(dt.getUTCDate() - 1);
  return dt.toISOString().slice(0, 10);
}

function minutesBetween(start: string, end: string): number {
  const [sh, sm] = start.split(":").map(Number);
  const [eh, em] = end.split(":").map(Number);
  let m = eh! * 60 + em! - (sh! * 60 + sm!);
  if (m <= 0) m += 24 * 60;
  return m;
}
const hours = (min: number) => `${Math.floor(min / 60)}h${min % 60 ? ` ${min % 60}m` : ""}`;
const clock = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return `${((h! + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h! < 12 ? "AM" : "PM"}`;
};
const dayLabel = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" }).format(new Date(`${iso}T00:00:00Z`));

// ------------------------------------------------------------------ list
export function AdvanceBookingsPage() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = new URLSearchParams({ page: String(page), ...(status && { status }), ...(search && { q: search }) });
  const list = useQuery({
    queryKey: [...SERIES_KEY, "list", query.toString()],
    queryFn: () => api<Paginated<Series>>(`/workspace/booking-series/?${query}`),
    placeholderData: keepPreviousData,
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 20)) : 1;
  return (
    <>
      <Link to="/workspace/bookings" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Bookings
      </Link>
      <PageHeader
        title="Advance & recurring"
        description="Book the same time for a customer on many future dates. Each date becomes a normal booking on your calendar."
        actions={
          <Button asChild>
            <Link to="/workspace/advance-bookings/new">
              <CalendarPlus /> Create advance booking
            </Link>
          </Button>
        }
      />
      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <form
            className="flex flex-1 gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setSearch(q.trim());
            }}
          >
            <Input aria-label="Search" placeholder="Series ID, customer name or phone" value={q} onChange={(e) => setQ(e.target.value)} />
            <Button type="submit" variant="outline" size="icon" aria-label="Search">
              <Search />
            </Button>
          </form>
          <Select aria-label="Status" className="sm:w-56" value={status} onChange={(e) => (setPage(1), setStatus(e.target.value))}>
            <option value="">All series</option>
            <option value="active">Active</option>
            <option value="pending_payment">Awaiting payment</option>
            <option value="cancelled">Cancelled</option>
            <option value="expired">Payment not received</option>
          </Select>
        </CardHeader>
        <CardContent>
          {list.isPending && <Skeleton className="h-48" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.count === 0 && (
            <EmptyState icon={<Repeat />} title={search || status ? "No series match" : "No advance bookings yet"}>
              Create one to reserve a regular slot for a team — for example every day 5–7 PM for a month.
            </EmptyState>
          )}
          {list.data && list.data.count > 0 && (
            <Table className={cn(list.isFetching && "opacity-70")}>
              <thead>
                <tr>
                  <th>Series</th>
                  <th>Customer</th>
                  <th>Schedule</th>
                  <th className="text-right">Dates</th>
                  <th className="text-right">Total</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/workspace/advance-bookings/${s.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">
                        {s.reference}
                      </Link>
                    </td>
                    <td>
                      {s.team_name || s.customer.name}
                      <span className="block text-xs text-muted-foreground">{s.customer.phone}</span>
                    </td>
                    <td className="text-xs">
                      {s.recurrence_label} · {clock(s.start_time)}–{clock(s.end_time)}
                      <span className="block text-muted-foreground">
                        {dayLabel(s.start_date)} – {dayLabel(s.end_date)} · {s.field.name}
                      </span>
                    </td>
                    <td className="tabular text-right">{s.occurrences_count}</td>
                    <td className="tabular text-right">{formatBDT(s.total)}</td>
                    <td>
                      <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              Page {page} of {pages}
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

// ------------------------------------------------------------------ create wizard
const STEPS = ["Customer", "Schedule", "Availability", "Pricing", "Confirm"];

interface Draft {
  customer_name: string;
  customer_phone: string;
  team_name: string;
  notes: string;
  field: string;
  start_time: string;
  end_time: string;
  recurrence: Recurrence;
  weekdays: number[];
  custom_dates: string[];
  start_date: string;
  end_date: string;
}

export function CreateAdvanceBookingPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const fields = useFields();
  const [step, setStep] = useState(0);
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const tomorrow = addDays(todayISO(), 1);
  const [d, setD] = useState<Draft>({
    customer_name: "",
    customer_phone: "",
    team_name: "",
    notes: "",
    field: "",
    start_time: "17:00",
    end_time: "19:00",
    recurrence: "daily",
    weekdays: [],
    custom_dates: [],
    start_date: tomorrow,
    end_date: endFor(tomorrow, { days: 30 }),
  });
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"confirm" | "pending">("confirm");
  const [advance, setAdvance] = useState({ amount: "", method: "cash", reference: "" });
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const field = d.field || fields.data?.find((f) => f.is_active)?.id || "";
  const body = { ...d, field, exclude_dates: [...excluded] };

  const check = useMutation({
    mutationFn: (exclude: string[]) =>
      api<Preview>("/workspace/booking-series/preview/", { method: "POST", json: { ...d, field, exclude_dates: exclude } }),
    onError: (e) => toast.error(errorText(e)),
  });
  const preview = check.data;
  const unresolved = preview?.rows.filter((r) => !r.available && !excluded.has(r.date)) ?? [];

  const submit = useMutation({
    mutationFn: () =>
      api<Series>("/workspace/booking-series/", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        json: { ...body, mode, ...(mode === "confirm" && Number(advance.amount) > 0 ? { advance_amount: advance.amount, advance_method: advance.method, advance_reference: advance.reference } : {}) },
      }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["ws"] });
      toast.success(`Series ${s.reference} created — ${s.occurrences_count} booking${s.occurrences_count === 1 ? "" : "s"}`);
      showSmsOutcome(s.sms);
      navigate(`/workspace/advance-bookings/${s.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fields?.code?.[0] === "dates_unavailable") {
        toast.error("Some dates were just taken. Review availability again.");
        setStep(2);
        check.mutate([...excluded]);
      } else toast.error(errorText(e));
    },
  });

  const go = (to: number) => {
    if (to === 2) check.mutate([...excluded]);
    if (to === 3) check.mutate([...excluded]);
    setStep(to);
  };
  const minutes = minutesBetween(d.start_time, d.end_time);
  const step1Ok = d.customer_name.trim().length > 1 && /^(\+?88)?01[3-9]\d{8}$/.test(d.customer_phone.replace(/[\s-]/g, ""));
  const step2Ok =
    Boolean(field) &&
    d.start_time !== d.end_time &&
    (d.recurrence !== "weekdays" || d.weekdays.length > 0) &&
    (d.recurrence !== "custom" || d.custom_dates.length > 0) &&
    (d.recurrence === "once" || d.recurrence === "custom" || d.end_date >= d.start_date);

  return (
    <>
      <Link to="/workspace/advance-bookings" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Advance &amp; recurring
      </Link>
      <PageHeader title="Create advance booking" description="One request, many dates. Every date is checked and priced before anything is booked." />
      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li key={label}>
            <span
              aria-current={i === step ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm",
                i === step ? "border-primary bg-primary text-primary-foreground" : i < step ? "border-primary/40 text-primary" : "text-muted-foreground",
              )}
            >
              <span className="tabular font-semibold">{i + 1}</span> {label}
            </span>
          </li>
        ))}
      </ol>

      {step === 0 && <CustomerStep draft={d} onChange={set} />}
      {step === 1 && <ScheduleStep draft={d} onChange={set} field={field} minutes={minutes} />}
      {step === 2 && (
        <AvailabilityStep
          pending={check.isPending}
          preview={preview}
          excluded={excluded}
          toggle={(date) =>
            setExcluded((s) => {
              const next = new Set(s);
              next.has(date) ? next.delete(date) : next.add(date);
              return next;
            })
          }
          excludeAll={() => setExcluded((s) => new Set([...s, ...(preview?.rows.filter((r) => !r.available).map((r) => r.date) ?? [])]))}
        />
      )}
      {step === 3 && <PricingStep pending={check.isPending} preview={preview} excluded={excluded} />}
      {step === 4 && preview && (
        <ConfirmStep draft={d} preview={preview} excluded={excluded} mode={mode} setMode={setMode} advance={advance} setAdvance={setAdvance} fieldName={fields.data?.find((f) => f.id === field)?.name ?? ""} />
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" disabled={step === 0 || submit.isPending} onClick={() => setStep((s) => s - 1)}>
          <ArrowLeft /> Back
        </Button>
        {step < 4 ? (
          <Button
            disabled={(step === 0 && !step1Ok) || (step === 1 && !step2Ok) || (step >= 2 && (check.isPending || !preview || unresolved.length > 0 || preview.summary.booking === 0))}
            onClick={() => go(step + 1)}
          >
            {step === 1 ? "Check availability" : "Continue"} <ArrowRight />
          </Button>
        ) : (
          <Button
            disabled={submit.isPending}
            onClick={() => {
              const n = preview?.summary.booking ?? 0;
              if (window.confirm(`Create ${n} booking${n === 1 ? "" : "s"} for ${d.customer_name}${mode === "pending" ? " (awaiting payment)" : ""}?`)) submit.mutate();
            }}
          >
            {submit.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
            {mode === "pending" ? "Reserve & await payment" : "Confirm bookings"}
          </Button>
        )}
      </div>
      {step >= 2 && unresolved.length > 0 && (
        <p className="mt-2 text-right text-sm text-destructive">
          {unresolved.length} date{unresolved.length === 1 ? " is" : "s are"} unavailable — exclude {unresolved.length === 1 ? "it" : "them"} or go back and change the schedule.
        </p>
      )}
    </>
  );
}

function CustomerStep({ draft, onChange }: { draft: Draft; onChange: (p: Partial<Draft>) => void }) {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const results = useQuery({
    queryKey: ["ws", "customers", "pick", q],
    queryFn: () => api<Paginated<Customer>>(`/workspace/customers/?sort=recent&q=${encodeURIComponent(q)}`),
    placeholderData: keepPreviousData,
  });
  const chosen = draft.customer_phone && !creating;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="size-5 text-primary" /> Who is the booking for?
        </CardTitle>
        <CardDescription>Pick a customer from your booking history, or add a new one. The same mobile number is always the same customer.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {chosen && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/40 bg-primary/5 p-3 text-sm">
            <span>
              <strong>{draft.customer_name}</strong> · {draft.customer_phone}
            </span>
            <Button size="sm" variant="ghost" onClick={() => onChange({ customer_name: "", customer_phone: "" })}>
              Change
            </Button>
          </div>
        )}
        {!chosen && !creating && (
          <>
            <Input aria-label="Search customers" placeholder="Search by name or mobile number" value={q} onChange={(e) => setQ(e.target.value)} />
            <ul className="max-h-72 divide-y overflow-y-auto rounded-md border text-sm">
              {results.data?.results.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-secondary"
                    onClick={() => onChange({ customer_name: c.name, customer_phone: c.phone })}
                  >
                    <span>
                      <span className="font-medium">{c.name}</span>
                      <span className="block text-xs text-muted-foreground">{c.phone}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">{c.bookings_count} bookings</span>
                  </button>
                </li>
              ))}
              {results.data?.results.length === 0 && <li className="px-3 py-4 text-center text-muted-foreground">No customer matches.</li>}
            </ul>
            <Button variant="outline" className="self-start" onClick={() => setCreating(true)}>
              <UserPlus /> New customer
            </Button>
          </>
        )}
        {creating && (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Customer name">{(id) => <Input id={id} required value={draft.customer_name} onChange={(e) => onChange({ customer_name: e.target.value })} />}</FormField>
            <FormField label="Mobile number" hint="Bangladesh mobile, e.g. 01712345678">
              {(id) => <Input id={id} type="tel" required placeholder="01XXXXXXXXX" value={draft.customer_phone} onChange={(e) => onChange({ customer_phone: e.target.value })} />}
            </FormField>
            <Button variant="ghost" className="self-start" onClick={() => setCreating(false)}>
              Search existing instead
            </Button>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Team name (optional)">{(id) => <Input id={id} value={draft.team_name} onChange={(e) => onChange({ team_name: e.target.value })} />}</FormField>
          <FormField label="Notes (optional)">{(id) => <Textarea id={id} rows={1} value={draft.notes} onChange={(e) => onChange({ notes: e.target.value })} />}</FormField>
        </div>
      </CardContent>
    </Card>
  );
}

function ScheduleStep({ draft, onChange, field, minutes }: { draft: Draft; onChange: (p: Partial<Draft>) => void; field: string; minutes: number }) {
  const fields = useFields();
  const [newDate, setNewDate] = useState("");
  const overnight = draft.end_time <= draft.start_time;
  const toggleDay = (v: number) =>
    onChange({ weekdays: draft.recurrence === "weekly" ? [v] : draft.weekdays.includes(v) ? draft.weekdays.filter((x) => x !== v) : [...draft.weekdays, v] });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="size-5 text-primary" /> Field &amp; time
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FormField label="Field">
            {(id) => (
              <Select id={id} value={field} onChange={(e) => onChange({ field: e.target.value })}>
                {fields.data
                  ?.filter((f) => f.is_active)
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
              </Select>
            )}
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Start time">{(id) => <Input id={id} type="time" step={900} value={draft.start_time} onChange={(e) => onChange({ start_time: e.target.value })} />}</FormField>
            <FormField label="End time">{(id) => <Input id={id} type="time" step={900} value={draft.end_time} onChange={(e) => onChange({ end_time: e.target.value })} />}</FormField>
          </div>
          <p className="rounded-md bg-secondary px-3 py-2 text-sm">
            {clock(draft.start_time)} – {clock(draft.end_time)} · <strong>{hours(minutes)}</strong> per booking
            {overnight && <span className="text-muted-foreground"> (ends the next day)</span>}
          </p>
          <p className="text-xs text-muted-foreground">Times follow your opening hours and slot schedule; they're checked for every date in the next step.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Repeat className="size-5 text-primary" /> Repeat
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Repeat">
            {RECURRENCES.map((r) => (
              <button
                key={r.v}
                type="button"
                role="radio"
                aria-checked={draft.recurrence === r.v}
                onClick={() => onChange({ recurrence: r.v, weekdays: r.v === "weekly" ? draft.weekdays.slice(0, 1) : draft.weekdays })}
                className={cn("rounded-lg border p-2 text-left text-sm transition", draft.recurrence === r.v ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-secondary")}
              >
                <span className="font-medium">{r.label}</span>
                <span className="block text-xs text-muted-foreground">{r.hint}</span>
              </button>
            ))}
          </div>
          {(draft.recurrence === "weekdays" || draft.recurrence === "weekly") && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Days of the week">
              {WEEKDAYS.map((w) => (
                <button
                  key={w.v}
                  type="button"
                  aria-pressed={draft.weekdays.includes(w.v)}
                  onClick={() => toggleDay(w.v)}
                  className={cn("w-12 rounded-md border py-1.5 text-sm font-medium", draft.weekdays.includes(w.v) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
                >
                  {w.label}
                </button>
              ))}
            </div>
          )}
          {draft.recurrence === "custom" ? (
            <div className="flex flex-col gap-2">
              <div className="flex gap-2">
                <Input type="date" aria-label="Add a date" min={todayISO()} value={newDate} onChange={(e) => setNewDate(e.target.value)} />
                <Button
                  type="button"
                  variant="outline"
                  disabled={!newDate || draft.custom_dates.includes(newDate)}
                  onClick={() => {
                    onChange({ custom_dates: [...draft.custom_dates, newDate].sort() });
                    setNewDate("");
                  }}
                >
                  <Plus /> Add
                </Button>
              </div>
              <ul className="flex flex-wrap gap-1.5">
                {draft.custom_dates.map((x) => (
                  <li key={x}>
                    <button type="button" onClick={() => onChange({ custom_dates: draft.custom_dates.filter((y) => y !== x) })} className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs hover:bg-destructive/10" aria-label={`Remove ${x}`}>
                      {dayLabel(x)} <XCircle className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <FormField label={draft.recurrence === "once" ? "Date" : "Start date"}>
                  {(id) => <Input id={id} type="date" min={todayISO()} value={draft.start_date} onChange={(e) => onChange({ start_date: e.target.value })} />}
                </FormField>
                {draft.recurrence !== "once" && (
                  <FormField label="End date">{(id) => <Input id={id} type="date" min={draft.start_date} value={draft.end_date} onChange={(e) => onChange({ end_date: e.target.value })} />}</FormField>
                )}
              </div>
              {draft.recurrence !== "once" && (
                <div className="flex flex-wrap gap-1.5" aria-label="Quick period">
                  {PERIODS.map((p) => {
                    const end = endFor(draft.start_date, p);
                    return (
                      <button
                        key={p.label}
                        type="button"
                        onClick={() => onChange({ end_date: end })}
                        className={cn("rounded-full border px-3 py-1 text-xs font-medium", draft.end_date === end ? "border-primary bg-primary/10 text-primary" : "hover:bg-secondary")}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AvailabilityStep({
  pending,
  preview,
  excluded,
  toggle,
  excludeAll,
}: {
  pending: boolean;
  preview?: Preview;
  excluded: Set<string>;
  toggle: (date: string) => void;
  excludeAll: () => void;
}) {
  if (pending && !preview) return <Skeleton className="h-64" />;
  if (!preview) return <EmptyState title="Checking availability…" />;
  const bad = preview.rows.filter((r) => !r.available);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="flex items-center gap-2">
            <CalendarCheck2 className="size-5 text-primary" /> {preview.summary.available} of {preview.summary.dates} dates available
          </CardTitle>
          <CardDescription>Checked against bookings, live holds, maintenance, opening hours, your slot schedule and the customer's daily limit. It's checked again when you submit.</CardDescription>
        </div>
        {bad.length > 0 && (
          <Button variant="outline" onClick={excludeAll}>
            Exclude {bad.length} unavailable date{bad.length === 1 ? "" : "s"}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <div className={cn("max-h-[28rem] overflow-y-auto", pending && "opacity-60")}>
          <Table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Availability</th>
                <th className="text-right">Price</th>
                <th className="text-right">Book?</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((r) => {
                const off = excluded.has(r.date);
                return (
                  <tr key={r.date} className={cn(off && "text-muted-foreground line-through", !r.available && !off && "bg-destructive/5")}>
                    <td className="whitespace-nowrap">{dayLabel(r.date)}</td>
                    <td className="whitespace-nowrap">{fmtRange(r.start, r.end)}</td>
                    <td>
                      {r.available ? (
                        <Badge tone="green">Available</Badge>
                      ) : (
                        <span className="text-sm">
                          <Badge tone="red">Unavailable</Badge> <span className="text-xs">{r.reason_label}{r.detail && ` (${r.detail})`}</span>
                        </span>
                      )}
                    </td>
                    <td className="tabular text-right">{formatBDT(r.price)}</td>
                    <td className="text-right">
                      <input
                        type="checkbox"
                        aria-label={`Book ${r.date}`}
                        className="size-4 accent-[var(--primary)]"
                        checked={!off}
                        onChange={() => toggle(r.date)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function PricingStep({ pending, preview, excluded }: { pending: boolean; preview?: Preview; excluded: Set<string> }) {
  if (!preview) return <Skeleton className="h-64" />;
  const s = preview.summary;
  const chosen = preview.rows.filter((r) => r.available && !excluded.has(r.date));
  const byPrice = new Map<string, number>();
  for (const r of chosen) byPrice.set(r.price, (byPrice.get(r.price) ?? 0) + 1);
  return (
    <div className={cn("flex flex-col gap-6", pending && "opacity-60")}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Bookings" value={s.booking} hint={`${hours(s.minutes_each)} each`} />
        <StatCard label="Total" value={formatBDT(s.total)} />
        <StatCard label="Advance required" value={formatBDT(s.advance_required)} hint={s.advance_rule} />
        <StatCard label="Remaining" value={formatBDT(s.remaining)} hint="Collected at the turf" />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>How the total is made</CardTitle>
          <CardDescription>Each date is priced by your own pricing (time categories, slot prices, special dates). Prices are saved with each booking, so later price changes don't affect it.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-1 text-sm">
          {[...byPrice.entries()].map(([price, n]) => (
            <p key={price} className="flex justify-between">
              <span>
                {n} date{n === 1 ? "" : "s"} × {formatBDT(price)}
              </span>
              <span className="tabular">{formatBDT(n * Number(price))}</span>
            </p>
          ))}
          <p className="mt-2 flex justify-between border-t pt-2 font-semibold">
            <span>Total</span>
            <span className="tabular">{formatBDT(s.total)}</span>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function ConfirmStep({
  draft,
  preview,
  excluded,
  mode,
  setMode,
  advance,
  setAdvance,
  fieldName,
}: {
  draft: Draft;
  preview: Preview;
  excluded: Set<string>;
  mode: "confirm" | "pending";
  setMode: (m: "confirm" | "pending") => void;
  advance: { amount: string; method: string; reference: string };
  setAdvance: (a: { amount: string; method: string; reference: string }) => void;
  fieldName: string;
}) {
  const s = preview.summary;
  const chosen = preview.rows.filter((r) => r.available && !excluded.has(r.date));
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Review</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Customer</dt>
            <dd>
              {draft.customer_name} · {draft.customer_phone}
              {draft.team_name && ` · ${draft.team_name}`}
            </dd>
            <dt className="text-muted-foreground">Field</dt>
            <dd>{fieldName}</dd>
            <dt className="text-muted-foreground">Time</dt>
            <dd>
              {clock(draft.start_time)} – {clock(draft.end_time)}
            </dd>
            <dt className="text-muted-foreground">Dates</dt>
            <dd>
              {chosen.length} · {chosen[0] && dayLabel(chosen[0].date)} – {chosen.at(-1) && dayLabel(chosen.at(-1)!.date)}
              {excluded.size > 0 && <span className="text-muted-foreground"> ({excluded.size} excluded)</span>}
            </dd>
            <dt className="text-muted-foreground">Total</dt>
            <dd className="font-semibold">{formatBDT(s.total)}</dd>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Payment</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <label className={cn("flex cursor-pointer gap-3 rounded-lg border p-3", mode === "confirm" && "border-primary bg-primary/5")}>
            <input type="radio" name="mode" className="mt-1 accent-[var(--primary)]" checked={mode === "confirm"} onChange={() => setMode("confirm")} />
            <span>
              <span className="font-medium">Confirm now</span>
              <span className="block text-muted-foreground">Every date is booked straight away and the customer gets one confirmation SMS. Record any advance you already received.</span>
            </span>
          </label>
          {mode === "confirm" && (
            <div className="grid gap-2 sm:grid-cols-3">
              <FormField label="Advance received (৳)">{(id) => <Input id={id} type="number" min={0} max={Number(s.total)} value={advance.amount} onChange={(e) => setAdvance({ ...advance, amount: e.target.value })} />}</FormField>
              <FormField label="Method">
                {(id) => (
                  <Select id={id} value={advance.method} onChange={(e) => setAdvance({ ...advance, method: e.target.value })}>
                    <option value="cash">Cash</option>
                    <option value="bkash">bKash</option>
                    <option value="nagad">Nagad</option>
                    <option value="bank">Bank transfer</option>
                  </Select>
                )}
              </FormField>
              <FormField label="Reference">{(id) => <Input id={id} value={advance.reference} onChange={(e) => setAdvance({ ...advance, reference: e.target.value })} />}</FormField>
            </div>
          )}
          <label className={cn("flex cursor-pointer gap-3 rounded-lg border p-3", mode === "pending" && "border-primary bg-primary/5")}>
            <input type="radio" name="mode" className="mt-1 accent-[var(--primary)]" checked={mode === "pending"} onChange={() => setMode("pending")} />
            <span>
              <span className="font-medium">Reserve, await payment</span>
              <span className="block text-muted-foreground">
                Dates are held (not confirmed) until you record the advance of at least {formatBDT(s.advance_required)}. If it isn't recorded in time, the dates are released automatically. No confirmation SMS until then.
              </span>
            </span>
          </label>
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ one series
export function SeriesDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const key = [...SERIES_KEY, "detail", id];
  const series = useQuery({ queryKey: key, queryFn: () => api<Series>(`/workspace/booking-series/${id}/`) });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<null | "pay" | "add" | "move">(null);
  const done = (s: Series, message: string) => {
    qc.setQueryData(key, s);
    qc.invalidateQueries({ queryKey: ["ws"] });
    setSelected(new Set());
    setDialog(null);
    toast.success(message);
    const sms = s.sms ?? s.result?.sms;
    if (sms && sms.status !== "sent" && sms.status !== "queued") showSmsOutcome(sms);
  };
  const cancel = useMutation({
    mutationFn: (body: { booking_ids?: string[]; all_future?: boolean }) => api<Series>(`/workspace/booking-series/${id}/cancel/`, { method: "POST", json: body }),
    onSuccess: (s) =>
      done(
        s,
        `${s.result?.cancelled} date(s) cancelled` + (Number(s.result?.paid_on_cancelled) > 0 ? ` — ${formatBDT(s.result!.paid_on_cancelled!)} was paid on them; refund it from each booking if your policy says so` : ""),
      ),
    onError: (e) => toast.error(errorText(e)),
  });

  if (series.isPending) return <Skeleton className="h-96" />;
  if (series.isError) return <ErrorState error={series.error} onRetry={() => series.refetch()} />;
  const s = series.data;
  const occ = s.occurrences ?? [];
  const cancellable = occ.filter((o) => o.can_cancel);
  const live = s.status === "active" || s.status === "pending_payment";

  return (
    <>
      <Link to="/workspace/advance-bookings" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Advance &amp; recurring
      </Link>
      <PageHeader
        title={s.reference}
        description={`${s.team_name || s.customer.name} · ${s.customer.phone} · ${s.field.name} · ${s.recurrence_label}, ${clock(s.start_time)}–${clock(s.end_time)}${s.created_by ? ` · created by ${s.created_by}` : ""}`}
        actions={<Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>}
      />
      {s.status === "pending_payment" && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
          <p>
            Dates are held until <strong>{s.hold_expires_at ? fmtDateTime(s.hold_expires_at) : "—"}</strong>. Record an
            advance of at least <strong>{formatBDT(s.advance_required ?? "0")}</strong> to confirm them.
          </p>
          <Button onClick={() => setDialog("pay")}>Record payment &amp; confirm</Button>
        </div>
      )}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Active dates" value={occ.filter((o) => o.status === "confirmed" || o.status === "pending").length} hint={`of ${occ.length} created`} />
        <StatCard label="Total (active)" value={formatBDT(s.live_total ?? "0")} />
        <StatCard label="Paid" value={formatBDT(s.paid_total ?? "0")} />
        <StatCard label="Due" value={formatBDT(s.due_total ?? "0")} />
      </div>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Dates</CardTitle>
          {live && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setDialog("add")}>
                <Plus /> Add a date
              </Button>
              <Button size="sm" variant="outline" disabled={cancellable.length === 0} onClick={() => setDialog("move")}>
                <Clock /> Change time
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={selected.size === 0 || cancel.isPending}
                onClick={() => window.confirm(`Cancel ${selected.size} selected date(s)? The customer gets one SMS if any were confirmed.`) && cancel.mutate({ booking_ids: [...selected] })}
              >
                Cancel selected ({selected.size})
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={cancellable.length === 0 || cancel.isPending}
                onClick={() => window.confirm(`Cancel all ${cancellable.length} upcoming date(s)? Past dates are kept as they are.`) && cancel.mutate({ all_future: true })}
              >
                Cancel all upcoming
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          <Table>
            <thead>
              <tr>
                <th className="w-8">
                  <span className="sr-only">Select</span>
                </th>
                <th>#</th>
                <th>Date</th>
                <th>Status</th>
                <th>Payment</th>
                <th className="text-right">Price</th>
              </tr>
            </thead>
            <tbody>
              {occ.map((o) => (
                <tr key={o.id} className={cn(!o.upcoming && "text-muted-foreground")}>
                  <td>
                    {o.can_cancel && (
                      <input
                        type="checkbox"
                        aria-label={`Select ${o.reference}`}
                        className="size-4 accent-[var(--primary)]"
                        checked={selected.has(o.id)}
                        onChange={() =>
                          setSelected((x) => {
                            const next = new Set(x);
                            next.has(o.id) ? next.delete(o.id) : next.add(o.id);
                            return next;
                          })
                        }
                      />
                    )}
                  </td>
                  <td className="tabular">{o.number}</td>
                  <td className="whitespace-nowrap">
                    <Link to={`/workspace/bookings?view=list&open=${o.id}`} className="hover:text-primary hover:underline">
                      {fmtDay(o.start)}
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      {fmtRange(o.start, o.end)} · {o.reference}
                    </span>
                  </td>
                  <td>
                    <Badge tone={OCC_TONE[o.status] ?? "neutral"}>{o.status_label}</Badge>
                  </td>
                  <td className="text-xs capitalize">
                    {o.payment_status}
                    {Number(o.paid) > 0 && <span className="block text-muted-foreground">{formatBDT(o.paid)} paid</span>}
                  </td>
                  <td className="tabular text-right">{formatBDT(o.total)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
      {dialog === "pay" && <PayDialog series={s} onClose={() => setDialog(null)} onDone={done} />}
      {dialog === "add" && <AddDateDialog series={s} onClose={() => setDialog(null)} onDone={done} />}
      {dialog === "move" && <MoveDialog series={s} onClose={() => setDialog(null)} onDone={done} />}
    </>
  );
}

function PayDialog({ series, onClose, onDone }: { series: Series; onClose: () => void; onDone: (s: Series, m: string) => void }) {
  const [form, setForm] = useState({ amount: series.advance_required ?? "", method: "bkash", reference: "" });
  const pay = useMutation({
    mutationFn: () => api<Series>(`/workspace/booking-series/${series.id}/confirm/`, { method: "POST", json: form }),
    onSuccess: (s) => onDone(s, `${s.reference} confirmed`),
  });
  const fields = pay.error instanceof ApiError ? pay.error.fields : null;
  return (
    <Dialog open onClose={onClose} title="Record payment & confirm" description={`At least ${formatBDT(series.advance_required ?? "0")} (same advance rule as single bookings). Check it in your bKash/cash records first.`}>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          pay.mutate();
        }}
      >
        <FormField label="Amount received (৳)" error={fields?.amount}>{(id) => <Input id={id} type="number" min={0} required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />}</FormField>
        <FormField label="Method">
          {(id) => (
            <Select id={id} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
              <option value="bkash">bKash</option>
              <option value="cash">Cash</option>
              <option value="nagad">Nagad</option>
              <option value="bank">Bank transfer</option>
            </Select>
          )}
        </FormField>
        <FormField label={form.method === "bkash" ? "bKash Transaction ID" : "Reference (optional)"} error={fields?.reference}>
          {(id) => <Input id={id} required={form.method === "bkash"} className="font-mono uppercase" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value.toUpperCase() })} />}
        </FormField>
        {pay.error && !fields?.amount && !fields?.reference && <p className="text-sm text-destructive">{errorText(pay.error)}</p>}
        <Button type="submit" disabled={pay.isPending}>
          {pay.isPending && <Loader2 className="animate-spin" />} Confirm series
        </Button>
      </form>
    </Dialog>
  );
}

function AddDateDialog({ series, onClose, onDone }: { series: Series; onClose: () => void; onDone: (s: Series, m: string) => void }) {
  const [date, setDate] = useState("");
  const check = useMutation({ mutationFn: () => api<Series>(`/workspace/booking-series/${series.id}/add-date/`, { method: "POST", json: { date, dry_run: true } }) });
  const add = useMutation({
    mutationFn: () => api<Series>(`/workspace/booking-series/${series.id}/add-date/`, { method: "POST", json: { date } }),
    onSuccess: (s) => (s.result?.added ? onDone(s, `${dayLabel(date)} added`) : toast.error(s.result?.row?.reason_label ?? "Not available")),
    onError: (e) => toast.error(errorText(e)),
  });
  const row = check.data?.result?.row;
  return (
    <Dialog open onClose={onClose} title="Add a date" description={`${clock(series.start_time)}–${clock(series.end_time)} on ${series.field.name}. Checked and priced like the others.`}>
      <div className="flex flex-col gap-3 text-sm">
        <div className="flex gap-2">
          <Input type="date" aria-label="Date" min={todayISO()} value={date} onChange={(e) => (setDate(e.target.value), check.reset())} />
          <Button variant="outline" disabled={!date || check.isPending} onClick={() => check.mutate()}>
            Check
          </Button>
        </div>
        {check.error && <p className="text-destructive">{errorText(check.error)}</p>}
        {row && (
          <p className={cn("rounded-md px-3 py-2", row.available ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-100" : "bg-destructive/10 text-destructive")}>
            {row.available ? `Available — ${formatBDT(row.price)}` : `Unavailable: ${row.reason_label}`}
          </p>
        )}
        <Button disabled={!row?.available || add.isPending} onClick={() => add.mutate()}>
          {add.isPending && <Loader2 className="animate-spin" />} Add date
        </Button>
      </div>
    </Dialog>
  );
}

function MoveDialog({ series, onClose, onDone }: { series: Series; onClose: () => void; onDone: (s: Series, m: string) => void }) {
  const [form, setForm] = useState({ start_time: series.start_time, end_time: series.end_time, from_date: "" });
  const [keep, setKeep] = useState<Set<string>>(new Set());
  const payload = useMemo(() => ({ ...form, from_date: form.from_date || null, keep_dates: [...keep] }), [form, keep]);
  const dry = useMutation({ mutationFn: () => api<Series>(`/workspace/booking-series/${series.id}/reschedule/`, { method: "POST", json: { ...payload, dry_run: true } }) });
  const apply = useMutation({
    mutationFn: () => api<Series>(`/workspace/booking-series/${series.id}/reschedule/`, { method: "POST", json: { ...payload, dry_run: false } }),
    onSuccess: (s) => onDone(s, `${s.result?.changed} upcoming date(s) moved`),
    onError: (e) => toast.error(errorText(e)),
  });
  const rows = dry.data?.result?.rows ?? [];
  const blocked = rows.filter((r) => !r.available && !keep.has(r.date));
  return (
    <Dialog open onClose={onClose} wide title="Change time of upcoming dates" description="Past and finished dates never change. Check first — nothing moves until you apply.">
      <div className="flex flex-col gap-3 text-sm">
        <div className="grid gap-2 sm:grid-cols-3">
          <FormField label="New start">{(id) => <Input id={id} type="time" step={900} value={form.start_time} onChange={(e) => (setForm({ ...form, start_time: e.target.value }), dry.reset())} />}</FormField>
          <FormField label="New end">{(id) => <Input id={id} type="time" step={900} value={form.end_time} onChange={(e) => (setForm({ ...form, end_time: e.target.value }), dry.reset())} />}</FormField>
          <FormField label="From date (optional)">{(id) => <Input id={id} type="date" min={todayISO()} value={form.from_date} onChange={(e) => (setForm({ ...form, from_date: e.target.value }), dry.reset())} />}</FormField>
        </div>
        <Button variant="outline" className="self-start" disabled={dry.isPending} onClick={() => dry.mutate()}>
          {dry.isPending && <Loader2 className="animate-spin" />} Check new time
        </Button>
        {dry.error && <p className="text-destructive">{errorText(dry.error)}</p>}
        {rows.length > 0 && (
          <div className="max-h-72 overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>New time</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.date}>
                    <td>{dayLabel(r.date)}</td>
                    <td>{fmtRange(r.start, r.end)}</td>
                    <td>
                      {r.available ? (
                        <Badge tone="green">Can move · {formatBDT(r.price)}</Badge>
                      ) : (
                        <label className="flex items-center gap-2 text-xs">
                          <input type="checkbox" className="accent-[var(--primary)]" checked={keep.has(r.date)} onChange={() => setKeep((k) => { const n = new Set(k); n.has(r.date) ? n.delete(r.date) : n.add(r.date); return n; })} />
                          {r.reason_label} — keep current time
                        </label>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}
        <Button
          disabled={rows.length === 0 || blocked.length > 0 || apply.isPending}
          onClick={() => window.confirm("Move these upcoming dates to the new time? The customer gets one SMS about the change.") && apply.mutate()}
        >
          {apply.isPending && <Loader2 className="animate-spin" />} Apply change
        </Button>
        {blocked.length > 0 && <p className="text-xs text-destructive">Tick “keep current time” for the {blocked.length} date(s) that can't move, or pick another time.</p>}
      </div>
    </Dialog>
  );
}
