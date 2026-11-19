import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, ChevronLeft, ChevronRight, Loader2, Phone, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, Dialog, EmptyState, ErrorState, FormField, Input, Select, STATUS_TONE, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { PAYMENT_METHODS, addDays, fmtDay, fmtRange, todayISO } from "@/lib/format";
import type { BoardSlot, SlotBoard } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText } from "./hooks";

const DAYS_SHOWN = 14;

const STATE_STYLE: Record<BoardSlot["state"], string> = {
  free: "border-border bg-card hover:border-primary hover:shadow-sm",
  booked: "border-sky-600/40 bg-sky-600/10 text-sky-900 dark:text-sky-100",
  pending: "border-amber-500/50 bg-amber-400/15 text-amber-900 dark:text-amber-100",
  maintenance:
    "border-dashed border-muted-foreground/40 bg-[repeating-linear-gradient(135deg,transparent_0_6px,color-mix(in_oklch,var(--muted-foreground)_12%,transparent)_6px_12px)] text-muted-foreground",
  past: "border-transparent bg-muted/60 text-muted-foreground opacity-60",
};

const LEGEND: { state: BoardSlot["state"]; label: string; swatch: string }[] = [
  { state: "free", label: "Free", swatch: "border bg-card" },
  { state: "booked", label: "Booked", swatch: "bg-sky-600/30" },
  { state: "pending", label: "Request (unconfirmed)", swatch: "bg-amber-400/50" },
  { state: "maintenance", label: "Maintenance", swatch: "border border-dashed border-muted-foreground/50" },
  { state: "past", label: "Past", swatch: "bg-muted" },
];

const EMPTY_FORM = {
  customer_name: "",
  customer_phone: "",
  team_name: "",
  notes: "",
  status: "confirmed",
  source: "phone",
  advance_amount: "",
  advance_method: "cash",
  discount_value: "",
  discount_mode: "amount" as "amount" | "percent",
};

const QUICK_PERCENTS = [5, 10, 15, 20];

/** Discount in taka from the form's amount-or-percent input, rounded to whole taka. */
function discountTaka(subtotal: number, value: string, mode: "amount" | "percent"): number {
  const n = Number(value);
  if (!value || !Number.isFinite(n) || n <= 0) return 0;
  return Math.round(mode === "percent" ? (subtotal * n) / 100 : n);
}

/** Owner/manager view of every slot for a field and day: book free ones, see who holds the rest. */
export function SlotBoardPage() {
  const qc = useQueryClient();
  const [day, setDay] = useState(todayISO());
  const [fieldId, setFieldId] = useState<string>("");
  const [range, setRange] = useState<{ from: number; to: number } | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [openSlot, setOpenSlot] = useState<BoardSlot | null>(null);
  const days = useMemo(() => Array.from({ length: DAYS_SHOWN }, (_, i) => addDays(todayISO(), i)), []);

  const board = useQuery({
    queryKey: ["ws", "board", day],
    queryFn: () => api<SlotBoard>(`/workspace/availability/?date=${day}&detail=1`),
    refetchInterval: 60_000, // pick up online requests that arrive while the page is open
  });

  const fields = board.data?.fields ?? [];
  useEffect(() => {
    if (fields.length && !fields.some((f) => f.id === fieldId)) setFieldId(fields[0]!.id);
  }, [fields, fieldId]);
  const field = fields.find((f) => f.id === fieldId);
  const slots = field?.slots ?? [];
  const chosen = range ? slots.slice(range.from, range.to + 1) : [];
  const subtotal = chosen.reduce((sum, s) => sum + Number(s.price ?? 0), 0);
  const discount = discountTaka(subtotal, form.discount_value, form.discount_mode);
  const total = Math.max(0, subtotal - discount);
  const advance = Number(form.advance_amount) || 0;
  const discountError =
    discount > subtotal
      ? "Discount can't be more than the price."
      : form.discount_mode === "percent" && Number(form.discount_value) > 100
        ? "Use a percentage up to 100."
        : null;
  const advanceError = advance > total ? "Advance can't be more than the total after discount." : null;

  const counts = slots.reduce<Record<string, number>>((acc, s) => ({ ...acc, [s.state]: (acc[s.state] ?? 0) + 1 }), {});

  const resetSelection = () => setRange(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ws", "board"] });
    qc.invalidateQueries({ queryKey: ["ws", "bookings"] });
    qc.invalidateQueries({ queryKey: ["ws", "dashboard"] });
  };

  const book = useMutation({
    mutationFn: () => {
      const { discount_value: _value, discount_mode: _mode, ...fields } = form;
      return api("/workspace/bookings/", {
        method: "POST",
        json: {
          field: fieldId,
          start: chosen[0]?.start,
          end: chosen.at(-1)?.end,
          ...fields,
          discount: discount.toFixed(2),
          advance_amount: form.advance_amount || "0",
        },
      });
    },
    onSuccess: () => {
      toast.success(`Booked ${fmtRange(chosen[0]!.start, chosen.at(-1)!.end)} for ${form.team_name || form.customer_name}`);
      setForm(EMPTY_FORM);
      resetSelection();
      refresh();
    },
    onError: () => board.refetch(), // someone may have taken the slot meanwhile
  });
  const fieldErrors = book.error instanceof ApiError ? book.error.fields : null;

  const pick = (i: number) => {
    const slot = slots[i];
    if (!slot) return;
    if (slot.state !== "free") {
      if (slot.booking || slot.state === "maintenance") setOpenSlot(slot);
      return;
    }
    if (range && i === range.to + 1) setRange({ from: range.from, to: i });
    else if (range && i === range.from - 1) setRange({ from: i, to: range.to });
    else if (range && i >= range.from && i <= range.to) setRange(null);
    else setRange({ from: i, to: i });
  };

  const shiftDay = (delta: number) => {
    setDay((d) => addDays(d, delta));
    resetSelection();
  };

  return (
    <>
      <PageHeader
        title="Book a slot"
        description="See every slot at a glance. Tap free slots to book them for a team; tap a booked slot to see who has it."
        actions={
          <Button variant="outline" asChild>
            <Link to="/workspace/bookings">
              <CalendarCheck2 /> All bookings
            </Link>
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:p-6">
          {fields.length > 1 && (
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Field">
              {fields.map((f) => {
                const free = f.slots.filter((s) => s.state === "free").length;
                return (
                  <button
                    key={f.id}
                    type="button"
                    role="radio"
                    aria-checked={f.id === fieldId}
                    onClick={() => {
                      setFieldId(f.id);
                      resetSelection();
                    }}
                    className={cn(
                      "rounded-full border px-4 py-2 text-sm font-semibold transition",
                      f.id === fieldId ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
                    )}
                  >
                    {f.name}
                    {f.size && <span className="font-normal opacity-75"> · {f.size}</span>}
                    <span className="ml-2 rounded-full bg-black/10 px-1.5 text-xs font-medium">{free} free</span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" aria-label="Previous day" disabled={day <= todayISO()} onClick={() => shiftDay(-1)}>
              <ChevronLeft />
            </Button>
            <div className="-mx-1 flex flex-1 gap-2 overflow-x-auto px-1 pb-1" role="radiogroup" aria-label="Date">
              {days.map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={d === day}
                  onClick={() => {
                    setDay(d);
                    resetSelection();
                  }}
                  className={cn(
                    "shrink-0 rounded-lg border px-3 py-2 text-sm font-medium transition",
                    d === day ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
                  )}
                >
                  {d === todayISO() ? "Today" : fmtDay(`${d}T12:00:00+06:00`)}
                </button>
              ))}
            </div>
            <Button variant="ghost" size="icon" aria-label="Next day" onClick={() => shiftDay(1)}>
              <ChevronRight />
            </Button>
            <Input
              type="date"
              aria-label="Jump to date"
              className="hidden w-40 sm:block"
              min={todayISO()}
              value={day}
              onChange={(e) => {
                if (e.target.value) {
                  setDay(e.target.value);
                  resetSelection();
                }
              }}
            />
          </div>

          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
            {LEGEND.map((l) => (
              <li key={l.state} className="flex items-center gap-1.5">
                <span className={cn("inline-block size-3 rounded-sm", l.swatch)} />
                {l.label}
                {counts[l.state] ? <span className="tabular font-semibold text-foreground">{counts[l.state]}</span> : null}
              </li>
            ))}
          </ul>

          {board.isPending && <Skeleton className="h-64" />}
          {board.isError && <ErrorState error={board.error} onRetry={() => board.refetch()} />}
          {board.data && fields.length === 0 && (
            <EmptyState title="No active fields">
              Add a field under <Link className="text-primary hover:underline" to="/workspace/fields">Fields</Link> first.
            </EmptyState>
          )}
          {field && slots.length === 0 && <p className="text-sm text-muted-foreground">Closed on this day (see Opening hours).</p>}

          {slots.length > 0 && (
            <div className={cn("grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4", board.isFetching && "opacity-80")}>
              {slots.map((s, i) => {
                const selected = range !== null && i >= range.from && i <= range.to;
                const who = s.booking ? s.booking.team_name || s.booking.customer_name : null;
                return (
                  <button
                    key={s.start}
                    type="button"
                    disabled={s.state === "past" && !s.booking}
                    aria-pressed={s.state === "free" ? selected : undefined}
                    onClick={() => pick(i)}
                    className={cn(
                      "flex min-h-[4.25rem] flex-col items-start rounded-lg border px-3 py-2 text-left text-sm transition",
                      STATE_STYLE[s.state],
                      s.state === "past" && s.booking && "opacity-70",
                      selected && "border-primary bg-primary text-primary-foreground hover:border-primary",
                    )}
                  >
                    <span className="font-semibold">{fmtRange(s.start, s.end)}</span>
                    {s.state === "free" && s.price && <span className="tabular text-xs opacity-80">{formatBDT(s.price)}</span>}
                    {who && <span className="w-full truncate text-xs font-medium">{who}</span>}
                    {s.state === "pending" && <span className="text-[11px] font-semibold uppercase">Needs confirming</span>}
                    {s.state === "booked" && s.booking && (
                      <span className="text-[11px] capitalize opacity-80">{s.booking.status.replace("_", " ")}</span>
                    )}
                    {s.state === "maintenance" && (
                      <span className="flex items-center gap-1 text-xs">
                        <Wrench className="size-3" /> {s.reason || "Maintenance"}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {chosen.length > 0 && (
            <form
              className="mt-2 flex flex-col gap-3 border-t pt-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (!discountError && !advanceError) book.mutate();
              }}
            >
              <p className="text-sm">
                <span className="font-semibold">
                  {field?.name} · {fmtDay(chosen[0]!.start)} · {fmtRange(chosen[0]!.start, chosen.at(-1)!.end)}
                </span>
                {subtotal > 0 && (
                  <>
                    {" "}
                    · <span className="tabular font-semibold">{formatBDT(String(total))}</span>
                    {discount > 0 && (
                      <span className="tabular ml-1 text-xs text-muted-foreground line-through">{formatBDT(String(subtotal))}</span>
                    )}
                  </>
                )}
                <button type="button" className="ml-3 text-xs text-muted-foreground hover:text-foreground" onClick={resetSelection}>
                  Clear
                </button>
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <FormField label="Team name" error={fieldErrors?.team_name}>
                  {(id) => <Input id={id} placeholder="e.g. Banani FC" value={form.team_name} onChange={(e) => setForm({ ...form, team_name: e.target.value })} />}
                </FormField>
                <FormField label="Contact name" error={fieldErrors?.customer_name}>
                  {(id) => <Input id={id} required value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })} />}
                </FormField>
                <FormField label="Mobile number" error={fieldErrors?.customer_phone}>
                  {(id) => (
                    <Input id={id} required type="tel" inputMode="tel" placeholder="01XXXXXXXXX" value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })} />
                  )}
                </FormField>
                <FormField label="Discount" error={discountError ?? fieldErrors?.discount} hint="Optional. In taka or as a percentage of the price.">
                  {(id) => (
                    <div className="flex flex-col gap-2">
                      <div className="flex">
                        <Input
                          id={id}
                          type="number"
                          min={0}
                          max={form.discount_mode === "percent" ? 100 : subtotal}
                          step={form.discount_mode === "percent" ? 1 : "0.01"}
                          placeholder="0"
                          className="rounded-r-none"
                          value={form.discount_value}
                          onChange={(e) => setForm({ ...form, discount_value: e.target.value })}
                        />
                        <div className="flex shrink-0 overflow-hidden rounded-r-md border border-l-0" role="radiogroup" aria-label="Discount type">
                          {(["amount", "percent"] as const).map((mode) => (
                            <button
                              key={mode}
                              type="button"
                              role="radio"
                              aria-checked={form.discount_mode === mode}
                              aria-label={mode === "amount" ? "Taka" : "Percent"}
                              onClick={() => setForm({ ...form, discount_mode: mode })}
                              className={cn(
                                "w-9 text-sm font-semibold transition",
                                form.discount_mode === mode ? "bg-primary text-primary-foreground" : "hover:bg-secondary",
                              )}
                            >
                              {mode === "amount" ? "৳" : "%"}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {QUICK_PERCENTS.map((pct) => {
                          const active = form.discount_mode === "percent" && form.discount_value === String(pct);
                          return (
                            <button
                              key={pct}
                              type="button"
                              aria-pressed={active}
                              onClick={() =>
                                setForm({ ...form, discount_mode: "percent", discount_value: active ? "" : String(pct) })
                              }
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-xs transition",
                                active ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
                              )}
                            >
                              {pct}%
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </FormField>
                <FormField label="Advance received (৳)" error={advanceError ?? fieldErrors?.advance_amount} hint="Leave empty if nothing paid yet.">
                  {(id) => (
                    <Input id={id} type="number" min={0} step="0.01" value={form.advance_amount} onChange={(e) => setForm({ ...form, advance_amount: e.target.value })} />
                  )}
                </FormField>
                <FormField label="Paid by">
                  {(id) => (
                    <Select id={id} value={form.advance_method} onChange={(e) => setForm({ ...form, advance_method: e.target.value })}>
                      {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Status">
                  {(id) => (
                    <Select id={id} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                      <option value="confirmed">Confirmed</option>
                      <option value="pending">Pending (hold, confirm later)</option>
                    </Select>
                  )}
                </FormField>
              </div>
              <FormField label="Notes (optional)">
                {(id) => <Textarea id={id} rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}
              </FormField>
              {subtotal > 0 && (
                <dl className="tabular grid max-w-sm grid-cols-[1fr_auto] gap-x-6 gap-y-1 rounded-lg bg-secondary/60 px-4 py-3 text-sm" aria-label="Price summary">
                  <dt className="text-muted-foreground">Price</dt>
                  <dd className="text-right">{formatBDT(String(subtotal))}</dd>
                  {discount > 0 && (
                    <>
                      <dt className="text-muted-foreground">
                        Discount{form.discount_mode === "percent" && ` (${form.discount_value}%)`}
                      </dt>
                      <dd className="text-right text-primary">− {formatBDT(String(Math.min(discount, subtotal)))}</dd>
                    </>
                  )}
                  <dt className="font-semibold">Total</dt>
                  <dd className="text-right font-semibold">{formatBDT(String(total))}</dd>
                  {advance > 0 && (
                    <>
                      <dt className="text-muted-foreground">Advance</dt>
                      <dd className="text-right">− {formatBDT(String(advance))}</dd>
                      <dt className="font-semibold">Due at the turf</dt>
                      <dd className="text-right font-semibold">{formatBDT(String(Math.max(0, total - advance)))}</dd>
                    </>
                  )}
                </dl>
              )}
              {book.error && (
                <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {errorText(book.error)}
                </p>
              )}
              <Button type="submit" size="lg" disabled={book.isPending} className="self-start">
                {book.isPending ? <Loader2 className="animate-spin" /> : <CalendarCheck2 />}
                Book {chosen.length > 1 ? `${chosen.length} slots` : "slot"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      <SlotDetailDialog slot={openSlot} onClose={() => setOpenSlot(null)} onChanged={refresh} />
    </>
  );
}

function SlotDetailDialog({ slot, onClose, onChanged }: { slot: BoardSlot | null; onClose: () => void; onChanged: () => void }) {
  const b = slot?.booking;
  const setStatus = useMutation({
    mutationFn: (status: string) => api(`/workspace/bookings/${b?.id}/status/`, { method: "POST", json: { status } }),
    onSuccess: (_, status) => {
      toast.success(status === "confirmed" ? "Booking confirmed" : "Booking updated");
      onChanged();
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const due = b ? Number(b.total) - Number(b.amount_paid) : 0;

  return (
    <Dialog open={slot !== null} onClose={onClose} title={b ? b.team_name || b.customer_name : "Maintenance"}>
      {slot && !b && (
        <p className="text-sm text-muted-foreground">
          {fmtRange(slot.start, slot.end)} is blocked: {slot.reason || "maintenance"}. Manage blocks under{" "}
          <Link to="/workspace/maintenance" className="text-primary hover:underline">
            Maintenance
          </Link>
          .
        </p>
      )}
      {b && (
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[b.status]} className="capitalize">
              {b.status.replace("_", " ")}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">{b.reference}</span>
          </div>
          <p>
            <span className="font-semibold">{fmtDay(b.start)}</span> · {fmtRange(b.start, b.end)}
          </p>
          <p>
            {b.customer_name}
            {b.team_name && <span className="text-muted-foreground"> · {b.team_name}</span>}
          </p>
          <a href={`tel:${b.customer_phone}`} className="flex items-center gap-1.5 text-primary hover:underline">
            <Phone className="size-4" /> {b.customer_phone}
          </a>
          <p className="tabular">
            Total {formatBDT(b.total)} · Paid {formatBDT(b.amount_paid)}
            {due > 0 && <span className="font-semibold text-destructive"> · Due {formatBDT(String(due))}</span>}
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            {b.status === "pending" && (
              <Button onClick={() => setStatus.mutate("confirmed")} disabled={setStatus.isPending}>
                Confirm booking
              </Button>
            )}
            {(b.status === "pending" || b.status === "confirmed") && (
              <Button
                variant="outline"
                disabled={setStatus.isPending}
                onClick={() => window.confirm("Cancel this booking and free the slot?") && setStatus.mutate("cancelled")}
              >
                Cancel booking
              </Button>
            )}
            <Button variant="ghost" asChild>
              <Link to={`/workspace/bookings?view=list&q=${encodeURIComponent(b.reference)}`}>Payments & details</Link>
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
