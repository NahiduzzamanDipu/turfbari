import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarRange, Copy, Loader2, Pencil, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, ErrorState, FormField, Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/auth";
import { ApiError, api } from "@/lib/api";
import { fmtClock } from "@/lib/format";
import { cn, formatBDT } from "@/lib/utils";
import { errorText, useFields } from "./hooks";

export type CategoryKey = "morning" | "evening" | "night" | "midnight";
export const CATEGORY: Record<CategoryKey, { label: string; bn: string; tone: BadgeTone; dot: string }> = {
  morning: { label: "Morning", bn: "সকাল", tone: "amber", dot: "bg-amber-400" },
  evening: { label: "Evening", bn: "বিকাল", tone: "lime", dot: "bg-lime-500" },
  night: { label: "Night", bn: "রাত", tone: "blue", dot: "bg-sky-500" },
  midnight: { label: "Midnight", bn: "মধ্যরাত", tone: "neutral", dot: "bg-indigo-500" },
};
const ORDER: CategoryKey[] = ["morning", "evening", "night", "midnight"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface Band {
  key: CategoryKey;
  label: string;
  start: string;
  end: string;
  hourly_rate: string;
}
interface CategoriesResponse {
  enabled: boolean;
  categories: Band[];
  suggested?: { key: CategoryKey; start: string; hourly_rate: string }[];
}

const hhmm = (t: string) => fmtClock(t.length === 5 ? `${t}:00` : t);

// ------------------------------------------------------------------ four-category pricing (card)
export function TimeOfDayPricingCard() {
  const qc = useQueryClient();
  const canEdit = useCan("manage_slots");
  const data = useQuery({ queryKey: ["ws", "price-categories"], queryFn: () => api<CategoriesResponse>("/workspace/price-categories/") });
  const [rows, setRows] = useState<{ key: CategoryKey; starts_at: string; hourly_rate: string }[] | null>(null);
  useEffect(() => {
    if (!data.data || rows) return;
    const source = data.data.enabled
      ? data.data.categories.map((b) => ({ key: b.key, starts_at: b.start, hourly_rate: b.hourly_rate }))
      : (data.data.suggested ?? []).map((s) => ({ key: s.key, starts_at: s.start, hourly_rate: s.hourly_rate }));
    setRows(ORDER.map((k) => source.find((r) => r.key === k)!).filter(Boolean));
  }, [data.data, rows]);
  const save = useMutation({
    mutationFn: (enabled: boolean) =>
      api<CategoriesResponse>("/workspace/price-categories/", { method: "PUT", json: enabled ? { enabled, categories: rows } : { enabled } }),
    onSuccess: (d) => {
      toast.success(d.enabled ? "Time-of-day prices saved" : "Time-of-day pricing turned off");
      qc.setQueryData(["ws", "price-categories"], d);
      setRows(null);
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const enabled = data.data?.enabled ?? false;
  const fieldErr = save.error instanceof ApiError ? save.error.fields?.categories?.[0] : null;
  // Each band ends where the next one starts.
  const endOf = (i: number) => (rows ? rows[(i + 1) % rows.length]?.starts_at : "");

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Time-of-day prices {enabled ? <Badge tone="green">On</Badge> : <Badge tone="neutral">Off</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Four prices for the day — Morning, Evening, Night and Midnight. A slot takes the price of the period it <strong>starts</strong> in
          (a 5:30–6:30 PM slot is an Evening slot). Special-date rules below and fixed slot prices still win.
        </p>
        {data.isPending && <Skeleton className="h-32" />}
        {data.isError && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
        {rows && (
          <fieldset disabled={!canEdit || save.isPending} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {rows.map((r, i) => (
              <div key={r.key} className="rounded-xl border p-3">
                <p className="mb-2 flex items-center gap-2 font-semibold">
                  <span className={cn("size-2.5 rounded-full", CATEGORY[r.key].dot)} />
                  {CATEGORY[r.key].label} <span className="text-sm font-normal text-muted-foreground">{CATEGORY[r.key].bn}</span>
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <FormField label="Starts">
                    {(id) => (
                      <Input
                        id={id}
                        type="time"
                        step={900}
                        value={r.starts_at}
                        onChange={(e) => setRows(rows.map((x) => (x.key === r.key ? { ...x, starts_at: e.target.value } : x)))}
                      />
                    )}
                  </FormField>
                  <FormField label="৳ per hour">
                    {(id) => (
                      <Input
                        id={id}
                        type="number"
                        min={0}
                        step="0.01"
                        value={r.hourly_rate}
                        onChange={(e) => setRows(rows.map((x) => (x.key === r.key ? { ...x, hourly_rate: e.target.value } : x)))}
                      />
                    )}
                  </FormField>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {hhmm(r.starts_at)} – {endOf(i) ? hhmm(endOf(i)!) : "…"}
                </p>
              </div>
            ))}
          </fieldset>
        )}
        {fieldErr && <p className="text-sm text-destructive">{fieldErr}</p>}
        {canEdit && rows && (
          <div className="flex flex-wrap justify-end gap-2">
            {enabled && (
              <Button variant="ghost" disabled={save.isPending} onClick={() => window.confirm("Turn off time-of-day prices? Fields go back to their standard rates and your rules.") && save.mutate(false)}>
                Turn off
              </Button>
            )}
            <Button disabled={save.isPending} onClick={() => save.mutate(true)}>
              {save.isPending && <Loader2 className="animate-spin" />} {enabled ? "Save prices" : "Turn on with these prices"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ custom slots page
interface SlotTemplate {
  id: string;
  field: string;
  weekday: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
  price: string | null;
  minutes: number;
  category: CategoryKey | null;
  crosses_into: CategoryKey | null;
}

export function SlotSchedulePage() {
  const qc = useQueryClient();
  const canEdit = useCan("manage_slots");
  const fields = useFields();
  const [fieldId, setFieldId] = useState("");
  const field = fields.data?.find((f) => f.id === fieldId) ?? fields.data?.[0];
  const slots = useQuery({
    queryKey: ["ws", "slot-templates", field?.id],
    queryFn: () => api<SlotTemplate[]>(`/workspace/slot-templates/?field=${field!.id}`),
    enabled: Boolean(field),
  });
  const [editing, setEditing] = useState<Partial<SlotTemplate> | null>(null);
  const [generating, setGenerating] = useState(false);
  const refresh = (rows?: SlotTemplate[]) => {
    if (rows) qc.setQueryData(["ws", "slot-templates", field?.id], rows);
    qc.invalidateQueries({ queryKey: ["ws", "slot-templates"] });
    qc.invalidateQueries({ queryKey: ["ws", "board"] });
  };
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<SlotTemplate> }) => api(`/workspace/slot-templates/${id}/`, { method: "PATCH", json: body }),
    onSuccess: () => refresh(),
    onError: (e) => toast.error(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/slot-templates/${id}/`, { method: "DELETE" }),
    onSuccess: () => refresh(),
    onError: (e) => toast.error(errorText(e)),
  });
  const bulk = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object }) => api<SlotTemplate[]>(`/workspace/slot-templates/${path}/`, { method: "POST", json: { field: field?.id, ...body } }),
    onSuccess: (rows) => {
      toast.success("Schedule updated");
      setGenerating(false);
      refresh(rows);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const byDay = DAYS.map((_, d) => (slots.data ?? []).filter((s) => s.weekday === d));

  return (
    <>
      <PageHeader
        title="Slot schedule"
        description="Make your own weekly slots — any start time and length, different for each day. Days without custom slots use automatic slots from your opening hours and the field's slot length."
        actions={
          canEdit &&
          field && (
            <Button onClick={() => setGenerating(true)}>
              <Sparkles /> Set up slots
            </Button>
          )
        }
      />
      {fields.isPending && <Skeleton className="h-64" />}
      {fields.data && fields.data.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2" role="radiogroup" aria-label="Field">
          {fields.data.map((f) => (
            <button
              key={f.id}
              type="button"
              role="radio"
              aria-checked={f.id === field?.id}
              onClick={() => setFieldId(f.id)}
              className={cn("rounded-full border px-3 py-1.5 text-sm font-medium", f.id === field?.id ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
            >
              {f.name}
            </button>
          ))}
        </div>
      )}
      {slots.isError && <ErrorState error={slots.error} onRetry={() => slots.refetch()} />}
      {field && slots.data && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
          {byDay.map((rows, d) => (
            <Card key={d} className="flex flex-col">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                  {DAYS_LONG[d]}
                  {rows.length === 0 ? (
                    <Badge tone="neutral">Automatic</Badge>
                  ) : (
                    <Badge tone="blue">{rows.filter((r) => r.is_active).length} slots</Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col gap-2">
                {rows.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    {field.slot_minutes}-minute slots through opening hours.
                  </p>
                )}
                {rows.map((s) => (
                  <div key={s.id} className={cn("rounded-lg border p-2 text-sm", !s.is_active && "opacity-50")}>
                    <div className="flex items-start justify-between gap-1">
                      <div>
                        <p className="font-medium tabular">
                          {fmtClock(s.start_time)}–{fmtClock(s.end_time)}
                        </p>
                        <p className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                          {s.category && <span className={cn("size-2 rounded-full", CATEGORY[s.category].dot)} />}
                          {s.category && `${CATEGORY[s.category].label} · `}
                          {s.minutes} min
                          {s.price && <span className="font-semibold text-foreground"> · {formatBDT(s.price)}</span>}
                        </p>
                      </div>
                      {canEdit && (
                        <div className="flex">
                          <Button size="icon" variant="ghost" className="size-7" aria-label="Edit slot" onClick={() => setEditing(s)}>
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button size="icon" variant="ghost" className="size-7" aria-label="Delete slot" onClick={() => window.confirm("Delete this slot?") && remove.mutate(s.id)}>
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      )}
                    </div>
                    {s.crosses_into && !s.price && (
                      <p className="mt-1 flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-300">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        Runs into {CATEGORY[s.crosses_into].label}; priced as {s.category && CATEGORY[s.category].label} (start time). Set a slot price to change it.
                      </p>
                    )}
                    {canEdit && (
                      <Checkbox
                        className="mt-1 text-xs"
                        label="Bookable"
                        checked={s.is_active}
                        onChange={(e) => patch.mutate({ id: s.id, body: { is_active: e.target.checked } })}
                      />
                    )}
                  </div>
                ))}
                {canEdit && (
                  <div className="mt-auto flex flex-wrap gap-1 pt-2">
                    <Button size="sm" variant="ghost" onClick={() => setEditing({ weekday: d, start_time: "18:00", end_time: "19:00", is_active: true, price: null })}>
                      <Plus /> Add
                    </Button>
                    {rows.length > 0 && (
                      <>
                        <CopyDay from={d} onCopy={(to) => bulk.mutate({ path: "copy", body: { from_weekday: d, to_weekdays: to } })} />
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => window.confirm(`Go back to automatic slots on ${DAYS_LONG[d]}?`) && bulk.mutate({ path: "clear", body: { weekdays: [d] } })}
                        >
                          <RotateCcw /> Auto
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {editing && field && <SlotDialog fieldId={field.id} slot={editing} onClose={() => setEditing(null)} onSaved={() => refresh()} />}
      {generating && field && <GenerateDialog fieldName={field.name} busy={bulk.isPending} onClose={() => setGenerating(false)} onSubmit={(body) => bulk.mutate({ path: "generate", body })} />}
    </>
  );
}

function CopyDay({ from, onCopy }: { from: number; onCopy: (to: number[]) => void }) {
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState<number[]>([]);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <Copy /> Copy
      </Button>
      {open && (
        <Dialog open onClose={() => setOpen(false)} title={`Copy ${DAYS_LONG[from]}'s slots`} description="The chosen days' slots are replaced.">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-3">
              {DAYS_LONG.map((name, d) =>
                d === from ? null : (
                  <Checkbox key={d} label={name} checked={to.includes(d)} onChange={(e) => setTo(e.target.checked ? [...to, d] : to.filter((x) => x !== d))} />
                ),
              )}
            </div>
            <Button
              disabled={to.length === 0}
              onClick={() => {
                onCopy(to);
                setOpen(false);
              }}
            >
              Copy to {to.length} day{to.length === 1 ? "" : "s"}
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function SlotDialog({ fieldId, slot, onClose, onSaved }: { fieldId: string; slot: Partial<SlotTemplate>; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    weekday: slot.weekday ?? 0,
    start_time: (slot.start_time ?? "18:00").slice(0, 5),
    end_time: (slot.end_time ?? "19:00").slice(0, 5),
    price: slot.price ?? "",
    is_active: slot.is_active ?? true,
  });
  const save = useMutation({
    mutationFn: () => {
      const json = { ...form, field: fieldId, price: form.price === "" ? null : form.price };
      return slot.id ? api(`/workspace/slot-templates/${slot.id}/`, { method: "PATCH", json }) : api("/workspace/slot-templates/", { method: "POST", json });
    },
    onSuccess: () => {
      toast.success("Slot saved");
      onSaved();
      onClose();
    },
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  return (
    <Dialog open onClose={onClose} title={slot.id ? "Edit slot" : `New slot on ${DAYS_LONG[form.weekday]}`} description="An end time earlier than the start means the slot ends after midnight.">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Starts" error={fields?.start_time}>
          {(id) => <Input id={id} type="time" step={900} required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />}
        </FormField>
        <FormField label="Ends" error={fields?.end_time}>
          {(id) => <Input id={id} type="time" step={900} required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />}
        </FormField>
        <FormField label="Slot price (optional)" hint="Whole-slot price. Empty = time-of-day / standard rate." error={fields?.price} className="sm:col-span-2">
          {(id) => <Input id={id} type="number" min={0} step="0.01" placeholder="Automatic" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />}
        </FormField>
        <Checkbox label="Bookable" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        {save.error && !fields && <p className="text-sm text-destructive sm:col-span-2">{errorText(save.error)}</p>}
        <Button type="submit" disabled={save.isPending} className="sm:col-span-2">
          Save slot
        </Button>
      </form>
    </Dialog>
  );
}

function GenerateDialog({ fieldName, busy, onClose, onSubmit }: { fieldName: string; busy: boolean; onClose: () => void; onSubmit: (body: object) => void }) {
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [form, setForm] = useState({ start: "06:00", end: "00:00", minutes: "90", price: "" });
  return (
    <Dialog open onClose={onClose} title={`Set up slots for ${fieldName}`} description="Creates back-to-back slots of one length. The chosen days' current slots are replaced.">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit({ weekdays: days, start: form.start, end: form.end, minutes: Number(form.minutes), price: form.price || null });
        }}
      >
        <div className="flex flex-wrap gap-3">
          {DAYS.map((name, d) => (
            <Checkbox key={d} label={name} checked={days.includes(d)} onChange={(e) => setDays(e.target.checked ? [...days, d] : days.filter((x) => x !== d))} />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="First slot starts">{(id) => <Input id={id} type="time" step={900} value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />}</FormField>
          <FormField label="Last slot ends" hint="Earlier than start = after midnight">
            {(id) => <Input id={id} type="time" step={900} value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />}
          </FormField>
          <FormField label="Slot length">
            {(id) => (
              <Select id={id} value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })}>
                {[30, 45, 60, 75, 90, 105, 120, 150, 180].map((m) => (
                  <option key={m} value={m}>
                    {m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}` : `${m} min`}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
        </div>
        <FormField label="Fixed price per slot (optional)" hint="Empty = priced by time of day / standard rate">
          {(id) => <Input id={id} type="number" min={0} step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />}
        </FormField>
        <Button type="submit" disabled={busy || days.length === 0}>
          {busy ? <Loader2 className="animate-spin" /> : <CalendarRange />} Create slots
        </Button>
      </form>
    </Dialog>
  );
}
