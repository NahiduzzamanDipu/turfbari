import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hourglass, Loader2, Send, TimerOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, FormField, Input, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { addDays, fmtDay, fmtRange, todayISO } from "@/lib/format";
import type { PublicBooking, SlotHold, PublicSlotState, TurfDetail, PublicAvailability } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";

const STATE_LABEL: Partial<Record<PublicSlotState, string>> = {
  held: "Someone is booking",
  requested: "Requested",
  booked: "Booked",
  unavailable: "Unavailable",
  past: "Past",
};

const tokenKey = (slug: string) => `turfbari-hold:${slug}`;
function readToken(slug: string) {
  try {
    return sessionStorage.getItem(tokenKey(slug));
  } catch {
    return null;
  }
}
function writeToken(slug: string, token: string | null) {
  try {
    if (token) sessionStorage.setItem(tokenKey(slug), token);
    else sessionStorage.removeItem(tokenKey(slug));
  } catch {
    /* private mode: the hold still works for this page view */
  }
}

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
const clock = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Dhaka" }).format(
    new Date(iso),
  );

/**
 * Public booking: selecting slots keeps them for this visitor for 10 minutes and shows them to
 * everyone else as "Someone is booking". Statuses refresh every few seconds.
 */
export function BookingPanel({ turf }: { turf: TurfDetail }) {
  const qc = useQueryClient();
  const [fieldId, setFieldId] = useState(turf.fields_list[0]?.id ?? "");
  const [day, setDay] = useState(todayISO());
  const [token, setToken] = useState<string | null>(() => readToken(turf.slug));
  const [form, setForm] = useState({ name: "", phone: "", email: "", team_name: "", notes: "", website: "" });
  const [done, setDone] = useState<PublicBooking | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(todayISO(), i)), []);

  const saveToken = (t: string | null) => {
    setToken(t);
    writeToken(turf.slug, t);
  };

  const slots = useQuery({
    queryKey: ["public", "availability", turf.slug, fieldId, day, token],
    queryFn: () =>
      api<PublicAvailability>(`/public/turfs/${turf.slug}/availability/?field=${fieldId}&date=${day}`, {
        headers: token ? { "X-Hold-Token": token } : {},
      }),
    enabled: Boolean(fieldId),
    refetchInterval: 5_000, // live: other players' selections and bookings show up within seconds
    staleTime: 0,
  });

  const list = slots.data?.slots ?? [];
  const myHold = slots.data?.my_hold ?? null;
  const cooldown = slots.data?.cooldown_until ?? null;
  const secondsLeft = useCountdown(myHold?.expires_at);
  const cooldownLeft = useCountdown(cooldown);

  // The server forgot our hold (it lapsed or was used): drop the stale token.
  useEffect(() => {
    if (slots.data && token && !myHold) {
      saveToken(null);
      if (cooldown) setNotice("Your 10 minutes ran out, so the slot was released for others.");
    }
    // The wait is over: drop the "time ran out" message.
    if (slots.data && !cooldown && notice?.startsWith("Your 10 minutes")) setNotice(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots.data]);

  // When the countdown hits zero, ask the server straight away.
  useEffect(() => {
    if (myHold && secondsLeft === 0) void slots.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secondsLeft === 0]);

  const heldHere = myHold && myHold.field === fieldId && myHold.start.slice(0, 10) === day ? myHold : null;
  const range = useMemo(() => {
    if (!heldHere) return null;
    const from = list.findIndex((s) => s.start.slice(0, 16) === heldHere.start.slice(0, 16));
    const to = list.findIndex((s) => s.end.slice(0, 16) === heldHere.end.slice(0, 16));
    return from >= 0 && to >= from ? { from, to } : null;
  }, [heldHere, list]);
  const chosen = range ? list.slice(range.from, range.to + 1) : [];
  const total = chosen.reduce((sum, s) => sum + Number(s.price ?? 0), 0);

  const refresh = () => qc.invalidateQueries({ queryKey: ["public", "availability", turf.slug] });

  const hold = useMutation({
    mutationFn: (r: { from: number; to: number }) =>
      api<SlotHold>(`/public/turfs/${turf.slug}/hold/`, {
        method: "POST",
        json: { field: fieldId, start: list[r.from]!.start, end: list[r.to]!.end, token: token ?? "" },
      }),
    onSuccess: (h) => {
      setNotice(null);
      saveToken(h.token);
      void refresh();
    },
    onError: (e) => {
      setNotice(e instanceof ApiError ? e.message : "Couldn't select that slot. Try again.");
      void refresh();
    },
  });

  const release = useMutation({
    mutationFn: () =>
      api<void>(`/public/turfs/${turf.slug}/hold/`, { method: "DELETE", headers: token ? { "X-Hold-Token": token } : {} }),
    onSettled: () => {
      saveToken(null);
      void refresh();
    },
  });

  const submit = useMutation({
    mutationFn: () =>
      api<PublicBooking>(`/public/turfs/${turf.slug}/book/`, {
        method: "POST",
        json: { field: fieldId, start: chosen[0]?.start, end: chosen.at(-1)?.end, hold_token: token ?? "", ...form },
      }),
    onSuccess: (b) => {
      setDone(b);
      saveToken(null);
      void refresh();
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
    if (range && i === range.to + 1) hold.mutate({ from: range.from, to: i });
    else hold.mutate({ from: i, to: i });
  };

  if (done) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Book a slot</CardTitle>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Book a slot</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
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
              onClick={() => setDay(d)}
              className={cn(
                "shrink-0 rounded-lg border px-3 py-2 text-center text-sm",
                d === day ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
              )}
            >
              {fmtDay(`${d}T12:00:00+06:00`)}
            </button>
          ))}
        </div>

        {cooldown && cooldownLeft > 0 ? (
          <p role="alert" className="flex items-start gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">
            <TimerOff className="mt-0.5 size-4 shrink-0" />
            <span>
              {notice ?? "Your last selection timed out without a booking request."} You can select a slot again at{" "}
              <span className="font-semibold">{clock(cooldown)}</span> ({mmss(cooldownLeft)}).
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
        {slots.data && list.length === 0 && <p className="text-sm text-muted-foreground">Closed on this day.</p>}
        {list.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground">
              Tap a free slot to hold it for 10 minutes; tap the next one to extend. Updates live.
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full border bg-background" /> Free</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-primary" /> Yours</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-amber-400" /> Someone is booking</span>
              <span className="flex items-center gap-1"><i className="size-2.5 rounded-full bg-sky-400" /> Requested / booked</span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
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
                      "rounded-lg border px-2 py-2 text-left text-sm transition",
                      state === "free" && "hover:border-primary",
                      state === "held" && "cursor-not-allowed border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
                      (state === "requested" || state === "booked") &&
                        "cursor-not-allowed border-sky-300 bg-sky-50 text-sky-900 dark:bg-sky-500/10 dark:text-sky-200",
                      (state === "past" || state === "unavailable") && "cursor-not-allowed bg-muted text-muted-foreground opacity-60",
                      selected && "border-primary bg-primary text-primary-foreground",
                      !clickable && state === "free" && "opacity-60",
                    )}
                  >
                    <span className="block font-medium">{fmtRange(s.start, s.end)}</span>
                    {selected ? (
                      <span className="text-xs opacity-90">Held for you</span>
                    ) : STATE_LABEL[state] ? (
                      <span className="text-xs">{STATE_LABEL[state]}</span>
                    ) : (
                      s.price && <span className="tabular text-xs opacity-80">{formatBDT(s.price)}</span>
                    )}
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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">
                <span className="font-semibold">{fmtRange(chosen[0]!.start, chosen.at(-1)!.end)}</span>
                {total > 0 && <> · <span className="tabular font-semibold">{formatBDT(total)}</span></>}
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={() => release.mutate()} disabled={busy}>
                Clear selection
              </Button>
            </div>
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
            <Button type="submit" size="lg" disabled={submit.isPending || secondsLeft === 0}>
              {submit.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Send booking request
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
