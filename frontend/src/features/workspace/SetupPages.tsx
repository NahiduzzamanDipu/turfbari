import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Crosshair, Download, Loader2, MapPinned, Pencil, Plus, Trash2, UserPlus } from "lucide-react";
import { Link } from "react-router";
import type * as React from "react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Badge,
  Checkbox,
  Dialog,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  Select,
  Table,
  Textarea,
} from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useAmenities, useLocations } from "@/features/public/shared";
import { api } from "@/lib/api";
import { SURFACE_LABEL, WEEKDAYS, WEEKDAYS_SHORT, fmtClock, weekdayLabel } from "@/lib/format";
import type { Field, Hours, Manager, PricingRule, TurfSettings } from "@/lib/types";
import { formatBDT } from "@/lib/utils";
import { errorText, useFields, useIsOwner } from "./hooks";
import { PicturesCard } from "./PicturesCard";
import { ThemeCard } from "./ThemeCard";

// ------------------------------------------------------------------ fields
const NEW_FIELD: Omit<Field, "id"> = {
  name: "",
  size: "5-a-side",
  surface: "artificial",
  is_indoor: false,
  has_lighting: true,
  is_active: true,
  sort_order: 0,
  slot_minutes: 60,
  default_hourly_rate: "1500.00",
};

export function FieldsPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const fields = useFields();
  const [editing, setEditing] = useState<(Omit<Field, "id"> & { id?: string }) | null>(null);

  const save = useMutation({
    mutationFn: (f: Omit<Field, "id"> & { id?: string }) =>
      f.id
        ? api<Field>(`/workspace/fields/${f.id}/`, { method: "PATCH", json: f })
        : api<Field>("/workspace/fields/", { method: "POST", json: f }),
    onSuccess: () => {
      toast.success("Field saved");
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/fields/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Field deleted");
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader
        title="Fields"
        description="The pitches customers can book. Inactive fields disappear from booking."
        actions={
          isOwner && (
            <Button onClick={() => setEditing({ ...NEW_FIELD, sort_order: (fields.data?.length ?? 0) + 1 })}>
              <Plus /> Add field
            </Button>
          )
        }
      />
      {fields.isPending && <Skeleton className="h-40" />}
      {fields.isError && <ErrorState error={fields.error} onRetry={() => fields.refetch()} />}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {fields.data?.map((f) => (
          <Card key={f.id}>
            <CardContent className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-lg font-semibold">{f.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {[f.size, SURFACE_LABEL[f.surface], f.is_indoor ? "Indoor" : "Outdoor", f.has_lighting && "Floodlit"].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <Badge tone={f.is_active ? "green" : "neutral"}>{f.is_active ? "Active" : "Inactive"}</Badge>
              </div>
              <p className="text-sm">
                <span className="tabular font-semibold">{formatBDT(f.default_hourly_rate)}</span>/hr standard ·{" "}
                {f.slot_minutes}-minute slots
              </p>
              {isOwner && (
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditing(f)}>
                    <Pencil /> Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => window.confirm(`Delete ${f.name}?`) && remove.mutate(f.id)}
                    aria-label={`Delete ${f.name}`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing?.id ? "Edit field" : "Add field"}>
        {editing && (
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(editing);
            }}
          >
            <FormField label="Name" className="sm:col-span-2">
              {(id) => <Input id={id} required value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />}
            </FormField>
            <FormField label="Size">
              {(id) => <Input id={id} placeholder="5-a-side" value={editing.size} onChange={(e) => setEditing({ ...editing, size: e.target.value })} />}
            </FormField>
            <FormField label="Surface">
              {(id) => (
                <Select id={id} value={editing.surface} onChange={(e) => setEditing({ ...editing, surface: e.target.value })}>
                  {Object.entries(SURFACE_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
            <FormField label="Standard hourly rate (৳)">
              {(id) => <Input id={id} type="number" min={0} step="0.01" required value={editing.default_hourly_rate} onChange={(e) => setEditing({ ...editing, default_hourly_rate: e.target.value })} />}
            </FormField>
            <FormField label="Slot length" hint="Shown to customers on the public booking page.">
              {(id) => (
                <Select id={id} value={editing.slot_minutes} onChange={(e) => setEditing({ ...editing, slot_minutes: Number(e.target.value) })}>
                  {[30, 45, 60, 90, 120].map((m) => (
                    <option key={m} value={m}>
                      {m} minutes
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Checkbox label="Indoor" checked={editing.is_indoor} onChange={(e) => setEditing({ ...editing, is_indoor: e.target.checked })} />
              <Checkbox label="Floodlights" checked={editing.has_lighting} onChange={(e) => setEditing({ ...editing, has_lighting: e.target.checked })} />
              <Checkbox label="Active (bookable)" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />
            </div>
            {save.error && <p className="text-sm text-destructive sm:col-span-2">{errorText(save.error)}</p>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                Save
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------ hours
const hhmm = (t: string) => t.slice(0, 5);

export function HoursPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const hours = useQuery({ queryKey: ["ws", "hours"], queryFn: () => api<Hours[]>("/workspace/hours/") });
  const [rows, setRows] = useState<Hours[]>([]);
  useEffect(() => {
    if (hours.data) setRows(hours.data);
  }, [hours.data]);

  const save = useMutation({
    mutationFn: () => api<Hours[]>("/workspace/hours/", { method: "PUT", json: rows }),
    onSuccess: (data) => {
      toast.success("Opening hours saved");
      qc.setQueryData(["ws", "hours"], data);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const update = (weekday: number, patch: Partial<Hours>) =>
    setRows((r) => r.map((h) => (h.weekday === weekday ? { ...h, ...patch } : h)));

  return (
    <>
      <PageHeader title="Opening hours" description="A closing time earlier than the opening time means you close after midnight." />
      {hours.isPending && <Skeleton className="h-64" />}
      {hours.isError && <ErrorState error={hours.error} onRetry={() => hours.refetch()} />}
      {rows.length > 0 && (
        <Card className="max-w-2xl">
          <CardContent className="flex flex-col gap-3">
            {rows.map((h) => (
              <div key={h.weekday} className="grid grid-cols-[6rem_1fr] items-center gap-3 sm:grid-cols-[7rem_1fr_1fr_auto]">
                <span className="font-medium">{WEEKDAYS[h.weekday]}</span>
                <Input type="time" aria-label={`${WEEKDAYS[h.weekday]} opens`} disabled={!isOwner || h.is_closed} value={hhmm(h.opens_at)} onChange={(e) => update(h.weekday, { opens_at: e.target.value })} className="col-start-2 sm:col-start-auto" />
                <Input type="time" aria-label={`${WEEKDAYS[h.weekday]} closes`} disabled={!isOwner || h.is_closed} value={hhmm(h.closes_at)} onChange={(e) => update(h.weekday, { closes_at: e.target.value })} className="col-start-2 sm:col-start-auto" />
                <Checkbox label="Closed" disabled={!isOwner} checked={h.is_closed} onChange={(e) => update(h.weekday, { is_closed: e.target.checked })} className="col-start-2 sm:col-start-auto" />
              </div>
            ))}
            {isOwner && (
              <div className="flex justify-end pt-2">
                <Button onClick={() => save.mutate()} disabled={save.isPending}>
                  {save.isPending && <Loader2 className="animate-spin" />} Save hours
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}

// ------------------------------------------------------------------ pricing
const NEW_RULE: Omit<PricingRule, "id" | "field_name"> = {
  field: null,
  label: "Peak hours",
  weekdays: [],
  date: null,
  start_time: "17:00",
  end_time: "23:00",
  hourly_rate: "2000.00",
  priority: 10,
  is_active: true,
};

export function PricingPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const fields = useFields();
  const rules = useQuery({ queryKey: ["ws", "pricing"], queryFn: () => api<PricingRule[]>("/workspace/pricing-rules/") });
  const [editing, setEditing] = useState<(Omit<PricingRule, "id" | "field_name"> & { id?: string }) | null>(null);

  const save = useMutation({
    mutationFn: (r: NonNullable<typeof editing>) =>
      r.id
        ? api(`/workspace/pricing-rules/${r.id}/`, { method: "PATCH", json: r })
        : api("/workspace/pricing-rules/", { method: "POST", json: r }),
    onSuccess: () => {
      toast.success("Price rule saved");
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/pricing-rules/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws"] }),
  });

  return (
    <>
      <PageHeader
        title="Pricing"
        description="Rules override a field's standard rate. A special date beats a field-specific rule, which beats higher priority. Bookings that cross a boundary are split and priced per part."
        actions={isOwner && <Button onClick={() => setEditing(NEW_RULE)}><Plus /> Add rule</Button>}
      />
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Standard rates</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4 text-sm">
          {fields.data?.map((f) => (
            <span key={f.id}>
              {f.name}: <strong className="tabular">{formatBDT(f.default_hourly_rate)}</strong>/hr
            </span>
          ))}
          <span className="text-muted-foreground">Change these on the Fields page.</span>
        </CardContent>
      </Card>
      {rules.isPending && <Skeleton className="h-40" />}
      {rules.isError && <ErrorState error={rules.error} onRetry={() => rules.refetch()} />}
      {rules.data?.length === 0 && <EmptyState title="No price rules yet">Every slot uses the field's standard rate.</EmptyState>}
      {rules.data && rules.data.length > 0 && (
        <Card>
          <CardContent className="p-2 sm:p-4">
            <Table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>When</th>
                  <th>Field</th>
                  <th className="text-right">Rate/hr</th>
                  <th>Priority</th>
                  {isOwner && <th />}
                </tr>
              </thead>
              <tbody>
                {rules.data.map((r) => (
                  <tr key={r.id} className={r.is_active ? "" : "opacity-50"}>
                    <td className="font-medium">
                      {r.label} {!r.is_active && <Badge>Off</Badge>}
                    </td>
                    <td>
                      {r.date ?? weekdayLabel(r.weekdays)}
                      <span className="block text-xs text-muted-foreground">
                        {fmtClock(r.start_time)} – {fmtClock(r.end_time)}
                      </span>
                    </td>
                    <td>{r.field_name ?? "All fields"}</td>
                    <td className="tabular text-right font-semibold">{formatBDT(r.hourly_rate)}</td>
                    <td className="tabular">{r.priority}</td>
                    {isOwner && (
                      <td className="whitespace-nowrap text-right">
                        <Button size="sm" variant="ghost" aria-label={`Edit ${r.label}`} onClick={() => setEditing({ ...r, start_time: hhmm(r.start_time), end_time: hhmm(r.end_time) })}>
                          <Pencil />
                        </Button>
                        <Button size="sm" variant="ghost" aria-label={`Delete ${r.label}`} onClick={() => window.confirm(`Delete "${r.label}"?`) && remove.mutate(r.id)}>
                          <Trash2 />
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing?.id ? "Edit price rule" : "Add price rule"}>
        {editing && (
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(editing);
            }}
          >
            <FormField label="Label" className="sm:col-span-2">
              {(id) => <Input id={id} required value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} />}
            </FormField>
            <FormField label="Applies to">
              {(id) => (
                <Select id={id} value={editing.field ?? ""} onChange={(e) => setEditing({ ...editing, field: e.target.value || null })}>
                  <option value="">All fields</option>
                  {fields.data?.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
            <FormField label="Hourly rate (৳)">
              {(id) => <Input id={id} type="number" min={0} step="0.01" required value={editing.hourly_rate} onChange={(e) => setEditing({ ...editing, hourly_rate: e.target.value })} />}
            </FormField>
            <FormField label="From">
              {(id) => <Input id={id} type="time" required value={editing.start_time} onChange={(e) => setEditing({ ...editing, start_time: e.target.value })} />}
            </FormField>
            <FormField label="Until" hint="Same as From = all day">
              {(id) => <Input id={id} type="time" required value={editing.end_time} onChange={(e) => setEditing({ ...editing, end_time: e.target.value })} />}
            </FormField>
            <fieldset className="sm:col-span-2">
              <legend className="mb-2 text-sm font-medium">Days (none selected = every day)</legend>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS_SHORT.map((d, i) => {
                  const on = editing.weekdays.includes(i);
                  return (
                    <button
                      key={d}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setEditing({ ...editing, weekdays: on ? editing.weekdays.filter((x) => x !== i) : [...editing.weekdays, i] })}
                      className={`rounded-full border px-3 py-1 text-sm ${on ? "border-primary bg-primary text-primary-foreground" : ""}`}
                    >
                      {d}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <FormField label="Special date (optional)" hint="e.g. Eid. Overrides the days above.">
              {(id) => <Input id={id} type="date" value={editing.date ?? ""} onChange={(e) => setEditing({ ...editing, date: e.target.value || null })} />}
            </FormField>
            <FormField label="Priority" hint="Higher wins when rules overlap.">
              {(id) => <Input id={id} type="number" value={editing.priority} onChange={(e) => setEditing({ ...editing, priority: Number(e.target.value) })} />}
            </FormField>
            <Checkbox label="Active" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />
            {save.error && <p className="text-sm text-destructive sm:col-span-2">{errorText(save.error)}</p>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                Save rule
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------ settings
const MAPS_LINK_HINT =
  "In Google Maps, open your turf, tap Share and copy the link. Full links fill the pin automatically.";

/** Google Maps link + map pin. The pin powers "near me" search; the link opens from the map icon. */
function MapLocationFields({
  form,
  setForm,
}: {
  form: TurfSettings;
  setForm: React.Dispatch<React.SetStateAction<TurfSettings | null>>;
}) {
  const [locating, setLocating] = useState(false);
  const update = (patch: Partial<TurfSettings>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const hasPin = Boolean(form.latitude && form.longitude);
  const preview = form.maps_url || (hasPin ? `https://www.google.com/maps/search/?api=1&query=${form.latitude},${form.longitude}` : "");

  const useCurrentLocation = () => {
    if (!("geolocation" in navigator)) {
      toast.error("This browser cannot share its location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        update({ latitude: pos.coords.latitude.toFixed(6), longitude: pos.coords.longitude.toFixed(6) });
        toast.success("Pin set to where you are now. Save settings to keep it.");
      },
      () => {
        setLocating(false);
        toast.error("Location permission was denied or unavailable.");
      },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  return (
    <>
      <FormField label="Google Maps link" hint={MAPS_LINK_HINT} className="sm:col-span-2">
        {(id) => (
          <Input
            id={id}
            type="url"
            placeholder="https://maps.app.goo.gl/..."
            value={form.maps_url}
            onChange={(e) => update({ maps_url: e.target.value })}
          />
        )}
      </FormField>
      <FormField label="Latitude">
        {(id) => (
          <Input id={id} inputMode="decimal" placeholder="23.8103" value={form.latitude ?? ""} onChange={(e) => update({ latitude: e.target.value.trim() || null })} />
        )}
      </FormField>
      <FormField label="Longitude">
        {(id) => (
          <Input id={id} inputMode="decimal" placeholder="90.4125" value={form.longitude ?? ""} onChange={(e) => update({ longitude: e.target.value.trim() || null })} />
        )}
      </FormField>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
        <Button type="button" variant="outline" size="sm" onClick={useCurrentLocation} disabled={locating}>
          {locating ? <Loader2 className="animate-spin" /> : <Crosshair />} Use my current location
        </Button>
        {preview && (
          <a href={preview} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
            <MapPinned className="size-4" /> Check on Google Maps
          </a>
        )}
        <p className="w-full text-xs text-muted-foreground">
          {hasPin ? "Players near you will see this turf first, with its distance." : "Add a pin so players nearby can find your turf."}
        </p>
      </div>
    </>
  );
}

export function SettingsPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const locations = useLocations();
  const amenities = useAmenities();
  const settings = useQuery({ queryKey: ["ws", "settings"], queryFn: () => api<TurfSettings>("/workspace/settings/") });
  const [form, setForm] = useState<TurfSettings | null>(null);
  // Load once: later refreshes (e.g. after a picture upload) must not wipe unsaved edits.
  useEffect(() => {
    if (settings.data) setForm((current) => current ?? settings.data);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () => api<TurfSettings>("/workspace/settings/", { method: "PATCH", json: form }),
    onSuccess: (data) => {
      toast.success("Settings saved");
      qc.setQueryData(["ws", "settings"], data);
      setForm(data);
      qc.invalidateQueries({ queryKey: ["ws", "dashboard"] });
      qc.invalidateQueries({ queryKey: ["auth"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));
  const areas = districts.find((d) => d.slug === form?.district)?.areas ?? [];
  const set = <K extends keyof TurfSettings>(key: K, value: TurfSettings[K]) => setForm((f) => (f ? { ...f, [key]: value } : f));
  const text = (key: keyof TurfSettings) => (e: { target: { value: string } }) => set(key, e.target.value as never);

  return (
    <>
      <PageHeader title="Settings" description="Your public profile and account." />
      {settings.isPending && <Skeleton className="h-64" />}
      {settings.isError && <ErrorState error={settings.error} onRetry={() => settings.refetch()} />}
      {form && (
        <form
          className="grid gap-6 xl:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <fieldset disabled={!isOwner} className="contents">
            <Card>
              <CardHeader>
                <CardTitle>Booking page &amp; QR code</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <Checkbox label="Publish my booking page (its link and QR code open for players)" checked={form.is_listed} onChange={(e) => set("is_listed", e.target.checked)} />
                <Checkbox label="Accept online booking requests" checked={form.public_booking_enabled} onChange={(e) => set("public_booking_enabled", e.target.checked)} />
                <Checkbox label="Show prices publicly" checked={form.show_pricing} onChange={(e) => set("show_pricing", e.target.checked)} />
                <BookingPageQR slug={form.slug} published={form.is_listed} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Location</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <FormField label="Turf name" className="sm:col-span-2">
                  {(id) => <Input id={id} required value={form.name} onChange={text("name")} />}
                </FormField>
                <FormField label="District">
                  {(id) => (
                    <Select id={id} value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value, area: null })}>
                      {districts.map((d) => (
                        <option key={d.slug} value={d.slug}>
                          {d.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Area">
                  {(id) => (
                    <Select id={id} value={form.area ?? ""} onChange={(e) => set("area", e.target.value || null)}>
                      <option value="">—</option>
                      {areas.map((a) => (
                        <option key={a.slug} value={a.slug}>
                          {a.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Address" className="sm:col-span-2">
                  {(id) => <Input id={id} required value={form.address} onChange={text("address")} />}
                </FormField>
                <MapLocationFields form={form} setForm={setForm} />
                <FormField label="Type">
                  {(id) => (
                    <Select id={id} value={form.turf_type} onChange={text("turf_type")}>
                      <option value="outdoor">Outdoor</option>
                      <option value="indoor">Indoor</option>
                      <option value="rooftop">Rooftop</option>
                    </Select>
                  )}
                </FormField>
                <FormField label="Surface">
                  {(id) => (
                    <Select id={id} value={form.surface} onChange={text("surface")}>
                      {Object.entries(SURFACE_LABEL).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Profile</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <FormField label="Short description" hint="Shown on the turf card (200 characters)." className="sm:col-span-2">
                  {(id) => <Input id={id} maxLength={200} value={form.short_description} onChange={text("short_description")} />}
                </FormField>
                <FormField label="About" className="sm:col-span-2">
                  {(id) => <Textarea id={id} rows={4} value={form.description} onChange={text("description")} />}
                </FormField>
                <FormField label="Public phone">
                  {(id) => <Input id={id} type="tel" value={form.public_phone} onChange={text("public_phone")} />}
                </FormField>
                <FormField label="Public email">
                  {(id) => <Input id={id} type="email" value={form.public_email} onChange={text("public_email")} />}
                </FormField>
                <FormField label="Payment methods" className="sm:col-span-2">
                  {(id) => <Input id={id} placeholder="Cash, bKash, Nagad" value={form.payment_methods_text} onChange={text("payment_methods_text")} />}
                </FormField>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Policies & amenities</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <FormField label="Booking instructions">
                  {(id) => <Textarea id={id} rows={2} value={form.booking_instructions} onChange={text("booking_instructions")} />}
                </FormField>
                <FormField label="Cancellation policy">
                  {(id) => <Textarea id={id} rows={2} value={form.cancellation_policy} onChange={text("cancellation_policy")} />}
                </FormField>
                <fieldset>
                  <legend className="mb-2 text-sm font-medium">Amenities</legend>
                  <div className="grid grid-cols-2 gap-2">
                    {amenities.data?.map((a) => (
                      <Checkbox
                        key={a.slug}
                        label={a.name}
                        checked={form.amenities.includes(a.slug)}
                        onChange={(e) =>
                          set("amenities", e.target.checked ? [...form.amenities, a.slug] : form.amenities.filter((s) => s !== a.slug))
                        }
                      />
                    ))}
                  </div>
                </fieldset>
              </CardContent>
            </Card>
            <ThemeCard form={form} update={(patch) => setForm((f) => (f ? { ...f, ...patch } : f))} />
          </fieldset>
          {isOwner && (
            <div className="sticky bottom-4 flex justify-end xl:col-span-2">
              <Button type="submit" size="lg" disabled={save.isPending} className="shadow-lg">
                {save.isPending && <Loader2 className="animate-spin" />} Save settings
              </Button>
            </div>
          )}
        </form>
      )}
      {settings.data && (
        <div className="mt-6 grid xl:grid-cols-2">
          <PicturesCard settings={settings.data} canEdit={isOwner} />
        </div>
      )}
      <p className="mt-6 text-sm text-muted-foreground">
        To change your password, open{" "}
        <Link to="/workspace/account" className="text-primary hover:underline">
          My account
        </Link>
        .
      </p>
    </>
  );
}

// ------------------------------------------------------------------ managers
export function ManagersPage() {
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["ws", "managers"], queryFn: () => api<Manager[]>("/workspace/managers/") });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", phone: "" });
  const [created, setCreated] = useState<Manager | null>(null);

  const add = useMutation({
    mutationFn: () => api<Manager>("/workspace/managers/", { method: "POST", json: form }),
    onSuccess: (m) => {
      setOpen(false);
      setForm({ email: "", full_name: "", phone: "" });
      setCreated(m);
      qc.invalidateQueries({ queryKey: ["ws", "managers"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/managers/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Access removed");
      qc.invalidateQueries({ queryKey: ["ws", "managers"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader
        title="Team"
        description="Managers can take bookings, record payments and manage customers. Only you can change prices, settings, expenses and reports."
        actions={<Button onClick={() => setOpen(true)}><UserPlus /> Add manager</Button>}
      />
      {team.isPending && <Skeleton className="h-40" />}
      {team.isError && <ErrorState error={team.error} onRetry={() => team.refetch()} />}
      {team.data && (
        <Card>
          <CardContent className="p-2 sm:p-4">
            <Table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {team.data.map((m) => (
                  <tr key={m.id}>
                    <td className="font-medium">
                      {m.full_name || "—"}
                      <span className="block text-xs text-muted-foreground">{m.phone}</span>
                    </td>
                    <td>{m.email}</td>
                    <td>
                      <Badge tone={m.role === "owner" ? "lime" : "blue"} className="capitalize">
                        {m.role}
                      </Badge>
                    </td>
                    <td className="text-right">
                      {m.role === "manager" && (
                        <Button size="sm" variant="ghost" onClick={() => window.confirm(`Remove ${m.email}?`) && remove.mutate(m.id)}>
                          Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Add manager">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <FormField label="Full name">
            {(id) => <Input id={id} required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}
          </FormField>
          <FormField label="Email" hint="They sign in with this email.">
            {(id) => <Input id={id} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
          </FormField>
          <FormField label="Phone (optional)">
            {(id) => <Input id={id} type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}
          </FormField>
          {add.error && <p className="text-sm text-destructive">{errorText(add.error)}</p>}
          <Button type="submit" disabled={add.isPending}>
            Add manager
          </Button>
        </form>
      </Dialog>
      <Dialog open={created !== null} onClose={() => setCreated(null)} title="Manager added" description="Share the login securely. The password is shown only once.">
        {created && (
          <div className="flex flex-col gap-3 text-sm">
            <p>
              Email: <strong>{created.email}</strong>
            </p>
            {created.temporary_password ? (
              <div className="flex items-center gap-2 rounded-md bg-secondary p-3">
                <code className="flex-1 font-mono text-base">{created.temporary_password}</code>
                <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(created.temporary_password ?? "").then(() => toast.success("Copied"))}>
                  <Copy /> Copy
                </Button>
              </div>
            ) : (
              <p className="text-muted-foreground">They already have a TurfBari account and can sign in with their existing password.</p>
            )}
            <Button onClick={() => setCreated(null)}>Done</Button>
          </div>
        )}
      </Dialog>
    </>
  );
}

/** The turf's own booking link and QR code. Owners and managers can download it to print or share. */
export function BookingPageQR({ slug, published }: { slug: string; published: boolean }) {
  const url = `${window.location.origin}/turfs/${slug}`;
  return (
    <div className="flex flex-col gap-4 rounded-lg border p-3 sm:flex-row sm:items-center">
      <img src="/api/workspace/booking-page/qr.svg" alt="Booking page QR code" className="size-32 shrink-0 rounded bg-white p-1" />
      <div className="min-w-0 space-y-2 text-sm">
        <a className="block truncate font-medium text-primary hover:underline" href={url} target="_blank" rel="noreferrer">
          {url.replace(/^https?:\/\//, "")}
        </a>
        <p className="text-muted-foreground">
          {published
            ? "Print the QR at your counter or share the link on Facebook — players book straight from it."
            : "Publish the page above first; until then the link and QR show “not found” to players."}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <a href="/api/workspace/booking-page/qr.png?download=1">
              <Download /> PNG
            </a>
          </Button>
          <Button asChild size="sm" variant="outline">
            <a href="/api/workspace/booking-page/qr.svg?download=1">
              <Download /> SVG (print)
            </a>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => navigator.clipboard.writeText(url).then(() => toast.success("Link copied"), () => toast.error("Couldn't copy the link"))}
          >
            <Copy /> Copy link
          </Button>
        </div>
      </div>
    </div>
  );
}
