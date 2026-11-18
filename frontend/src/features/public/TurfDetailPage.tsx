import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Loader2,
  Mail,
  MapPin,
  Phone,
  QrCode,
  Send,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Dialog, ErrorState, FormField, Input, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import {
  SURFACE_LABEL,
  TURF_TYPE_LABEL,
  WEEKDAYS,
  addDays,
  fmtClock,
  fmtDay,
  fmtRange,
  todayISO,
  weekdayLabel,
} from "@/lib/format";
import type { PublicBooking, Slot, TurfDetail } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { themeStyle } from "@/lib/themes";
import { PhotoGallery } from "./PhotoGallery";
import { GoogleMapsPin, TurfArt } from "./shared";

export function TurfDetailPage() {
  const { slug = "" } = useParams();
  const turf = useQuery({
    queryKey: ["public", "turf", slug],
    queryFn: () => api<TurfDetail>(`/public/turfs/${slug}/`),
  });
  const [showQR, setShowQR] = useState(false);

  if (turf.isPending) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8">
        <Skeleton className="h-56 rounded-2xl" />
        <Skeleton className="mt-6 h-8 w-1/2" />
      </div>
    );
  }
  if (turf.isError) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16">
        {turf.error instanceof ApiError && turf.error.status === 404 ? (
          <div className="text-center">
            <h1 className="text-2xl font-semibold">Turf not found</h1>
            <p className="mt-2 text-muted-foreground">It may have been unlisted.</p>
            <Button asChild className="mt-6">
              <Link to="/explore">Browse turfs</Link>
            </Button>
          </div>
        ) : (
          <ErrorState error={turf.error} onRetry={() => turf.refetch()} />
        )}
      </div>
    );
  }

  const t = turf.data;
  const location = [t.area?.name, t.district.name].filter(Boolean).join(", ");

  return (
    <div className="mx-auto max-w-6xl px-4 py-6" style={themeStyle(t.theme)}>
      <Link to="/explore" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> All turfs
      </Link>
      <div className="relative mt-3 overflow-hidden rounded-2xl">
        {t.photos[0] ? (
          <img src={t.photos[0].url} alt="" className="h-56 w-full object-cover sm:h-80" />
        ) : (
          <TurfArt seed={t.slug} className="h-48 sm:h-64" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        {t.map_link && (
          <a
            href={t.map_link}
            target="_blank"
            rel="noreferrer"
            className="absolute right-4 top-4 inline-flex items-center gap-2 rounded-full bg-white/95 px-3 py-2 text-sm font-semibold text-neutral-900 shadow transition hover:scale-105"
          >
            <GoogleMapsPin className="size-5" /> Directions
          </a>
        )}
        <div className="absolute inset-x-0 bottom-0 p-5 text-white sm:p-8">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {t.is_featured && <Badge tone="lime">Featured</Badge>}
            <Badge className="bg-white/20 text-white">{TURF_TYPE_LABEL[t.turf_type]}</Badge>
            <Badge className="bg-white/20 text-white">{SURFACE_LABEL[t.surface]}</Badge>
          </div>
          <div className="flex items-end gap-4">
            {t.profile_image_url && (
              <img
                src={t.profile_image_url}
                alt={`${t.name} logo`}
                className="size-16 shrink-0 rounded-full border-4 border-white/90 object-cover shadow-lg sm:size-24"
              />
            )}
            <h1 className="font-display text-4xl font-extrabold uppercase leading-none sm:text-5xl">{t.name}</h1>
          </div>
          <p className="mt-2 flex items-center gap-1 text-sm opacity-90">
            <MapPin className="size-4" /> {t.address} · {location}
          </p>
        </div>
      </div>

      {t.photos.length > 1 && (
        <div className="mt-4">
          <PhotoGallery photos={t.photos} turfName={t.name} />
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="flex flex-col gap-6">
          {t.public_booking_enabled ? (
            <BookingPanel turf={t} />
          ) : (
            <Card>
              <CardContent>
                <p className="font-semibold">Online requests are off for this turf.</p>
                <p className="text-sm text-muted-foreground">Call {t.public_phone || "the turf"} to book.</p>
              </CardContent>
            </Card>
          )}

          {(t.description || t.short_description) && (
            <section>
              <h2 className="mb-2 text-lg font-semibold">About</h2>
              <p className="whitespace-pre-line text-muted-foreground">{t.description || t.short_description}</p>
            </section>
          )}

          {t.amenities.length > 0 && (
            <section>
              <h2 className="mb-2 text-lg font-semibold">Amenities</h2>
              <ul className="flex flex-wrap gap-2">
                {t.amenities.map((a) => (
                  <li key={a} className="rounded-full border bg-card px-3 py-1 text-sm">
                    {a}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="mb-2 text-lg font-semibold">Fields</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {t.fields_list.map((f) => (
                <div key={f.id} className="glass rounded-lg p-3">
                  <p className="font-medium">{f.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {[f.size, SURFACE_LABEL[f.surface], f.is_indoor ? "Indoor" : "Outdoor", f.has_lighting && "Floodlit"]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {(t.booking_instructions || t.cancellation_policy) && (
            <section className="grid gap-4 sm:grid-cols-2">
              {t.booking_instructions && (
                <div>
                  <h2 className="mb-1 font-semibold">How booking works</h2>
                  <p className="whitespace-pre-line text-sm text-muted-foreground">{t.booking_instructions}</p>
                </div>
              )}
              {t.cancellation_policy && (
                <div>
                  <h2 className="mb-1 font-semibold">Cancellation policy</h2>
                  <p className="whitespace-pre-line text-sm text-muted-foreground">{t.cancellation_policy}</p>
                </div>
              )}
            </section>
          )}
        </div>

        <aside className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Contact</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              {t.public_phone && (
                <a href={`tel:${t.public_phone}`} className="flex items-center gap-2 hover:text-primary">
                  <Phone className="size-4" /> {t.public_phone}
                </a>
              )}
              {t.public_email && (
                <a href={`mailto:${t.public_email}`} className="flex items-center gap-2 break-all hover:text-primary">
                  <Mail className="size-4 shrink-0" /> {t.public_email}
                </a>
              )}
              {t.map_link && (
                <a href={t.map_link} target="_blank" rel="noreferrer" className="flex items-center gap-2 hover:text-primary">
                  <MapPin className="size-4" /> Open in Maps
                </a>
              )}
              {t.payment_methods_text && <p className="text-muted-foreground">Pay by: {t.payment_methods_text}</p>}
              <Button variant="outline" size="sm" className="mt-2" onClick={() => setShowQR(true)}>
                <QrCode /> Show QR code
              </Button>
            </CardContent>
          </Card>

          {(t.base_rates.length > 0 || t.pricing.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle>Prices per hour</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {t.base_rates.map((r) => (
                  <div key={r.field} className="flex justify-between">
                    <span>{r.field} (standard)</span>
                    <span className="tabular font-semibold">{formatBDT(r.hourly_rate)}</span>
                  </div>
                ))}
                {t.pricing.map((p) => (
                  <div key={`${p.label}-${p.start_time}-${p.field_name}`} className="flex justify-between gap-2 border-t pt-2">
                    <span>
                      {p.label}
                      {p.field_name && ` · ${p.field_name}`}
                      <span className="block text-xs text-muted-foreground">
                        {p.date ?? weekdayLabel(p.weekdays)}, {fmtClock(p.start_time)}–{fmtClock(p.end_time)}
                      </span>
                    </span>
                    <span className="tabular font-semibold">{formatBDT(p.hourly_rate)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="size-4" /> Opening hours
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                {t.hours.map((h) => (
                  <div key={h.weekday} className="contents">
                    <dt className="text-muted-foreground">{WEEKDAYS[h.weekday]}</dt>
                    <dd className="text-right">{h.is_closed ? "Closed" : `${fmtClock(h.opens_at)} – ${fmtClock(h.closes_at)}`}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </aside>
      </div>

      <Dialog open={showQR} onClose={() => setShowQR(false)} title={`${t.name} QR code`} description="Scan to open this booking page.">
        <div className="flex flex-col items-center gap-4">
          <img src={`/api/public/turfs/${t.slug}/qr.svg`} alt={`QR code for ${t.name}`} className="size-64 rounded-lg bg-white p-2" />
          <Button asChild variant="outline">
            <a href={`/api/public/turfs/${t.slug}/qr.svg`} download={`${t.slug}-qr.svg`}>
              Download SVG
            </a>
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

function BookingPanel({ turf }: { turf: TurfDetail }) {
  const [fieldId, setFieldId] = useState(turf.fields_list[0]?.id ?? "");
  const [day, setDay] = useState(todayISO());
  const [range, setRange] = useState<{ from: number; to: number } | null>(null);
  const [form, setForm] = useState({ name: "", phone: "", email: "", team_name: "", notes: "", website: "" });
  const [done, setDone] = useState<PublicBooking | null>(null);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(todayISO(), i)), []);

  const slots = useQuery({
    queryKey: ["public", "availability", turf.slug, fieldId, day],
    queryFn: () => api<{ slots: Slot[] }>(`/public/turfs/${turf.slug}/availability/?field=${fieldId}&date=${day}`),
    enabled: Boolean(fieldId),
    refetchInterval: 10_000, // slots taken by other players disappear without a reload
  });

  const list = slots.data?.slots ?? [];
  const chosen = range ? list.slice(range.from, range.to + 1) : [];
  const total = chosen.reduce((sum, s) => sum + Number(s.price ?? 0), 0);

  const submit = useMutation({
    mutationFn: () =>
      api<PublicBooking>(`/public/turfs/${turf.slug}/book/`, {
        method: "POST",
        json: { field: fieldId, start: chosen[0]?.start, end: chosen.at(-1)?.end, ...form },
      }),
    onSuccess: (b) => {
      setDone(b);
      setRange(null);
      slots.refetch();
    },
  });
  const fieldErrors = submit.error instanceof ApiError ? submit.error.fields : null;

  const pick = (i: number) => {
    const slot = list[i];
    if (!slot?.available) return;
    if (range && i === range.to + 1) setRange({ from: range.from, to: i });
    else if (range && i >= range.from && i <= range.to) setRange(null);
    else setRange({ from: i, to: i });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Book a slot</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {done ? (
          <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
            <CheckCircle2 className="size-12 text-primary" />
            <p className="text-lg font-semibold">Request sent!</p>
            <p className="text-sm text-muted-foreground">
              {done.field}, {fmtDay(done.start)} · {fmtRange(done.start, done.end)}
              {done.total && <> · {formatBDT(done.total)}</>}
            </p>
            <p className="text-sm">
              Your reference: <span className="font-mono text-base font-bold">{done.reference}</span>
            </p>
            <p className="max-w-sm text-sm text-muted-foreground">
              The turf will call you to confirm. Track it any time on the{" "}
              <Link to={`/booking-status?reference=${done.reference}`} className="font-semibold text-primary hover:underline">
                booking status page
              </Link>
              .
            </p>
            <Button variant="outline" onClick={() => setDone(null)}>
              Book another slot
            </Button>
          </div>
        ) : (
          <>
            {turf.fields_list.length > 1 && (
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Field">
                {turf.fields_list.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    role="radio"
                    aria-checked={f.id === fieldId}
                    onClick={() => {
                      setFieldId(f.id);
                      setRange(null);
                    }}
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-sm font-medium",
                      f.id === fieldId ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
                    )}
                  >
                    {f.name} {f.size && <span className="opacity-75">· {f.size}</span>}
                  </button>
                ))}
              </div>
            )}
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="radiogroup" aria-label="Date">
              {days.map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={d === day}
                  onClick={() => {
                    setDay(d);
                    setRange(null);
                  }}
                  className={cn(
                    "shrink-0 rounded-lg border px-3 py-2 text-center text-sm",
                    d === day ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
                  )}
                >
                  {fmtDay(`${d}T12:00:00+06:00`)}
                </button>
              ))}
            </div>

            {slots.isPending && <Skeleton className="h-32" />}
            {slots.isError && <ErrorState error={slots.error} onRetry={() => slots.refetch()} />}
            {slots.data && list.length === 0 && <p className="text-sm text-muted-foreground">Closed on this day.</p>}
            {list.length > 0 && (
              <>
                <p className="text-xs text-muted-foreground">
                  Tap a free slot; tap the next one to extend your booking.
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                  {list.map((s, i) => {
                    const selected = range !== null && i >= range.from && i <= range.to;
                    return (
                      <button
                        key={s.start}
                        type="button"
                        disabled={!s.available}
                        aria-pressed={selected}
                        onClick={() => pick(i)}
                        className={cn(
                          "rounded-lg border px-2 py-2 text-left text-sm transition",
                          s.available ? "hover:border-primary" : "cursor-not-allowed bg-muted text-muted-foreground line-through opacity-60",
                          selected && "border-primary bg-primary text-primary-foreground",
                        )}
                      >
                        <span className="block font-medium">{fmtRange(s.start, s.end)}</span>
                        {s.price && <span className="tabular text-xs opacity-80">{formatBDT(s.price)}</span>}
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            {chosen.length > 0 && (
              <form
                className="mt-2 flex flex-col gap-3 border-t pt-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit.mutate();
                }}
              >
                <p className="text-sm">
                  <span className="font-semibold">{fmtRange(chosen[0]!.start, chosen.at(-1)!.end)}</span>
                  {total > 0 && <> · <span className="tabular font-semibold">{formatBDT(total)}</span></>}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField label="Your name" error={fieldErrors?.name}>
                    {(id) => <Input id={id} required autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
                  </FormField>
                  <FormField label="Mobile number" error={fieldErrors?.phone} hint="We'll call this number to confirm.">
                    {(id) => <Input id={id} required type="tel" inputMode="tel" autoComplete="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}
                  </FormField>
                  <FormField label="Email (optional)" error={fieldErrors?.email}>
                    {(id) => <Input id={id} type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
                  </FormField>
                  <FormField label="Team name (optional)">
                    {(id) => <Input id={id} value={form.team_name} onChange={(e) => setForm({ ...form, team_name: e.target.value })} />}
                  </FormField>
                </div>
                <FormField label="Notes (optional)">
                  {(id) => <Textarea id={id} rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}
                </FormField>
                {/* Honeypot: hidden from people, filled by bots. */}
                <input
                  type="text"
                  name="website"
                  tabIndex={-1}
                  autoComplete="off"
                  aria-hidden
                  className="hidden"
                  value={form.website}
                  onChange={(e) => setForm({ ...form, website: e.target.value })}
                />
                {submit.error && (
                  <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {fieldErrors?.start?.[0] ?? fieldErrors?.non_field_errors?.[0] ?? submit.error.message}
                  </p>
                )}
                <Button type="submit" size="lg" disabled={submit.isPending}>
                  {submit.isPending ? <Loader2 className="animate-spin" /> : <Send />}
                  Send booking request
                </Button>
              </form>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
