import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Activity, ArrowRight, BadgeCheck, CalendarDays, ChartNoAxesCombined, Clock3, ExternalLink, Eye, MessageSquareText, QrCode, RefreshCw, Search, SlidersHorizontal, Users, Wallet } from "lucide-react";
import { Badge, FormField, Input } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatBDT } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import { demoApi } from "./demoApi";
import { TurfDetailPage } from "@/features/public/TurfDetailPage";

type DemoSlot = { id: string; label: string; start_time: string; end_time: string; category: string; price: string; enabled: boolean; booked: boolean };
type DemoBooking = { id: string; reference: string; customer_name: string; customer_phone: string; date: string; slot_id: string; start_time: string; end_time: string; price: string; payment_amount: string; sender_phone: string; transaction_reference: string; payment_status: string; rejection_reason: string; note: string; status: "pending" | "confirmed" | "rejected" | "cancelled"; created_at: string; reviewed_at: string | null };
type DemoData = { id: string; name: string; owner_name: string; location: string; reset_count: number; last_reset_at: string | null; slots: DemoSlot[]; bookings: DemoBooking[]; customers: { id: string; name: string; phone: string }[]; activity: { action: string; summary: string; created_at: string }[]; sms_messages: { kind: string; recipient: string; body: string; status: string; created_at: string; reference: string }[]; summary: { today: number; pending: number; confirmed: number; customers: number; enabled_slots: number } };

function useDemoData() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      await demoApi("/owner-access/", { method: "POST", json: {} });
      setData(await demoApi<DemoData>("/owner/workspace/"));
    } catch (cause) {
      if (cause instanceof Error) setError(cause.message);
    } finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, []);
  return { data, error, loading, refresh, setData };
}

export function DemoExperiencePage() {
  const [params] = useSearchParams();
  return params.get("mode") === "owner" ? <DemoAccountPage /> : <TurfDetailPage demo />;
}

export function DemoBookingPage() {
  const { data, error, loading, refresh } = useDemoData();
  const [date, setDate] = useState(() => localDatePlus(1));
  const [slotId, setSlotId] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [result, setResult] = useState<DemoBooking | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const slots = useMemo(() => (data?.slots ?? []).map((slot) => ({ ...slot, booked: data?.bookings.some((booking) => booking.date === date && booking.slot_id === slot.id && ["pending", "confirmed"].includes(booking.status)) ?? false })), [data, date]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(""); setBusy(true);
    try {
      const booking = await demoApi<DemoBooking>("/book/", { method: "POST", json: { date, slot_id: slotId, name, phone } });
      setResult(booking); await refresh();
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Could not submit demo booking."); }
    finally { setBusy(false); }
  };
  if (loading) return <PageLoading />;
  if (error) return <DemoError message={error} retry={() => void refresh()} />;
  if (result) return <main className="mx-auto max-w-3xl px-4 py-10 sm:py-16">
    <DemoBanner ownerLink />
    <div className="mt-6 rounded-2xl border bg-card p-6 shadow-sm sm:p-9">
      <div className="mb-5 grid size-12 place-items-center rounded-full bg-emerald-100 text-emerald-800"><BadgeCheck /></div>
      <p className="text-sm font-semibold uppercase tracking-wide text-primary">Demo booking submitted</p>
      <h1 className="mt-2 font-display text-3xl font-extrabold">Your slot is in the owner dashboard</h1>
      <p className="mt-3 text-muted-foreground">This is a demonstration only. No real booking, payment, or SMS was created.</p>
      <dl className="mt-6 grid gap-4 rounded-xl bg-muted/40 p-4 sm:grid-cols-2">
        <Summary label="Reference" value={result.reference} /><Summary label="Customer" value={result.customer_name} />
        <Summary label="Date and time" value={`${result.date} · ${result.start_time}–${result.end_time}`} /><Summary label="Demo price" value={formatBDT(result.price)} />
        <Summary label="Status" value={result.status} />
      </dl>
      <div className="mt-6 flex flex-wrap gap-3"><Button asChild><Link to="/demo-account">Explore owner dashboard <ArrowRight /></Link></Button><Button variant="outline" onClick={() => { setResult(null); setSlotId(""); }}>Book another demo slot</Button></div>
    </div>
  </main>;
  return <main className="mx-auto max-w-5xl px-4 py-7 sm:py-10">
    <DemoBanner ownerLink />
    <section className="mt-6 overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="bg-primary px-5 py-7 text-primary-foreground sm:px-8 sm:py-9">
        <p className="text-xs font-bold uppercase tracking-[.18em] text-primary-foreground/75">Demo Location, Bangladesh</p>
        <h1 className="mt-2 font-display text-3xl font-extrabold sm:text-4xl">{data?.name ?? "TURFBARI Demo Arena"}</h1>
        <p className="mt-2 max-w-2xl text-sm text-primary-foreground/85">Explore the player booking experience. Choose a date and time, then send a simulated booking request to the linked demo owner dashboard.</p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-white/15 px-3 py-1.5">5-a-side football</span><span className="rounded-full bg-white/15 px-3 py-1.5">Floodlights</span><span className="rounded-full bg-white/15 px-3 py-1.5">Changing room</span></div>
      </div>
      <form onSubmit={submit} className="grid gap-7 p-5 sm:p-8 lg:grid-cols-[1.1fr_.9fr]">
        <div>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm font-semibold text-primary">01 · Choose your time</p><h2 className="mt-1 text-xl font-bold">Available demo slots</h2></div><FormField label="Booking date" className="w-full sm:w-52">{(id) => <Input id={id} type="date" min={localDatePlus(0)} max={localDatePlus(60)} value={date} onChange={(e) => { setDate(e.target.value); setSlotId(""); }} />}</FormField></div>
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {slots.map((slot) => <button key={slot.id} type="button" disabled={!slot.enabled || slot.booked} onClick={() => setSlotId(slot.id)} className={`rounded-xl border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-55 ${slotId === slot.id ? "border-primary bg-primary/5 ring-2 ring-primary/20" : "hover:border-primary/50"}`}>
              <span className="flex items-center justify-between gap-2"><span className="font-semibold">{slot.start_time}–{slot.end_time}</span><span className="text-sm font-bold">{formatBDT(slot.price)}</span></span>
              <span className="mt-1 flex items-center justify-between text-xs text-muted-foreground"><span className="capitalize">{slot.category}</span><span>{slot.booked ? "Booked" : slot.enabled ? "Available" : "Unavailable"}</span></span>
            </button>)}
          </div>
          <div className="mt-5 rounded-xl border border-dashed p-4 text-sm text-muted-foreground"><span className="font-semibold text-foreground">Selected:</span> {slots.find((s) => s.id === slotId)?.label ?? "Choose an available time above"}</div>
        </div>
        <div className="rounded-xl bg-muted/30 p-4 sm:p-5">
          <p className="text-sm font-semibold text-primary">02 · Booking details</p><h2 className="mt-1 text-xl font-bold">Your information</h2>
          <div className="mt-4 space-y-4">
            <FormField label="Full name">{(id) => <Input id={id} autoComplete="name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />}</FormField>
            <FormField label="Bangladesh mobile number" hint="Shared demo: use sample details only. Your number is masked and not stored in full.">{(id) => <Input id={id} required type="tel" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="01XXXXXXXXX" />}</FormField>
          </div>
          {message && <p role="alert" className="mt-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{message}</p>}
          <Button className="mt-5 w-full" disabled={busy || !slotId}>{busy ? "Submitting demo…" : "Submit demo booking"}</Button>
          <p className="mt-3 text-center text-xs text-muted-foreground">No payment details are requested. Nothing is sent to a real turf.</p>
        </div>
      </form>
    </section>
    <p className="mt-4 text-center text-xs text-muted-foreground">This is a shared demo workspace. Changes are visible to visitors and automatically reset every 10 minutes; use sample details only. <Link to="/register-turf" className="font-semibold text-primary hover:underline">Ready to create your own account?</Link></p>
  </main>;
}

export function DemoAccountPage() {
  const { data, error, loading, refresh, setData } = useDemoData();
  const [tab, setTab] = useState("Overview");
  const [search, setSearch] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState("");
  const [newSlot, setNewSlot] = useState({ label: "Custom demo slot", start_time: "19:00", end_time: "20:00", category: "night", price: "1600" });
  const navigate = useNavigate();
  useEffect(() => {
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const latest = await demoApi<DemoData>("/owner/workspace/");
        if (active) setData((current) => {
          if (current && latest.reset_count !== current.reset_count) setMessage("The shared demo was refreshed. The sample dashboard has been restored.");
          return latest;
        });
      } catch {
        try {
          await demoApi("/owner-access/", { method: "POST", json: {} });
          const latest = await demoApi<DemoData>("/owner/workspace/");
          if (active) { setData(latest); setMessage("The shared demo was refreshed. The sample dashboard has been restored."); }
        } catch { /* Keep the last snapshot visible if the demo is temporarily unavailable. */ }
      }
    }, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [setData]);
  const act = async (booking: DemoBooking, action: string) => {
    setBusyId(booking.id); setMessage("");
    try {
      const updated = await demoApi<DemoBooking>(`/owner/bookings/${booking.id}/`, { method: "PATCH", json: { action } });
      setData((current) => current ? { ...current, bookings: current.bookings.map((b) => b.id === updated.id ? updated : b) } : current);
      const pastTense: Record<string, string> = { approve: "approved", reject: "rejected", cancel: "cancelled" };
      setMessage(`${booking.reference} ${pastTense[action] ?? action} in demo. No real notification was sent.`);
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Demo action failed."); }
    finally { setBusyId(""); }
  };
  const updateSlot = async (slot: DemoSlot, changes: { enabled?: boolean; price?: string; start_time?: string; end_time?: string }) => {
    try { await demoApi(`/owner/slots/${slot.id}/`, { method: "PATCH", json: changes }); await refresh(); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Could not update the demo slot."); }
  };
  const createSlot = async (event: FormEvent) => {
    event.preventDefault();
    try { await demoApi("/owner/slots/", { method: "POST", json: newSlot }); await refresh(); setMessage("Custom demo slot added. It does not affect real schedules."); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Could not add demo slot."); }
  };
  const tabs = ["Overview", "Bookings", "Slots & pricing", "Customers", "Reports", "SMS preview", "QR preview", "Staff preview", "Turf profile", "Subscription"];
  const filtered = (data?.bookings ?? []).filter((b) => `${b.reference} ${b.customer_name} ${b.customer_phone}`.toLowerCase().includes(search.toLowerCase()) && (!dateFilter || b.date === dateFilter) && (statusFilter === "all" || b.status === statusFilter));
  if (loading) return <PageLoading />;
  if (error) return <DemoError message={error} retry={() => void refresh()} />;
  return <main className="min-h-[80vh] bg-muted/25">
    <div className="border-b bg-card"><div className="mx-auto max-w-7xl px-4 py-4 sm:px-6"><DemoBanner ownerLink={false} /><div className="mt-4 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-muted-foreground">Shared demo workspace · {data?.name}</p><h1 className="font-display text-3xl font-extrabold">Good day, {data?.owner_name}</h1><p className="mt-1 text-sm text-muted-foreground">Changes are shared live with every visitor to this demo.</p></div><Button size="sm" asChild><Link to="/register-turf">Create your account <ArrowRight /></Link></Button></div></div></div>
    <div className="mx-auto grid max-w-7xl gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[220px_1fr]">
      <aside className="h-fit rounded-xl border bg-card p-2 lg:sticky lg:top-20"><nav aria-label="Demo workspace" className="grid grid-cols-2 gap-1 sm:grid-cols-4 lg:grid-cols-1">{tabs.map((item) => <button key={item} onClick={() => setTab(item)} className={`rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${tab === item ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>{item}</button>)}</nav><div className="mt-3 hidden border-t px-3 py-3 text-xs text-muted-foreground lg:block">Permanent shared demo. Please use sample customer information only.</div></aside>
      <section className="min-w-0">
        {message && <p role="status" className="mb-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">{message}</p>}
        {tab === "Overview" && <><div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="text-xl font-bold">Dashboard overview</h2><p className="text-sm text-muted-foreground">Live counts from this demo workspace.</p></div><Button variant="outline" size="sm" onClick={() => void refresh()}><RefreshCw /> Refresh</Button></div><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{([["Today's bookings", data!.summary.today, CalendarDays], ["Pending requests", data!.summary.pending, Clock3], ["Confirmed", data!.summary.confirmed, BadgeCheck], ["Demo customers", data!.summary.customers, Users], ["Enabled slots", data!.summary.enabled_slots, SlidersHorizontal]] as [string, number, LucideIcon][]).map(([label, value, Icon]) => <div key={String(label)} className="rounded-xl border bg-card p-4"><span className="flex items-center gap-2 text-sm text-muted-foreground"><Icon className="size-4 text-primary" />{label}</span><p className="mt-3 text-2xl font-bold tabular-nums">{value}</p></div>)}</div><div className="mt-5 grid gap-4 xl:grid-cols-[1.3fr_.7fr]"><div className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between gap-3"><div><h3 className="font-semibold">Recent demo bookings</h3><p className="text-xs text-muted-foreground">Customer requests appear here instantly.</p></div><Button variant="link" size="sm" onClick={() => setTab("Bookings")}>View all <ArrowRight /></Button></div><BookingList bookings={data!.bookings.slice(0, 5)} act={act} busyId={busyId} /></div><div className="rounded-xl border bg-card p-4"><h3 className="font-semibold">Quick actions</h3><div className="mt-3 grid gap-2"><Button variant="outline" onClick={() => navigate("/demo-booking")}><Eye /> Preview booking page</Button><Button variant="outline" onClick={() => setTab("Slots & pricing")}><SlidersHorizontal /> Edit demo pricing</Button><Button variant="outline" onClick={() => setTab("Reports")}><ChartNoAxesCombined /> View demo reports</Button></div><p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Payments, subscriptions, and SMS are previews only. No real services are called.</p></div></div></>}
        {tab === "Bookings" && <div className="rounded-xl border bg-card p-4 sm:p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-bold">Demo bookings</h2><p className="text-sm text-muted-foreground">Approve, reject, or cancel requests to explore the workflow.</p></div><div className="relative w-full sm:w-64"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input className="pl-9" aria-label="Search bookings" placeholder="Search customer or reference" value={search} onChange={(e) => setSearch(e.target.value)} /></div></div><div className="mt-3 grid gap-2 sm:grid-cols-2"><FormField label="Filter by date">{(id) => <Input id={id} type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />}</FormField><FormField label="Filter by status">{(id) => <select id={id} className="h-10 w-full rounded-md border bg-card px-3 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="all">All statuses</option><option value="pending">Pending</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option><option value="cancelled">Cancelled</option></select>}</FormField></div><BookingList bookings={filtered} act={act} busyId={busyId} /></div>}
        {tab === "Slots & pricing" && <div className="rounded-xl border bg-card p-4 sm:p-5"><h2 className="text-xl font-bold">Slots & pricing</h2><p className="text-sm text-muted-foreground">Changes are confined to this demo workspace.</p><form onSubmit={createSlot} className="mt-4 grid gap-3 rounded-xl bg-muted/30 p-3 sm:grid-cols-2 lg:grid-cols-6"><FormField label="Slot label">{(id) => <Input id={id} value={newSlot.label} onChange={(e) => setNewSlot({ ...newSlot, label: e.target.value })} required />}</FormField><FormField label="Start">{(id) => <Input id={id} type="time" value={newSlot.start_time} onChange={(e) => setNewSlot({ ...newSlot, start_time: e.target.value })} required />}</FormField><FormField label="End">{(id) => <Input id={id} type="time" value={newSlot.end_time} onChange={(e) => setNewSlot({ ...newSlot, end_time: e.target.value })} required />}</FormField><FormField label="Category">{(id) => <select id={id} className="h-10 w-full rounded-md border bg-card px-3 text-sm" value={newSlot.category} onChange={(e) => setNewSlot({ ...newSlot, category: e.target.value })}><option value="morning">Morning</option><option value="evening">Evening</option><option value="night">Night</option><option value="midnight">Midnight</option></select>}</FormField><FormField label="Price (৳)">{(id) => <Input id={id} type="number" step="0.01" min="0" value={newSlot.price} onChange={(e) => setNewSlot({ ...newSlot, price: e.target.value })} required />}</FormField><div className="flex items-end"><Button className="w-full">Add slot</Button></div></form><div className="mt-4 space-y-3">{data!.slots.map((slot) => <div key={slot.id} className="grid items-center gap-3 rounded-xl border p-3 sm:grid-cols-[1fr_auto_auto] sm:p-4"><div className="grid grid-cols-2 gap-2"><FormField label="Start">{(id) => <Input id={id} type="time" defaultValue={slot.start_time} onBlur={(e) => { if (e.target.value !== slot.start_time) void updateSlot(slot, { start_time: e.target.value }); }} />}</FormField><FormField label="End">{(id) => <Input id={id} type="time" defaultValue={slot.end_time} onBlur={(e) => { if (e.target.value !== slot.end_time) void updateSlot(slot, { end_time: e.target.value }); }} />}</FormField><p className="col-span-2 text-xs capitalize text-muted-foreground">{slot.category} · {slot.label}</p></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={slot.enabled} onChange={(e) => void updateSlot(slot, { enabled: e.target.checked })} /> Enabled</label><FormField label="Price (৳)" className="w-36">{(id) => <Input id={id} type="number" step="0.01" min="0" defaultValue={slot.price} onBlur={(e) => { if (e.target.value !== slot.price) void updateSlot(slot, { price: e.target.value }); }} />}</FormField></div>)}</div></div>}
        {tab === "Customers" && <div className="rounded-xl border bg-card p-4 sm:p-5"><h2 className="text-xl font-bold">Demo customers</h2><p className="text-sm text-muted-foreground">Only contacts entered in this isolated browser demo are shown.</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{data!.customers.map((customer) => <div key={customer.id} className="rounded-xl border p-4"><p className="font-semibold">{customer.name}</p><p className="mt-1 text-sm text-muted-foreground">{customer.phone}</p><p className="mt-2 text-xs text-muted-foreground">{data!.bookings.filter((b) => b.customer_phone === customer.phone).length} demo booking(s)</p></div>)}{!data!.customers.length && <EmptyState text="Customer details entered in the booking demo will appear here." />}</div></div>}
        {tab === "Reports" && <div className="rounded-xl border bg-card p-5"><h2 className="text-xl font-bold">Demo reports</h2><p className="text-sm text-muted-foreground">Calculated only from this temporary workspace.</p><div className="mt-4 grid gap-3 sm:grid-cols-3"><Summary label="Demo booking requests" value={data!.bookings.length} /><Summary label="Confirmed demo value" value={formatBDT(data!.bookings.filter((b) => b.status === "confirmed").reduce((sum, b) => sum + Number(b.price), 0))} /><Summary label="Pending requests" value={data!.summary.pending} /></div></div>}
        {tab === "SMS preview" && <div className="rounded-xl border bg-card p-4 sm:p-5"><div className="flex items-start gap-3"><span className="inline-flex rounded-xl bg-accent p-3 text-accent-foreground"><MessageSquareText /></span><div><h2 className="text-xl font-bold">Simulated SMS history</h2><p className="mt-1 text-sm text-muted-foreground">Preview-only records from this demo. No provider is called and no wallet is charged.</p></div></div><div className="mt-4 space-y-3">{data!.sms_messages.map((sms) => <article key={sms.reference} className="rounded-xl border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">{sms.kind.replaceAll("_", " ")}</p><Badge tone="neutral">Preview only</Badge></div><p className="mt-1 text-xs text-muted-foreground">{sms.recipient} · {new Date(sms.created_at).toLocaleString()}</p><p className="mt-3 whitespace-pre-wrap text-sm">{sms.body}</p></article>)}{!data!.sms_messages.length && <EmptyState text="Simulated booking messages will appear here after demo actions." />}</div></div>}
        {tab === "QR preview" && <PreviewCard icon={<QrCode />} title="Public booking page & QR preview" text="Each real turf can share its own booking page and downloadable QR code. This demo QR opens only the simulated booking page." action={<div className="flex flex-wrap items-center gap-4"><img src="/api/public/demo/qr.svg" alt="QR code linking to the TurfBari demo booking page" className="size-36 rounded-lg border bg-white p-2" /><Button onClick={() => navigate("/demo-booking")}>Open demo booking page <ExternalLink /></Button></div>} />}
        {tab === "Subscription" && <PreviewCard icon={<Wallet />} title="Subscription preview" text="Plans and billing are shown in the real owner account. This demo does not create, renew, or modify any subscription." action={<Button asChild><Link to="/#plans">View plans <ArrowRight /></Link></Button>} />}
        {tab === "Staff preview" && <PreviewCard icon={<Users />} title="Staff and manager access" text="Real TURFBARI workspaces let owners grant staff only the operational permissions they need. This demo preview does not create any real staff accounts or change access outside this workspace." />}
        {tab === "Turf profile" && <PreviewCard icon={<Eye />} title="Turf profile settings" text="Review how a public turf page presents business details, photos, location, operating hours, and booking options. These settings are illustrative and cannot change a real profile." action={<Button variant="outline" onClick={() => navigate("/demo-booking")}>View demo public page <ExternalLink /></Button>} />}
      </section>
    </div>
    <div className="border-t bg-card"><div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><p className="font-semibold">Ready to manage your own turf?</p><p className="text-sm text-muted-foreground">Create an account to configure your real business workspace.</p></div><div className="flex gap-2"><Button variant="outline" asChild><Link to="/#plans">View plans</Link></Button><Button asChild><Link to="/register-turf">Create account <ArrowRight /></Link></Button></div></div></div>
  </main>;
}

export function AdminDemoManagementPage() {
  const [rows, setRows] = useState<AdminDemo[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [activity, setActivity] = useState<{ actor_type: string; action: string; summary: string; created_at: string }[] | null>(null);
  const load = async () => { setBusy(true); try { setRows(await api<AdminDemo[]>("/admin/demo/workspaces/")); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Could not load demo workspace."); } finally { setBusy(false); } };
  useEffect(() => { void load(); }, []);
  const action = async (row: AdminDemo, path: string, method: string, json?: unknown) => { try { await api(`/admin/demo/workspaces/${row.id}/${path}`, { method, json }); setNotice(path === "reset/" ? "Shared demo restored to its sample state." : "Shared demo settings updated."); await load(); } catch (e) { setError(e instanceof Error ? e.message : "Action failed."); } };
  const showActivity = async (row: AdminDemo) => { try { setActivity(await api<{ actor_type: string; action: string; summary: string; created_at: string }[]>(`/admin/demo/workspaces/${row.id}/activity/`)); } catch (e) { setError(e instanceof Error ? e.message : "Could not load activity."); } };
  const row = rows[0];
  return <div className="space-y-5"><div><h1 className="font-display text-3xl font-extrabold">Demo Management</h1><p className="mt-1 text-sm text-muted-foreground">Manage the shared interactive demo workspace.</p></div>
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><span className="font-semibold">Public shared data:</span> Visitors can see demo bookings and dashboard activity. Demo data is isolated from real bookings, SMS, payments, wallets and subscriptions. The system automatically restores sample data every 10 minutes; manual reset is also available.</div>
    {notice && <div role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</div>}{error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
    {busy ? <PageLoading /> : row ? <><div className="rounded-xl border bg-card p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><h2 className="text-xl font-bold">{row.name}</h2><Badge tone={row.status === "active" ? "green" : "amber"}>{row.status === "active" ? "Enabled" : "Disabled"}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{row.owner_name} · Last activity {row.last_access_at ? new Date(row.last_access_at).toLocaleString() : "No visits yet"}</p></div><div className="flex flex-wrap gap-2">{row.status === "active" ? <Button variant="destructive" onClick={() => window.confirm("Disable the public demo for everyone?") && void action(row, "", "PATCH", { status: "disabled" })}>Disable public demo</Button> : <Button onClick={() => void action(row, "", "PATCH", { status: "active" })}>Enable public demo</Button>}<Button variant="outline" onClick={() => window.confirm("Restore the demo sample state? Current demo bookings and customers will be cleared.") && void action(row, "reset/", "POST")}><RefreshCw /> Reset demo data</Button><Button variant="outline" onClick={() => void showActivity(row)}><Activity /> Activity</Button></div></div><div className="mt-5 grid gap-3 sm:grid-cols-3"><Summary label="Bookings" value={row.booking_count} /><Summary label="Customers" value={row.customer_count} /><Summary label="Demo slots" value={row.slot_count} /></div><p className="mt-4 text-xs text-muted-foreground">Visitor activity is isolated to demo records and reset every 10 minutes. Manual resets are recorded.</p></div>
    {activity && <div className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between"><h3 className="font-semibold">Recent activity</h3><Button size="sm" variant="ghost" onClick={() => setActivity(null)}>Close</Button></div><div className="mt-3 divide-y">{activity.map((item, i) => <div key={i} className="py-2"><p className="text-sm">{item.summary}</p><p className="text-xs text-muted-foreground">{item.actor_type} · {item.action} · {new Date(item.created_at).toLocaleString()}</p></div>)}{!activity.length && <p className="py-3 text-sm text-muted-foreground">No recorded activity.</p>}</div></div>}</> : <EmptyState text="The shared public workspace will be created on first visit." />}
  </div>;
}

type AdminDemo = { id: string; name: string; owner_name: string; status: string; created_at: string; last_access_at: string | null; booking_count: number; customer_count: number; slot_count: number; reset_count: number };
function BookingList({ bookings, act, busyId }: { bookings: DemoBooking[]; act: (booking: DemoBooking, action: string) => void; busyId: string }) {
  if (!bookings.length) return <EmptyState text="No demo bookings yet. Submit one on the customer booking demo page." />;
  return <div className="mt-4 space-y-3">{bookings.map((booking) => <article key={booking.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{booking.customer_name}</p><Badge tone={booking.status === "confirmed" ? "green" : booking.status === "pending" ? "amber" : "neutral"}>{booking.status}</Badge><Badge tone="neutral">Payment: {booking.payment_status.replaceAll("_", " ")}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{booking.date} · {booking.start_time}–{booking.end_time} · {formatBDT(booking.price)}</p><p className="mt-1 text-xs text-muted-foreground">{booking.reference} · {booking.customer_phone}</p>{booking.payment_amount && <p className="mt-2 text-xs text-muted-foreground">Simulated payment: {formatBDT(booking.payment_amount)} · Sender {booking.sender_phone || "—"} · Ref {booking.transaction_reference || "—"}</p>}{booking.rejection_reason && <p className="mt-2 text-sm text-destructive">Reason: {booking.rejection_reason}</p>}{booking.note && <p className="mt-2 text-sm">“{booking.note}”</p>}</div><div className="flex flex-wrap gap-2">{booking.status === "pending" && <><Button size="sm" disabled={busyId === booking.id} onClick={() => act(booking, "approve")}><BadgeCheck /> Approve</Button><Button size="sm" variant="outline" disabled={busyId === booking.id} onClick={() => act(booking, "reject")}>Reject</Button></>}{booking.status === "confirmed" && <Button size="sm" variant="outline" disabled={busyId === booking.id} onClick={() => act(booking, "cancel")}>Cancel demo booking</Button>}</div></div></article>)}</div>;
}
function DemoBanner({ ownerLink }: { ownerLink: boolean }) { return <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-950"><span><strong>SHARED DEMO</strong> · Changes are visible to visitors and reset every 10 minutes. Use sample information only; no real booking payment, SMS, wallet, or subscription is processed.</span>{ownerLink && <Link to="/demo-booking?mode=owner" className="inline-flex items-center gap-1 font-semibold underline underline-offset-2">Owner dashboard <ArrowRight className="size-4" /></Link>}</div>; }
function PageLoading() { return <div className="mx-auto flex min-h-64 max-w-5xl items-center justify-center px-4" role="status"><span className="size-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" /><span className="sr-only">Loading demo</span></div>; }
function DemoError({ message, retry }: { message: string; retry: () => void }) { useEffect(() => { console.error("TurfBari public demo failed to load:", message); }, [message]); return <main className="mx-auto max-w-2xl px-4 py-16"><div className="rounded-2xl border bg-card p-6 text-center"><h1 className="text-xl font-bold">Demo temporarily unavailable</h1><p role="alert" className="mt-2 text-sm text-muted-foreground">{message}</p><Button className="mt-5" variant="outline" onClick={retry}><RefreshCw /> Retry demo</Button></div></main>; }
function EmptyState({ text }: { text: string }) { return <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{text}</div>; }
function Summary({ label, value }: { label: string; value: string | number }) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-semibold">{value}</dd></div>; }
function PreviewCard({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) { return <div className="mx-auto max-w-2xl rounded-xl border bg-card p-6 sm:p-8"><span className="inline-flex rounded-xl bg-accent p-3 text-accent-foreground">{icon}</span><h2 className="mt-4 text-xl font-bold">{title}</h2><p className="mt-2 leading-relaxed text-muted-foreground">{text}</p>{action && <div className="mt-5">{action}</div>}</div>; }
function localDatePlus(days: number) { const date = new Date(); date.setDate(date.getDate() + days); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
