import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, Hourglass, Loader2, Send, TimerOff } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { LegalAcceptBox } from "@/components/legal/Legal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, FormField, Input, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { YouTubeDialog, YouTubeIcon } from "@/components/content/YouTube";
import { usePublicYoutubeVideo } from "./usePublicYoutubeVideo";
import { addDays, fmtDay, fmtRange, todayISO } from "@/lib/format";
import {
  clearDraft,
  loadDraft,
  loadSubmitted,
  newIdempotencyKey,
  saveDraft,
  saveSubmitted,
  type SubmittedBooking,
  visitorId,
} from "@/lib/visitor";
import type { PublicBooking, SlotHold, PublicSlotState, TurfDetail, PublicAvailability } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n";

const STATE_LABEL: Partial<Record<PublicSlotState, string>> = {
  held: "Someone is booking",
  requested: "Requested",
  booked: "Booked",
  unavailable: "Unavailable",
  past: "Past",
};

/** Seconds left until an ISO time, ticking every second. */
function useCountdown(until: string | null | undefined) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!until) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [until]);
  return until ? Math.max(0, Math.round((new Date(until).getTime() - now) / 1000)) : 0;
}

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const clock = (iso: string, language: "en" | "bn") =>
  new Intl.DateTimeFormat(language === "bn" ? "bn-BD" : "en-BD", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Dhaka" }).format(
    new Date(iso),
  );

/**
 * Public booking: selecting slots keeps them for this visitor for 10 minutes and shows them to
 * everyone else as "Someone is booking". Statuses refresh every few seconds.
 */
export function BookingPanel({ turf, demo = false }: { turf: TurfDetail; demo?: boolean }) {
  const { t, language, formatDate, formatMoney } = useLanguage();
  const youtube = usePublicYoutubeVideo("booking");
  const youtubeVideoId = youtube.data?.enabled ? youtube.data.video_id : null;
  const qc = useQueryClient();
  const qcDraft = useMemo(() => loadDraft(turf.slug), [turf.slug]);
  const validDay = (d?: string) => (d && d >= todayISO() ? d : todayISO());
  const [fieldId, setFieldId] = useState(
    turf.fields_list.some((f) => f.id === qcDraft?.fieldId) ? qcDraft!.fieldId : (turf.fields_list[0]?.id ?? ""),
  );
  const [day, setDay] = useState(validDay(qcDraft?.day));
  const [token, setToken] = useState<string | null>(qcDraft?.token ?? null);
  const [agree, setAgree] = useState(false);
  const [showVideo, setShowVideo] = useState(false);
  const [submitted, setSubmitted] = useState<SubmittedBooking | null>(() => loadSubmitted(turf.slug));
  const visitor = useMemo(() => visitorId(), []);
  const visitorHeaders = useMemo(() => ({ "X-Visitor-Id": visitor }), [visitor]);
  const [form, setForm] = useState({ name: "", phone: "", email: "", team_name: "", notes: "", website: "" });
  const [pay, setPay] = useState({ payment_amount: "", bkash_sender: "", trx_id: "" });
  const [done, setDone] = useState<PublicBooking | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(todayISO(), i)), []);
  const basePath = demo ? "/public/demo" : `/public/turfs/${turf.slug}`;

  useEffect(() => {
    if (!demo || !done?.reference) return;
    const id = window.setInterval(() => {
      void api<PublicBooking>(`/public/demo/bookings/status/${done.reference}/`).then(setDone).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(id);
  }, [demo, done?.reference]);

  const saveToken = (t: string | null) => {
    setToken(t);
    if (t) saveDraft(turf.slug, { token: t, fieldId, day });
    else saveDraft(turf.slug, { token: null, idempotencyKey: newIdempotencyKey() });
  };
  // Remember where the visitor is looking, so a reload comes back to the same field and day.
  useEffect(() => {
    saveDraft(turf.slug, { fieldId, day });
  }, [turf.slug, fieldId, day]);

  const tokenRef = useRef(token);
  tokenRef.current = token;
  const slotsKey = ["public", "availability", turf.slug, fieldId, day] as const;
  const slots = useQuery({
    queryKey: slotsKey,
    queryFn: () =>
      api<PublicAvailability>(`${basePath}/availability/?field=${fieldId}&date=${day}`, {
        headers: tokenRef.current ? { "X-Hold-Token": tokenRef.current, ...visitorHeaders } : visitorHeaders,
      }),
    placeholderData: keepPreviousData,
    enabled: Boolean(fieldId),
    refetchInterval: 8_000, // live: others' selections and bookings show up within seconds (paused when hidden)
    staleTime: 0,
  });

  const list = slots.data?.slots ?? [];
  const myHold = slots.data?.my_hold ?? null;
  const cooldown = slots.data?.cooldown_until ?? null;
  const secondsLeft = useCountdown(myHold?.expires_at);
  const cooldownLeft = useCountdown(cooldown);

  // The server still holds a slot for this browser (reload / new tab): adopt it and show it.
  const [adopted, setAdopted] = useState(false);
  useEffect(() => {
    const h = slots.data?.my_hold;
    if (!h || adopted) return;
    setAdopted(true);
    if (h.token !== token) saveToken(h.token);
    const holdDay = h.start.slice(0, 10);
    if (h.field !== fieldId) setFieldId(h.field);
    if (holdDay !== day) setDay(holdDay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots.data?.my_hold?.token]);

  // The server forgot our hold (it lapsed or was used): drop the stale token.
  useEffect(() => {
    if (slots.data && token && !myHold) {
      saveToken(null);
      if (cooldown) setNotice("Your 10 minutes ran out, so the slot was released for others.");
      else setNotice("Your earlier selection has expired. Please choose a slot again.");
    }
    // The wait is over: drop the "time ran out" message.
    if (slots.data && !cooldown && notice?.startsWith("Your 10 minutes")) setNotice(null);
    if (slots.data && myHold && notice?.startsWith("Your earlier selection")) setNotice(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots.data]);

  // When the countdown hits zero, ask the server straight away.
  useEffect(() => {
    if (myHold && secondsLeft === 0) void slots.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secondsLeft === 0]);

  const heldHere = myHold && myHold.field === fieldId && myHold.start.slice(0, 10) === day ? myHold : null;
  // Optimistic: the tapped range shows as selected at once; the server confirms (or we revert).
  const [pending, setPending] = useState<{ from: number; to: number } | null>(null);
  const serverRange = useMemo(() => {
    if (!heldHere) return null;
    const from = list.findIndex((s) => s.start.slice(0, 16) === heldHere.start.slice(0, 16));
    const to = list.findIndex((s) => s.end.slice(0, 16) === heldHere.end.slice(0, 16));
    return from >= 0 && to >= from ? { from, to } : null;
  }, [heldHere, list]);
  const range = pending ?? serverRange;
  const chosen = range ? list.slice(range.from, range.to + 1) : [];
  const total = chosen.reduce((sum, s) => sum + Number(s.price ?? 0), 0);
  const payment = turf.payment;
  const advanceSetting = Math.max(Number(payment.advance_amount), Number(payment.min_advance));
  // The least to send now (the server checks the same rule): the advance, or the whole price if lower.
  const advance = total > 0 ? Math.min(total, advanceSetting) : advanceSetting;

  const refresh = () => qc.invalidateQueries({ queryKey: ["public", "availability", turf.slug] });

  const hold = useMutation({
    mutationFn: (r: { from: number; to: number }) =>
      api<SlotHold>(`${basePath}/hold/`, {
        method: "POST",
        headers: visitorHeaders,
        json: { field: fieldId, start: list[r.from]!.start, end: list[r.to]!.end, token: token ?? "" },
      }),
    onMutate: (r) => setPending(r),
    onSuccess: (h) => {
      setNotice(null);
      saveToken(h.token);
      // Patch the list we already have instead of reloading it: this hold is now "yours".
      qc.setQueryData<PublicAvailability>(slotsKey, (old) =>
        old
          ? {
              ...old,
              my_hold: h,
              slots: old.slots.map((s) => {
                const mine = s.start >= h.start && s.end <= h.end && h.field === fieldId;
                if (mine) return { ...s, state: "yours", available: true };
                return s.state === "yours" ? { ...s, state: "free", available: true } : s;
              }),
            }
          : old,
      );
      setPending(null);
    },
    onError: (e) => {
      setPending(null); // revert the optimistic selection
      setNotice(e instanceof ApiError ? e.message : "Couldn't select that slot. Try again.");
      void refresh();
    },
  });

  const release = useMutation({
    mutationFn: () =>
      api<void>(`${basePath}/hold/`, { method: "DELETE", headers: token ? { "X-Hold-Token": token, ...visitorHeaders } : visitorHeaders }),
    onMutate: () => setPending({ from: -1, to: -2 }), // shows nothing selected right away
    onSettled: () => {
      saveToken(null);
      setPending(null);
      void refresh();
    },
  });

  const submit = useMutation({
    mutationFn: () =>
      api<PublicBooking>(`${basePath}/book/`, {
        method: "POST",
        headers: { ...visitorHeaders, "Idempotency-Key": loadDraft(turf.slug)?.idempotencyKey ?? newIdempotencyKey() },
        json: {
          agree_terms: agree,
          accepted_versions: turf.legal.map((d) => d.version_id),
          field: fieldId,
          start: chosen[0]?.start,
          end: chosen.at(-1)?.end,
          hold_token: token ?? "",
          ...form,
          payment_amount: pay.payment_amount || String(advance),
          bkash_sender: pay.bkash_sender || form.phone,
          trx_id: pay.trx_id,
        },
      }),
    onSuccess: (b) => {
      setDone(b);
      setPay({ payment_amount: "", bkash_sender: "", trx_id: "" });
      setAgree(false);
      const record = { reference: b.reference, start: b.start, at: Date.now() };
      saveSubmitted(turf.slug, record);
      setSubmitted(record);
      setToken(null);
      clearDraft(turf.slug);
      void refresh();
    },
    onError: (e) => {
      // The terms changed while the form was open: fetch the new versions and ask again.
      if (e instanceof ApiError && e.fields?.code?.[0] === "legal_versions_changed") {
        setAgree(false);
        void qc.invalidateQueries({ queryKey: ["public", "turf", turf.slug] });
      }
    },
  });
  const fieldErrors = submit.error instanceof ApiError ? submit.error.fields : null;
  const busy = hold.isPending || release.isPending;

  const pick = (i: number) => {
    const slot = list[i];
    if (!slot || busy) return;
    if (cooldown && cooldownLeft > 0) return;
    if (range && i >= range.from && i <= range.to) {
      // Tapping a selected slot: shrink from that end, or let go of everything.
      if (range.from === range.to) release.mutate();
      else if (i === range.to) hold.mutate({ from: range.from, to: i - 1 });
      else if (i === range.from) hold.mutate({ from: i + 1, to: range.to });
      else release.mutate();
      return;
    }
    if (!slot.available) return;
    // Extend only with the very next slot in time (custom schedules can have gaps).
    if (range && i === range.to + 1 && list[range.to]!.end === slot.start) hold.mutate({ from: range.from, to: i });
    else hold.mutate({ from: i, to: i });
  };

  const header = (
    <CardHeader className="gap-2 sm:gap-1.5">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <CardTitle className="text-lg sm:text-base">
          {t("Book a slot")} <span className="font-normal text-muted-foreground">· বুক করুন</span>
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
        {turf.legal.length > 0 && (
          <Link
            to={turf.legal.find((d) => d.scope === "sector")?.url ?? "/legal/terms"}
            className="inline-flex min-h-10 items-center rounded-full border px-2.5 py-1 text-[10px] font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground sm:min-h-0 sm:px-3 sm:py-1.5 sm:text-xs"
          >
            {t("Terms & Conditions")}
          </Link>
        )}
        {youtubeVideoId && (
          <button
            type="button"
            onClick={() => setShowVideo(true)}
            className="inline-flex min-h-10 items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition hover:bg-secondary sm:min-h-0 sm:gap-1.5 sm:px-3 sm:py-1.5 sm:text-sm"
          >
            <YouTubeIcon className="h-4 w-auto" />
            <span lang="bn">বুকিং করার নিয়ম</span>
          </button>
        )}
        </div>
      </div>
    </CardHeader>
  );
  const video =
    showVideo && youtubeVideoId ? (
      <YouTubeDialog videoId={youtubeVideoId} title={youtube.data?.title || t("How to book")} onClose={() => setShowVideo(false)} />
    ) : null;

  if (done) {
    return (
      <Card>
        {header}
        {video}
        <CardContent>
          <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
            <CheckCircle2 className="size-12 text-primary" />
            <p className="text-lg font-semibold">বুকিং অনুরোধ পাঠানো হয়েছে</p>
            {done.message_bn && (
              <p lang="bn" className="max-w-md rounded-lg bg-primary/10 px-4 py-3 text-sm leading-relaxed">
                {done.message_bn}
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              {done.field}, {fmtDay(done.start)} · {fmtRange(done.start, done.end)}
              {done.total && <> · {formatMoney(done.total)}</>}
            </p>
            {done.payment && (
              <p className="text-sm text-muted-foreground">
                bKash {formatMoney(done.payment.amount)} · TrxID <span className="font-mono">{done.payment.trx_id}</span>
              </p>
            )}
            <p className="text-sm">
              Booking ID: <span className="font-mono text-base font-bold">{done.reference}</span>
            </p>
            <p className="max-w-sm text-sm text-muted-foreground">
              {demo ? "Your simulated payment is waiting for the Demo Owner to review it. Its status will refresh automatically." : <>Not confirmed yet — the turf checks the payment first. Track it on the{" "}
              <Link to={`/booking-status?reference=${done.reference}`} className="font-semibold text-primary hover:underline">booking status page</Link>.</>}
            </p>
            {demo && <Button asChild variant="outline"><Link to="/demo-booking?mode=owner">Open Demo Owner Dashboard</Link></Button>}
            <Button variant="outline" onClick={() => setDone(null)}>
              Book another slot
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
    <Card>
      {header}
      {video}
      <CardContent className={cn("flex flex-col gap-3 sm:gap-4", chosen.length > 0 && payment.accepts_online && "pb-24 sm:pb-6")}>
        {submitted && !done && (
          <p role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
            <span>
              You already sent a booking request (<span className="font-mono font-semibold">{submitted.reference}</span>).{" "}
              <Link className="font-semibold text-primary hover:underline" to={`/booking-status?reference=${submitted.reference}`}>
                Check its status
              </Link>
            </span>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => {
                saveSubmitted(turf.slug, null);
                setSubmitted(null);
              }}
            >
              Dismiss
            </button>
          </p>
        )}
        {turf.fields_list.length > 1 && (
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Field">
            {turf.fields_list.map((f) => (
              <button
                key={f.id}
                type="button"
                role="radio"
                aria-checked={f.id === fieldId}
                onClick={() => setFieldId(f.id)}
                className={cn(
                  "min-h-10 rounded-full border px-2.5 py-1 text-xs font-medium sm:px-3 sm:py-1.5 sm:text-sm",
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
              onClick={() => setDay(d)}
              className={cn(
                "min-h-[40px] shrink-0 rounded-md border px-2 py-1 text-center text-[10px] sm:rounded-lg sm:px-3 sm:py-2 sm:text-sm",
                d === day ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
              )}
            >
              {formatDate(`${d}T12:00:00+06:00`, { weekday: "short", day: "numeric", month: "short" })}
            </button>
          ))}
        </div>

        {cooldown && cooldownLeft > 0 ? (
          <p role="alert" className="flex items-start gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">
            <TimerOff className="mt-0.5 size-4 shrink-0" />
            <span>
              {notice ?? "Your last selection timed out without a booking request."} You can select a slot again at{" "}
              <span className="font-semibold">{clock(cooldown, language)}</span> ({mmss(cooldownLeft)}).
            </span>
          </p>
        ) : (
          notice && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {notice}
            </p>
          )
        )}

        {myHold && secondsLeft > 0 && (
          <p className="flex items-center gap-2 rounded-md bg-primary/10 px-3 py-2 text-sm" role="status">
            <Hourglass className="size-4 text-primary" />
            <span>
              {heldHere ? "These slots are" : `Your slot on ${fmtDay(myHold.start)} is`} held for you for{" "}
              <span className="tabular font-semibold">{mmss(secondsLeft)}</span>. Send the request before time runs out.
            </span>
          </p>
        )}

        {slots.isPending && <Skeleton className="h-32" />}
        {slots.isError && <ErrorState error={slots.error} onRetry={() => slots.refetch()} />}
        {slots.data && list.length === 0 && <p className="text-sm text-muted-foreground">{t("Closed on this day.")}</p>}
        {list.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground">
              Tap a free slot to hold it for 10 minutes; tap the next one to extend. Updates live.
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full border bg-background" /> {t("Free")}</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-primary" /> {t("Yours")}</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-amber-400" /> {t("Someone is booking")}</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-sky-400" /> {t("Requested / booked")}</span>
            </div>
            <div className="grid grid-cols-2 gap-1 min-[381px]:grid-cols-3 sm:grid-cols-3 sm:gap-2 md:grid-cols-4">
              {list.map((s, i) => {
                const state: PublicSlotState = s.state ?? (s.available ? "free" : "booked");
                const selected = range !== null && i >= range.from && i <= range.to;
                const clickable = selected || (s.available && !(cooldown && cooldownLeft > 0));
                return (
                  <button
                    key={s.start}
                    type="button"
                    disabled={!clickable || busy}
                    aria-pressed={selected}
                    onClick={() => pick(i)}
                    className={cn(
                      "min-h-[44px] rounded-md border px-1.5 py-1 text-left text-xs leading-tight transition sm:rounded-lg sm:px-2 sm:py-2 sm:text-sm",
                      state === "free" && "hover:border-primary",
                      state === "held" && "cursor-not-allowed border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
                      (state === "requested" || state === "booked") &&
                        "cursor-not-allowed border-sky-300 bg-sky-50 text-sky-900 dark:bg-sky-500/10 dark:text-sky-200",
                      (state === "past" || state === "unavailable") && "cursor-not-allowed bg-muted text-muted-foreground opacity-60",
                      selected && "border-primary bg-primary text-primary-foreground",
                      !clickable && state === "free" && "opacity-60",
                    )}
                  >
                    <span className="flex items-center gap-1 font-medium">
                      {fmtRange(s.start, s.end)}
                      {selected && hold.isPending && <Loader2 className="size-3 animate-spin" aria-label="Reserving" />}
                    </span>
                    {selected ? (
                      <span className="text-[10px] opacity-90 sm:text-xs">Held for you</span>
                    ) : STATE_LABEL[state] ? (
                      <span className="text-[10px] leading-tight sm:text-xs">{t(STATE_LABEL[state]!)}</span>
                    ) : (
                      s.price && <span className="tabular text-[10px] opacity-80 sm:text-xs">{formatMoney(s.price)}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {chosen.length > 0 && !payment.accepts_online && (
          <p className="rounded-md border px-3 py-3 text-sm">
            This turf isn't taking online bookings right now.
            {turf.public_phone && (
              <>
                {" "}
                Call{" "}
                <a className="font-semibold text-primary hover:underline" href={`tel:${turf.public_phone}`}>
                  {turf.public_phone}
                </a>{" "}
                to book.
              </>
            )}
          </p>
        )}

        {chosen.length > 0 && payment.accepts_online && (
          <form
            id="public-booking-form"
            className="mt-1 flex flex-col gap-2.5 border-t pt-3 sm:mt-2 sm:gap-3 sm:pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              submit.mutate();
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">
                <span className="font-semibold">{fmtRange(chosen[0]!.start, chosen.at(-1)!.end)}</span>
                {total > 0 && <> · <span className="tabular font-semibold">{formatMoney(total)}</span></>}
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={() => release.mutate()} disabled={busy}>
                {t("Clear selection")}
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label={t("Your name")} error={fieldErrors?.name}>
                {(id) => <Input id={id} required autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
              </FormField>
              <FormField label={t("Mobile number")} error={fieldErrors?.phone} hint={t("The confirmation SMS comes to this number.")}>
                {(id) => <Input id={id} required type="tel" inputMode="tel" autoComplete="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}
              </FormField>
              <FormField label={t("Email (optional)")} error={fieldErrors?.email}>
                {(id) => <Input id={id} type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
              </FormField>
              <FormField label={t("Team name (optional)")}>
                {(id) => <Input id={id} value={form.team_name} onChange={(e) => setForm({ ...form, team_name: e.target.value })} />}
              </FormField>
            </div>
            <p className="text-xs text-muted-foreground" lang="bn">
              একজন গ্রাহক প্রতিদিন সর্বোচ্চ {turf.max_slots_per_customer}টি স্লট বুক করতে পারবেন (সব টার্ফ মিলিয়ে)।
            </p>
            <FormField label={t("Notes (optional)")}>
              {(id) => <Textarea id={id} rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}
            </FormField>
            <BkashBox number={payment.bkash_number ?? ""} total={total} advance={advance} holdMinutes={payment.hold_minutes} demoMode={demo} />
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField label={demo ? "Simulated payment amount (BDT)" : "Amount sent (৳)"} error={fieldErrors?.payment_amount} hint={`At least ${formatBDT(advance)}`}>
                {(id) => (
                  <Input
                    id={id}
                    required
                    type="number"
                    inputMode="decimal"
                    min={advance}
                    max={total > 0 ? total : undefined}
                    step="0.01"
                    placeholder={String(advance)}
                    value={pay.payment_amount}
                    onChange={(e) => setPay({ ...pay, payment_amount: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label={demo ? "Sample sender mobile number" : "bKash number you sent from"} error={fieldErrors?.bkash_sender}>
                {(id) => (
                  <Input
                    id={id}
                    type="tel"
                    inputMode="tel"
                    placeholder={form.phone || "01XXXXXXXXX"}
                    value={pay.bkash_sender}
                    onChange={(e) => setPay({ ...pay, bkash_sender: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label={demo ? "Simulated transaction reference" : "Transaction ID (TrxID)"} error={fieldErrors?.trx_id} hint={demo ? "Use a sample like SIM-9C7A6B5D; never enter a real transaction ID." : "From the bKash SMS"}>
                {(id) => (
                  <Input
                    id={id}
                    required
                    autoCapitalize="characters"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={demo ? "SIM-9C7A6B5D" : "e.g. 9C7A6B5D4E"}
                    className="font-mono uppercase"
                    value={pay.trx_id}
                    onChange={(e) => setPay({ ...pay, trx_id: e.target.value.toUpperCase().replace(/\s/g, "") })}
                  />
                )}
              </FormField>
            </div>
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
            <LegalAcceptBox
              id="agree-terms"
              docs={turf.legal}
              checked={agree}
              onChange={setAgree}
              intro="আমি এই বুকিংয়ের শর্তাবলী, বুকিং নিয়মাবলী ও রিফান্ড/বাতিলকরণ নীতি পড়েছি এবং সম্মত হয়েছি।"
              error={fieldErrors?.agree_terms?.[0]}
            />
            {submit.error && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {(fieldErrors?.code?.[0] === "booking_limit" ? fieldErrors.phone?.[0] : undefined) ??
                  fieldErrors?.start?.[0] ??
                  fieldErrors?.non_field_errors?.[0] ??
                  (fieldErrors ? "Please fix the highlighted fields." : submit.error.message)}
              </p>
            )}
            <Button type="submit" size="lg" disabled={submit.isPending || secondsLeft === 0 || (turf.legal.length > 0 && !agree)}>
              {submit.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Submit payment &amp; request booking
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
    {chosen.length > 0 && payment.accepts_online && (
      <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 px-3 pt-2 pb-[calc(.5rem+env(safe-area-inset-bottom))] shadow-lg backdrop-blur sm:hidden">
        <div className="mx-auto flex max-w-xl items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-xs text-muted-foreground">{fmtRange(chosen[0]!.start, chosen.at(-1)!.end)}</p>
            <p className="tabular font-semibold">{formatMoney(total)}</p>
          </div>
          <Button type="button" onClick={() => document.getElementById("public-booking-form")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" })}>
            {t("Continue")}
          </Button>
        </div>
      </div>
    )}
    </>
  );
}

/** How to pay: bKash "Send Money" to the turf's number, then type the TrxID from the bKash SMS. */
function BkashBox({ number, total, advance, holdMinutes, demoMode = false }: { number: string; total: number; advance: number; holdMinutes: number; demoMode?: boolean }) {
  const [copied, setCopied] = useState(false);
  const hours = holdMinutes >= 60 ? `${Math.round(holdMinutes / 6) / 10} hour${holdMinutes === 60 ? "" : "s"}` : `${holdMinutes} minutes`;
  return (
    <section aria-labelledby="bkash-title" className="rounded-lg border border-[#e2136e]/30 bg-[#e2136e]/5 p-2.5 sm:rounded-xl sm:border-2 sm:p-4">
      <h3 id="bkash-title" className="flex items-center gap-2 font-semibold">
        <span className="rounded bg-[#e2136e] px-1.5 py-0.5 text-xs font-bold text-white">bKash</span>
        {demoMode ? "Simulate advance payment" : "Pay the advance to book"}
      </h3>
      {demoMode ? <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950">Demo Mode — No Real Payment. Do not send money. Enter sample payment details below to experience the verification flow.</p> : <>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 sm:mt-3 sm:gap-2">
        <span className="text-sm text-muted-foreground">Send Money to</span>
        <span className="tabular font-mono text-base font-bold tracking-wide sm:text-xl">{number}</span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            navigator.clipboard.writeText(number).then(
              () => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 2000);
              },
              () => undefined,
            )
          }
        >
          <Copy /> {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-1.5 text-xs sm:mt-3 sm:gap-2 sm:text-sm">
        {total > 0 && (
          <div>
            <dt className="text-muted-foreground">Slot price</dt>
            <dd className="tabular font-semibold">{formatBDT(total)}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted-foreground">Advance now</dt>
          <dd className="tabular font-semibold text-[#c2105e] dark:text-pink-300">{formatBDT(advance)}+</dd>
        </div>
        {total > 0 && (
          <div>
            <dt className="text-muted-foreground">Pay at the turf</dt>
            <dd className="tabular font-semibold">{formatBDT(Math.max(total - advance, 0))}</dd>
          </div>
        )}
      </dl>
      </>}
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
        <li>Open the bKash app and choose <strong className="text-foreground">Send Money</strong> (not Payment or Cash Out).</li>
        <li>Send at least {formatBDT(advance)} to {number}.</li>
        <li>Copy the <strong className="text-foreground">TrxID</strong> from the bKash confirmation SMS and enter it below.</li>
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">
        The turf checks your payment and confirms by SMS. Your slot is kept for {hours} while they check. It is not confirmed until then.
      </p>
    </section>
  );
}
