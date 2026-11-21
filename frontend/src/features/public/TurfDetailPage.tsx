import { useQuery } from "@tanstack/react-query";
import {
  Clock,
  Mail,
  MapPin,
  Phone,
  QrCode,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Dialog, ErrorState } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import {
  SURFACE_LABEL,
  TURF_TYPE_LABEL,
  WEEKDAYS,
  fmtClock,
  weekdayLabel,
} from "@/lib/format";
import type { TurfDetail } from "@/lib/types";
import { formatBDT } from "@/lib/utils";
import { themeProps } from "@/lib/themes";
import { BookingPanel } from "./BookingPanel";
import { PhotoGallery } from "./PhotoGallery";
import { GoogleMapsPin, TurfArt } from "./shared";

const CATEGORY_BN: Record<string, string> = { morning: "সকাল", evening: "বিকাল", night: "রাত", midnight: "মধ্যরাত" };

export function TurfDetailPage({ demo = false }: { demo?: boolean }) {
  const { slug = "" } = useParams();
  const turfSlug = demo ? "turfbari-demo-arena" : slug;
  const turf = useQuery({
    queryKey: ["public", "turf", turfSlug],
    queryFn: () => api<TurfDetail>(demo ? "/public/demo/turf/" : `/public/turfs/${turfSlug}/`),
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
            <p className="mt-2 text-muted-foreground">Check the link or QR code you used, or ask the turf for its booking page.</p>
            <Button asChild className="mt-6">
              <Link to="/booking-status">Check a booking</Link>
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
    <div {...themeProps(t.theme)} className="min-h-full">
      <div className="mx-auto max-w-6xl px-[var(--page-gutter)] py-4 sm:px-4 sm:py-6">
      {demo && <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950"><span><strong>DEMO MODE</strong> · Use sample details only. No real booking, payment, or SMS is created.</span><Link to="/demo-booking?mode=owner" className="font-semibold underline underline-offset-2">Open connected owner dashboard</Link></div>}
      <div className="relative overflow-hidden rounded-2xl">
        {t.photos[0] ? (
          <img src={t.photos[0].url} alt="" className="h-56 w-full object-cover sm:h-80" />
        ) : (
          <TurfArt seed={t.slug} className="h-48 sm:h-64" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        <div className="absolute right-4 top-4 flex gap-2">
        {t.map_link && (
          <a
            href={t.map_link}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full bg-white/95 px-3 py-2 text-sm font-semibold text-neutral-900 shadow transition hover:scale-105"
          >
            <GoogleMapsPin className="size-5" /> Directions
          </a>
        )}
        </div>
        <div className="absolute inset-x-0 bottom-0 p-3 text-white sm:p-8">
          <div className="mb-1.5 flex flex-wrap gap-1 sm:mb-2 sm:gap-1.5">
            {t.is_featured && <Badge tone="lime">Featured</Badge>}
            <Badge className="bg-white/20 text-white">{TURF_TYPE_LABEL[t.turf_type]}</Badge>
            <Badge className="bg-white/20 text-white">{SURFACE_LABEL[t.surface]}</Badge>
          </div>
          <div className="flex min-w-0 items-end gap-2 sm:gap-4">
            {t.profile_image_url && (
              <img
                src={t.profile_image_url}
                alt={`${t.name} logo`}
                className="size-12 shrink-0 rounded-full border-2 border-white/90 object-cover shadow-lg sm:size-24 sm:border-4"
              />
            )}
            <h1 className="min-w-0 font-display text-xl font-extrabold uppercase leading-tight sm:text-5xl">{t.name}</h1>
          </div>
          <p className="mt-1 flex min-w-0 items-start gap-1 text-xs opacity-90 sm:mt-2 sm:items-center sm:text-sm">
            <MapPin className="mt-0.5 size-3.5 shrink-0 sm:mt-0 sm:size-4" /> <span>{t.address} · {location}</span>
          </p>
        </div>
      </div>

      {t.photos.length > 1 && (
        <div className="mt-4">
          <PhotoGallery photos={t.photos} turfName={t.name} />
        </div>
      )}

      <div className="mt-3 space-y-3 sm:mt-6 sm:space-y-6">
        <Card>
          <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs sm:gap-4 sm:text-sm">
            <span className="font-semibold">Contact</span>
            {t.public_phone && <a href={`tel:${t.public_phone}`} className="flex items-center gap-1.5 hover:text-primary"><Phone className="size-3.5" /> {t.public_phone}</a>}
            {t.public_email && <a href={`mailto:${t.public_email}`} className="flex items-center gap-1.5 break-all hover:text-primary"><Mail className="size-3.5 shrink-0" /> {t.public_email}</a>}
            {t.map_link && <a href={t.map_link} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 hover:text-primary"><MapPin className="size-3.5" /> Open in Maps</a>}
            {t.payment_methods_text && <span className="text-muted-foreground">Pay by: {t.payment_methods_text}</span>}
            <Button variant="outline" size="sm" className="ml-auto" onClick={() => setShowQR(true)}><QrCode /> Show QR</Button>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3 xl:grid-cols-3">
          {(t.description || t.short_description) && (
            <Card className="sm:col-span-2 xl:col-span-3">
              <CardHeader><CardTitle>About</CardTitle></CardHeader>
              <CardContent className="pt-2 text-sm leading-relaxed text-muted-foreground"><p className="whitespace-pre-line">{t.description || t.short_description}</p></CardContent>
            </Card>
          )}

          {t.amenities.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Amenities</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap gap-1.5 pt-2">
                {t.amenities.map((a) => <span key={a} className="rounded-full border bg-card px-2 py-1 text-xs">{a}</span>)}
              </CardContent>
            </Card>
          )}

          {t.fields_list.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Fields</CardTitle></CardHeader>
              <CardContent className="grid gap-1.5 pt-2">
                {t.fields_list.map((f) => (
                  <div key={f.id} className="rounded-md border px-2 py-1.5">
                    <p className="text-sm font-medium">{f.name}</p>
                    <p className="text-xs text-muted-foreground">{[f.size, SURFACE_LABEL[f.surface], f.is_indoor ? "Indoor" : "Outdoor", f.has_lighting && "Floodlit"].filter(Boolean).join(" · ")}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {t.price_categories.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Prices per hour</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-1.5 pt-2 text-sm">
                {t.price_categories.map((c) => (
                  <div key={c.key} className="rounded-md border px-2 py-1.5">
                    <p className="text-xs font-semibold">{c.label} <span className="font-normal text-muted-foreground">{CATEGORY_BN[c.key]}</span></p>
                    <p className="text-[10px] text-muted-foreground">{fmtClock(`${c.start}:00`)}–{fmtClock(`${c.end}:00`)}</p>
                    <p className="tabular text-sm font-bold">{formatBDT(c.hourly_rate)}</p>
                  </div>
                ))}
                {t.pricing.some((p) => p.date) && <p className="col-span-2 text-xs text-muted-foreground">Special prices apply on some dates; the slot list shows the exact price.</p>}
              </CardContent>
            </Card>
          )}

          {t.price_categories.length === 0 && (t.base_rates.length > 0 || t.pricing.length > 0) && (
            <Card>
              <CardHeader><CardTitle>Prices per hour</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-1.5 pt-2 text-xs">
                {t.base_rates.map((r) => <div key={r.field} className="flex justify-between gap-2"><span>{r.field} (standard)</span><span className="tabular font-semibold">{formatBDT(r.hourly_rate)}</span></div>)}
                {t.pricing.map((p) => <div key={`${p.label}-${p.start_time}-${p.field_name}`} className="flex justify-between gap-2 border-t pt-1.5"><span className="min-w-0">{p.label}{p.field_name && ` · ${p.field_name}`}<span className="block text-[10px] text-muted-foreground">{p.date ?? weekdayLabel(p.weekdays)}, {fmtClock(p.start_time)}–{fmtClock(p.end_time)}</span></span><span className="tabular shrink-0 font-semibold">{formatBDT(p.hourly_rate)}</span></div>)}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Clock className="size-3.5" /> Opening hours</CardTitle></CardHeader>
            <CardContent className="pt-2">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                {t.hours.map((h) => <div key={h.weekday} className="contents"><dt className="text-muted-foreground">{WEEKDAYS[h.weekday]}</dt><dd className="text-right">{h.is_closed ? "Closed" : `${fmtClock(h.opens_at)} – ${fmtClock(h.closes_at)}`}</dd></div>)}
              </dl>
            </CardContent>
          </Card>

          {(t.booking_instructions || t.cancellation_policy) && (
            <Card className="sm:col-span-2 xl:col-span-3">
              <CardHeader><CardTitle>Booking information</CardTitle></CardHeader>
              <CardContent className="grid gap-2 pt-2 sm:grid-cols-2 sm:gap-3">
                {t.booking_instructions && <div><h3 className="mb-1 text-sm font-semibold">How booking works</h3><p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{t.booking_instructions}</p></div>}
                {t.cancellation_policy && <div><h3 className="mb-1 text-sm font-semibold">Cancellation policy</h3><p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{t.cancellation_policy}</p></div>}
              </CardContent>
            </Card>
          )}
        </div>

        {t.public_booking_enabled ? <BookingPanel turf={t} demo={demo} /> : (
          <Card><CardContent className="py-3"><p className="text-sm font-semibold">Online requests are off for this turf.</p><p className="text-xs text-muted-foreground">Call {t.public_phone || "the turf"} to book.</p></CardContent></Card>
        )}
      </div>

      <Dialog open={showQR} onClose={() => setShowQR(false)} title={`${t.name} QR code`} description="Scan to open this booking page.">
        <div className="flex flex-col items-center gap-4">
          <img src={demo ? "/api/public/demo/qr.svg" : `/api/public/turfs/${t.slug}/qr.svg`} alt={`QR code for ${t.name}`} className="size-64 rounded-lg bg-white p-2" />
          <Button asChild variant="outline">
            <a href={demo ? "/api/public/demo/qr.svg" : `/api/public/turfs/${t.slug}/qr.svg`} download={`${t.slug}-qr.svg`}>
              Download SVG
            </a>
          </Button>
        </div>
      </Dialog>
    </div>
    </div>
  );
}
