import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarX2, ChevronLeft, ChevronRight, Loader2, Pencil, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Badge,
  Dialog,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  STATUS_TONE,
  Select,
  Table,
  Textarea,
} from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  PAYMENT_METHODS,
  addDays,
  dhakaDay,
  dhakaISO,
  fmtDateTime,
  fmtDay,
  fmtRange,
  todayISO,
} from "@/lib/format";
import type { Booking, BookingStatus, Paginated } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText, useFields } from "./hooks";

const STATUS_ACTIONS: Record<BookingStatus, { to: BookingStatus; label: string; variant?: "destructive" | "outline" }[]> = {
  pending: [
    { to: "confirmed", label: "Confirm" },
    { to: "rejected", label: "Reject", variant: "destructive" },
  ],
  confirmed: [
    { to: "completed", label: "Mark played" },
    { to: "no_show", label: "No-show", variant: "outline" },
    { to: "cancelled", label: "Cancel", variant: "destructive" },
  ],
  no_show: [{ to: "completed", label: "Mark played" }],
  completed: [],
  cancelled: [],
  rejected: [],
};

export function BookingsPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? (params.get("status") ? "list" : "day");
  const day = params.get("date") ?? todayISO();
  const [formOpen, setFormOpen] = useState(params.get("new") === "1");
  const [editing, setEditing] = useState<Booking | null>(null);
  const openId = params.get("open");

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page" && key !== "open") next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (params.get("new") === "1") setParam("new", null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <PageHeader
        title="Bookings"
        actions={
          <>
            <div className="inline-flex rounded-md border p-0.5">
              {(["day", "list"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setParam("view", v)}
                  className={cn("rounded px-3 py-1.5 text-sm font-medium capitalize", view === v && "bg-secondary")}
                >
                  {v === "day" ? "Day board" : "All bookings"}
                </button>
              ))}
            </div>
            <Button
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus /> New booking
            </Button>
          </>
        }
      />
      {view === "day" ? (
        <DayBoard day={day} onDay={(d) => setParam("date", d)} onOpen={(id) => setParam("open", id)} />
      ) : (
        <BookingList params={params} setParam={setParam} onOpen={(id) => setParam("open", id)} />
      )}
      <BookingFormDialog
        open={formOpen}
        booking={editing}
        defaultDay={day}
        onClose={() => setFormOpen(false)}
        onSaved={(b) => {
          setFormOpen(false);
          setParam("open", b.id);
        }}
      />
      {openId && (
        <BookingDetailDialog
          id={openId}
          onClose={() => setParam("open", null)}
          onEdit={(b) => {
            setParam("open", null);
            setEditing(b);
            setFormOpen(true);
          }}
        />
      )}
    </>
  );
}

function DayBoard({ day, onDay, onOpen }: { day: string; onDay: (d: string) => void; onOpen: (id: string) => void }) {
  const fields = useFields();
  const bookings = useQuery({
    queryKey: ["ws", "bookings", "day", day],
    queryFn: () => api<Paginated<Booking>>(`/workspace/bookings/?date=${day}&ordering=start&page_size=100`),
    placeholderData: keepPreviousData,
  });
  const active = (fields.data ?? []).filter((f) => f.is_active);
  const rows = (bookings.data?.results ?? []).filter((b) => !["cancelled", "rejected"].includes(b.status));
  const cancelled = (bookings.data?.results ?? []).length - rows.length;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Previous day" onClick={() => onDay(addDays(day, -1))}>
          <ChevronLeft />
        </Button>
        <Button variant="outline" onClick={() => onDay(todayISO())}>
          Today
        </Button>
        <Button variant="outline" size="icon" aria-label="Next day" onClick={() => onDay(addDays(day, 1))}>
          <ChevronRight />
        </Button>
        <Input type="date" aria-label="Date" className="w-44" value={day} onChange={(e) => e.target.value && onDay(e.target.value)} />
        <p className="font-semibold">{fmtDay(`${day}T12:00:00+06:00`)}</p>
        <p className="text-sm text-muted-foreground">
          {rows.length} booking{rows.length === 1 ? "" : "s"}
          {cancelled > 0 && ` · ${cancelled} cancelled/rejected`}
        </p>
      </div>
      {bookings.isError && <ErrorState error={bookings.error} onRetry={() => bookings.refetch()} />}
      {(fields.isPending || bookings.isPending) && <Skeleton className="h-64" />}
      {fields.data && bookings.data && (
        <div className={cn("grid gap-4 md:grid-cols-2 xl:grid-cols-3", bookings.isFetching && "opacity-70")}>
          {active.map((field) => {
            const own = rows.filter((b) => b.field === field.id);
            return (
              <Card key={field.id}>
                <CardContent className="flex flex-col gap-2 p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold">{field.name}</p>
                    <span className="text-xs text-muted-foreground">{own.length} booked</span>
                  </div>
                  {own.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Free all day</p>}
                  {own.map((b) => (
                    <button
                      key={b.id}
                      type="button"
                      onClick={() => onOpen(b.id)}
                      className={cn(
                        "flex items-center justify-between gap-2 rounded-lg border-l-4 bg-secondary/60 p-3 text-left transition hover:bg-secondary",
                        b.status === "pending" && "border-l-amber-500",
                        b.status === "confirmed" && "border-l-sky-500",
                        b.status === "completed" && "border-l-emerald-500",
                        b.status === "no_show" && "border-l-red-500",
                      )}
                    >
                      <div className="min-w-0">
                        <p className="tabular text-sm font-semibold">{fmtRange(b.start, b.end)}</p>
                        <p className="truncate text-sm">{b.team_name || b.customer.name}</p>
                        <p className="text-xs text-muted-foreground">{b.customer.phone}</p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <Badge tone={STATUS_TONE[b.status]}>{b.status_label}</Badge>
                        <Badge tone={STATUS_TONE[b.payment_status]} className="capitalize">
                          {b.payment_status === "paid" ? "Paid" : `Due ${formatBDT(b.due)}`}
                        </Badge>
                      </div>
                    </button>
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

function BookingList({
  params,
  setParam,
  onOpen,
}: {
  params: URLSearchParams;
  setParam: (k: string, v: string | null) => void;
  onOpen: (id: string) => void;
}) {
  const fields = useFields();
  const page = Number(params.get("page") ?? "1");
  const query = new URLSearchParams();
  for (const key of ["q", "status", "field", "from", "to", "page"]) {
    const v = params.get(key);
    if (v) query.set(key, v);
  }
  const list = useQuery({
    queryKey: ["ws", "bookings", "list", query.toString()],
    queryFn: () => api<Paginated<Booking>>(`/workspace/bookings/?${query}`),
    placeholderData: keepPreviousData,
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 20)) : 1;

  return (
    <>
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <form
          className="flex gap-2 lg:col-span-2"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", new FormData(e.currentTarget).get("q")?.toString().trim() || null);
          }}
        >
          <Input name="q" aria-label="Search" placeholder="Reference, name, phone or team" defaultValue={params.get("q") ?? ""} />
          <Button type="submit" variant="outline" size="icon" aria-label="Search">
            <Search />
          </Button>
        </form>
        <Select aria-label="Status" value={params.get("status") ?? ""} onChange={(e) => setParam("status", e.target.value || null)}>
          <option value="">All statuses</option>
          <option value="pending">Pending requests</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="rejected">Rejected</option>
          <option value="no_show">No-show</option>
        </Select>
        <Select aria-label="Field" value={params.get("field") ?? ""} onChange={(e) => setParam("field", e.target.value || null)}>
          <option value="">All fields</option>
          {fields.data?.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </Select>
        <div className="flex gap-2">
          <Input type="date" aria-label="From" value={params.get("from") ?? ""} onChange={(e) => setParam("from", e.target.value || null)} />
          <Input type="date" aria-label="To" value={params.get("to") ?? ""} onChange={(e) => setParam("to", e.target.value || null)} />
        </div>
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-48" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.count === 0 && <EmptyState icon={<CalendarX2 />} title="No bookings match" />}
          {list.data && list.data.count > 0 && (
            <Table className={cn(list.isFetching && "opacity-70")}>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Customer</th>
                  <th>Field</th>
                  <th>Status</th>
                  <th className="text-right">Total</th>
                  <th className="text-right">Due</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((b) => (
                  <tr key={b.id} className="cursor-pointer hover:bg-secondary/60" onClick={() => onOpen(b.id)}>
                    <td className="whitespace-nowrap">
                      {fmtDay(b.start)}
                      <span className="block text-xs text-muted-foreground">{fmtRange(b.start, b.end)}</span>
                    </td>
                    <td>
                      <button type="button" className="text-left font-medium hover:text-primary" onClick={() => onOpen(b.id)}>
                        {b.team_name || b.customer.name}
                      </button>
                      <span className="block text-xs text-muted-foreground">
                        {b.customer.phone} · {b.reference}
                      </span>
                    </td>
                    <td>{b.field_name}</td>
                    <td>
                      <Badge tone={STATUS_TONE[b.status]}>{b.status_label}</Badge>
                    </td>
                    <td className="tabular text-right">{formatBDT(b.total)}</td>
                    <td className={cn("tabular text-right", Number(b.due) > 0 && "font-semibold text-destructive")}>
                      {Number(b.due) > 0 ? formatBDT(b.due) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>
                Previous
              </Button>
              <span className="text-sm">
                Page {page} of {pages}
              </span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setParam("page", String(page + 1))}>
                Next
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

const DURATIONS = [60, 90, 120, 150, 180];

function emptyForm(day: string, fieldId: string) {
  return {
    field: fieldId,
    day,
    time: "18:00",
    minutes: 60,
    customer_name: "",
    customer_phone: "",
    customer_email: "",
    team_name: "",
    notes: "",
    discount: "0",
    status: "confirmed",
    source: "phone",
    advance_amount: "",
    advance_method: "cash",
  };
}

function BookingFormDialog({
  open,
  booking,
  defaultDay,
  onClose,
  onSaved,
}: {
  open: boolean;
  booking: Booking | null;
  defaultDay: string;
  onClose: () => void;
  onSaved: (b: Booking) => void;
}) {
  const qc = useQueryClient();
  const fields = useFields();
  const activeFields = (fields.data ?? []).filter((f) => f.is_active);
  const [form, setForm] = useState(() => emptyForm(defaultDay, ""));

  useEffect(() => {
    if (!open) return;
    if (booking) {
      const minutes = Math.round((new Date(booking.end).getTime() - new Date(booking.start).getTime()) / 60000);
      setForm({
        ...emptyForm(dhakaDay(booking.start), booking.field),
        time: fmtTime24(booking.start),
        minutes,
        customer_name: booking.customer.name,
        customer_phone: booking.customer.phone,
        customer_email: booking.customer.email,
        team_name: booking.team_name,
        notes: booking.notes,
        discount: booking.discount,
      });
    } else {
      setForm(emptyForm(defaultDay, activeFields[0]?.id ?? ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, booking]);

  useEffect(() => {
    if (open && !form.field && activeFields[0]) setForm((f) => ({ ...f, field: activeFields[0]!.id }));
  }, [open, form.field, activeFields]);

  const start = dhakaISO(form.day, form.time);
  const end = new Date(new Date(start).getTime() + form.minutes * 60000).toISOString();
  const quote = useQuery({
    queryKey: ["ws", "quote", form.field, start, end, booking?.id],
    queryFn: () =>
      api<{ subtotal: string; available: boolean; segments: { label: string; minutes: number; amount: string }[] }>(
        "/workspace/quote/",
        { method: "POST", json: { field: form.field, start, end, ...(booking ? { exclude: booking.id } : {}) } },
      ),
    enabled: open && Boolean(form.field && form.day && form.time),
    retry: false,
  });

  const save = useMutation({
    mutationFn: () => {
      const body = {
        field: form.field,
        start,
        end,
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        customer_email: form.customer_email,
        team_name: form.team_name,
        notes: form.notes,
        discount: form.discount || "0",
        status: form.status,
        source: form.source,
        advance_amount: form.advance_amount || "0",
        advance_method: form.advance_method,
      };
      return booking
        ? api<Booking>(`/workspace/bookings/${booking.id}/`, { method: "PUT", json: body })
        : api<Booking>("/workspace/bookings/", { method: "POST", json: body });
    },
    onSuccess: (b) => {
      toast.success(booking ? "Booking updated" : `Booking ${b.reference} created`);
      qc.invalidateQueries({ queryKey: ["ws"] });
      onSaved(b);
    },
  });

  const set = (key: keyof ReturnType<typeof emptyForm>) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: key === "minutes" ? Number(e.target.value) : e.target.value }));
  const total = quote.data ? Math.max(0, Number(quote.data.subtotal) - Number(form.discount || 0)) : null;

  return (
    <Dialog open={open} onClose={onClose} title={booking ? `Edit ${booking.reference}` : "New booking"} wide>
      <form
        className="grid gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Field">
          {(id) => (
            <Select id={id} required value={form.field} onChange={set("field")}>
              {activeFields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        <FormField label="Date">
          {(id) => <Input id={id} type="date" required value={form.day} onChange={set("day")} />}
        </FormField>
        <FormField label="Start time" hint="15-minute steps">
          {(id) => <Input id={id} type="time" step={900} required value={form.time} onChange={set("time")} />}
        </FormField>
        <FormField label="Duration">
          {(id) => (
            <Select id={id} value={form.minutes} onChange={set("minutes")}>
              {[...new Set([...DURATIONS, form.minutes])].sort((a, b) => a - b).map((m) => (
                <option key={m} value={m}>
                  {m % 60 === 0 ? `${m / 60} hour${m === 60 ? "" : "s"}` : `${(m / 60).toFixed(1)} hours`}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        <div className="rounded-lg bg-secondary/70 p-3 text-sm sm:col-span-2" aria-live="polite">
          {quote.isFetching && <Loader2 className="size-4 animate-spin" />}
          {quote.isError && <span className="text-destructive">{errorText(quote.error)}</span>}
          {quote.data && !quote.isFetching && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {quote.data.segments.map((s) => `${s.label} ${s.minutes}m ${formatBDT(s.amount)}`).join(" + ")}
              </span>
              {quote.data.available ? (
                <span className="tabular font-semibold">{formatBDT(total ?? 0)}</span>
              ) : (
                <Badge tone="red">Slot already booked</Badge>
              )}
            </div>
          )}
        </div>
        <FormField label="Customer name">
          {(id) => <Input id={id} required value={form.customer_name} onChange={set("customer_name")} />}
        </FormField>
        <FormField label="Mobile number">
          {(id) => <Input id={id} required type="tel" placeholder="01XXXXXXXXX" value={form.customer_phone} onChange={set("customer_phone")} />}
        </FormField>
        <FormField label="Team name (optional)">
          {(id) => <Input id={id} value={form.team_name} onChange={set("team_name")} />}
        </FormField>
        <FormField label="Discount (৳)">
          {(id) => <Input id={id} type="number" min={0} step={10} value={form.discount} onChange={set("discount")} />}
        </FormField>
        {!booking && (
          <>
            <FormField label="Status">
              {(id) => (
                <Select id={id} value={form.status} onChange={set("status")}>
                  <option value="confirmed">Confirmed</option>
                  <option value="pending">Pending (hold slot)</option>
                </Select>
              )}
            </FormField>
            <FormField label="Booked via">
              {(id) => (
                <Select id={id} value={form.source} onChange={set("source")}>
                  <option value="phone">Phone</option>
                  <option value="walk_in">Walk-in</option>
                  <option value="staff">Other</option>
                </Select>
              )}
            </FormField>
            <FormField label="Advance received (৳)">
              {(id) => <Input id={id} type="number" min={0} step={50} placeholder="0" value={form.advance_amount} onChange={set("advance_amount")} />}
            </FormField>
            <FormField label="Advance method">
              {(id) => (
                <Select id={id} value={form.advance_method} onChange={set("advance_method")}>
                  {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
          </>
        )}
        <FormField label="Notes" className="sm:col-span-2">
          {(id) => <Textarea id={id} rows={2} value={form.notes} onChange={set("notes")} />}
        </FormField>
        {save.error && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive sm:col-span-2">
            {errorText(save.error)}
          </p>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending || quote.data?.available === false}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {booking ? "Save changes" : "Create booking"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function fmtTime24(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
}

function BookingDetailDialog({ id, onClose, onEdit }: { id: string; onClose: () => void; onEdit: (b: Booking) => void }) {
  const qc = useQueryClient();
  const booking = useQuery({ queryKey: ["ws", "booking", id], queryFn: () => api<Booking>(`/workspace/bookings/${id}/`) });
  const [payment, setPayment] = useState({ amount: "", method: "cash", kind: "payment", reference: "" });

  const done = (b: Booking, message: string) => {
    toast.success(message);
    qc.setQueryData(["ws", "booking", id], b);
    qc.invalidateQueries({ queryKey: ["ws", "bookings"] });
    qc.invalidateQueries({ queryKey: ["ws", "dashboard"] });
  };
  const status = useMutation({
    mutationFn: (to: BookingStatus) => api<Booking>(`/workspace/bookings/${id}/status/`, { method: "POST", json: { status: to } }),
    onSuccess: (b) => done(b, `Booking ${b.status_label.toLowerCase()}`),
    onError: (e) => toast.error(errorText(e)),
  });
  const pay = useMutation({
    mutationFn: () => api<Booking>(`/workspace/bookings/${id}/payments/`, { method: "POST", json: payment }),
    onSuccess: (b) => {
      done(b, payment.kind === "refund" ? "Refund recorded" : "Payment recorded");
      setPayment({ amount: "", method: "cash", kind: "payment", reference: "" });
    },
  });

  const b = booking.data;
  return (
    <Dialog open onClose={onClose} title={b ? b.reference : "Booking"} wide>
      {booking.isPending && <Skeleton className="h-40" />}
      {booking.isError && <ErrorState error={booking.error} />}
      {b && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[b.status]}>{b.status_label}</Badge>
            <Badge tone={STATUS_TONE[b.payment_status]} className="capitalize">
              {b.payment_status}
            </Badge>
            <span className="text-sm text-muted-foreground">via {b.source_label}</span>
          </div>
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">When</dt>
              <dd className="font-medium">
                {fmtDay(b.start)}, {fmtRange(b.start, b.end)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Field</dt>
              <dd className="font-medium">{b.field_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Customer</dt>
              <dd className="font-medium">
                {b.customer.name}
                {b.team_name && <span className="text-muted-foreground"> · {b.team_name}</span>}
              </dd>
              <dd>
                <a className="text-primary hover:underline" href={`tel:${b.customer.phone}`}>
                  {b.customer.phone}
                </a>
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Price</dt>
              <dd className="tabular">
                {formatBDT(b.subtotal)}
                {Number(b.discount) > 0 && ` − ${formatBDT(b.discount)} discount`} ={" "}
                <strong>{formatBDT(b.total)}</strong>
              </dd>
              <dd className="tabular text-muted-foreground">
                Paid {formatBDT(b.amount_paid)} · Due <strong className={cn(Number(b.due) > 0 && "text-destructive")}>{formatBDT(b.due)}</strong>
              </dd>
            </div>
            {b.notes && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Notes</dt>
                <dd className="whitespace-pre-line">{b.notes}</dd>
              </div>
            )}
          </dl>

          {(STATUS_ACTIONS[b.status].length > 0 || ["pending", "confirmed"].includes(b.status)) && (
            <div className="flex flex-wrap gap-2 border-t pt-4">
              {STATUS_ACTIONS[b.status].map((a) => (
                <Button key={a.to} variant={a.variant ?? "default"} size="sm" disabled={status.isPending} onClick={() => status.mutate(a.to)}>
                  {a.label}
                </Button>
              ))}
              {["pending", "confirmed"].includes(b.status) && (
                <Button variant="outline" size="sm" onClick={() => onEdit(b)}>
                  <Pencil /> Edit / reschedule
                </Button>
              )}
            </div>
          )}

          <div className="border-t pt-4">
            <h3 className="mb-2 font-semibold">Payments</h3>
            {b.payments?.length === 0 && <p className="text-sm text-muted-foreground">No payments yet.</p>}
            <ul className="flex flex-col gap-1 text-sm">
              {b.payments?.map((p) => (
                <li key={p.id} className="flex justify-between gap-2">
                  <span>
                    {fmtDateTime(p.paid_at)} · {PAYMENT_METHODS[p.method] ?? p.method}
                    {p.reference && ` · ${p.reference}`}
                    {p.received_by_name && <span className="text-muted-foreground"> · {p.received_by_name}</span>}
                  </span>
                  <span className={cn("tabular font-medium", p.kind === "refund" && "text-destructive")}>
                    {p.kind === "refund" ? "−" : ""}
                    {formatBDT(p.amount)}
                  </span>
                </li>
              ))}
            </ul>
            {!["rejected"].includes(b.status) && (
              <form
                className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]"
                onSubmit={(e) => {
                  e.preventDefault();
                  pay.mutate();
                }}
              >
                <Input aria-label="Amount" type="number" min={1} step="0.01" required placeholder={Number(b.due) > 0 ? b.due : "Amount"} value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })} />
                <Select aria-label="Method" value={payment.method} onChange={(e) => setPayment({ ...payment, method: e.target.value })}>
                  {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
                <Select aria-label="Type" value={payment.kind} onChange={(e) => setPayment({ ...payment, kind: e.target.value })}>
                  <option value="payment">Payment</option>
                  <option value="refund">Refund</option>
                </Select>
                <Input aria-label="Transaction ID" placeholder="Txn ID (optional)" value={payment.reference} onChange={(e) => setPayment({ ...payment, reference: e.target.value })} />
                <Button type="submit" disabled={pay.isPending}>
                  Record
                </Button>
                {pay.error && <p className="text-sm text-destructive sm:col-span-5">{errorText(pay.error)}</p>}
              </form>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}
