import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, KeyRound, Loader2, MessageSquareText, PlugZap, Trash2, XCircle, Phone, Mail, MapPin, Share2 } from "lucide-react";
import { useEffect, useState } from "react";
import type React from "react";
import { toast } from "sonner";
import { YouTubeIcon } from "@/components/content/YouTube";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Checkbox, ErrorState, FormField, Input, Select, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

const YT_ID = /^[A-Za-z0-9_-]{11}$/;
/** Client-side twin of the server's youtube_id() — only for the instant preview; the server re-checks. */
function youtubeId(url: string): string | null {
  const raw = url.trim();
  if (YT_ID.test(raw)) return raw;
  try {
    const u = new URL(/^https?:\/\//.test(raw) ? raw : `https://${raw}`);
    const host = u.hostname.toLowerCase();
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"].includes(host)) return null;
    let id: string | null = null;
    if (host === "youtu.be") id = u.pathname.split("/")[1] ?? null;
    else if (u.pathname === "/watch") id = u.searchParams.get("v");
    else {
      const [kind, value] = u.pathname.split("/").filter(Boolean);
      if (kind && ["shorts", "embed", "live", "v"].includes(kind)) id = value ?? null;
    }
    return id && YT_ID.test(id) ? id : null;
  } catch {
    return null;
  }
}

interface ApiConfig {
  youtube: { homepage: YoutubeVideoConfig; booking_page: YoutubeVideoConfig };
  bulksmsbd: {
    api_key_masked: string;
    api_key_source: "admin" | "environment" | "none";
    stored_key_unreadable: boolean;
    sender_id: string;
    sender_id_source: string;
    provider: string;
    enabled: boolean;
    connected: boolean;
    panel_url: string;
    iframe_supported: boolean;
    balance?: string | null;
    test?: { ok: boolean; message: string };
  };
  booking: { max_slots_per_customer: number };
  recurring: { max_days: number; max_occurrences: number; hold_hours: number; limit_exempt: boolean };
}

interface YoutubeVideoConfig {
  video_id: string | null;
  url: string | null;
  title: string;
  enabled: boolean;
}

function Preview({ id }: { id: string }) {
  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg bg-black">
      <iframe
        className="size-full"
        src={`https://www.youtube-nocookie.com/embed/${id}?rel=0`}
        title="Video preview"
        loading="lazy"
        allow="encrypted-media; picture-in-picture; fullscreen"
        referrerPolicy="strict-origin-when-cross-origin"
        allowFullScreen
      />
    </div>
  );
}

export function AdminApiPage() {
  const qc = useQueryClient();
  const config = useQuery({ queryKey: ["admin", "api-config"], queryFn: () => api<ApiConfig>("/admin/api-config/") });
  const c = config.data;
  return (
    <>
      <PageHeader title="API Settings" description="Manage platform integrations and public video settings. Provider credentials stay on the server." />
      {config.isPending && <Skeleton className="h-96" />}
      {config.isError && <ErrorState error={config.error} onRetry={() => config.refetch()} />}
      {c && (
        <div className="space-y-8">
          <section aria-labelledby="youtube-management-title">
            <div className="mb-4"><h2 id="youtube-management-title" className="text-lg font-semibold">YouTube Video Management</h2><p className="text-sm text-muted-foreground">Configure homepage and public booking videos independently.</p></div>
            <div className="grid gap-6 xl:grid-cols-2">
              <YouTubeConfigCard
                current={c.youtube.homepage}
                scope="homepage"
                onSaved={() => {
                  qc.invalidateQueries({ queryKey: ["admin", "api-config"] });
                  qc.invalidateQueries({ queryKey: ["public", "youtube", "homepage"] });
                }}
              />
              <YouTubeConfigCard
                current={c.youtube.booking_page}
                scope="booking"
                onSaved={() => {
                  qc.invalidateQueries({ queryKey: ["admin", "api-config"] });
                  qc.invalidateQueries({ queryKey: ["public", "youtube", "booking"] });
                }}
              />
            </div>
          </section>
          <section aria-labelledby="other-api-settings-title">
            <h2 id="other-api-settings-title" className="mb-4 text-lg font-semibold">Other API &amp; Platform Settings</h2>
            <div className="grid gap-6 xl:grid-cols-2">
              <BulkSmsCard current={c.bulksmsbd} onSaved={(b) => qc.setQueryData(["admin", "api-config"], { ...c, bulksmsbd: b })} />
              <BookingLimitCard current={c.booking.max_slots_per_customer} onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "api-config"] })} />
              <PaymentsCard />
              <RecurringPolicyCard current={c.recurring} onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "api-config"] })} />
              <CredentialSmsCard />
            </div>
          </section>
        </div>
      )}
    </>
  );
}

interface ContactSettings {
  enabled: boolean; phone: string; email: string; facebook_url: string; whatsapp: string; address: string;
  heading: string; description: string; show_phone: boolean; show_email: boolean; show_facebook: boolean;
  show_whatsapp: boolean; show_address: boolean; updated_at: string;
}

export function AdminContactSettingsPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "contact-settings"], queryFn: () => api<ContactSettings>("/admin/contact-settings/") });
  const [form, setForm] = useState<ContactSettings | null>(null);
  useEffect(() => { if (query.data) setForm(query.data); }, [query.data]);
  const save = useMutation({
    mutationFn: (data: ContactSettings) => api<ContactSettings>("/admin/contact-settings/", { method: "PUT", json: data }),
    onSuccess: (data) => { setForm(data); qc.setQueryData(["admin", "contact-settings"], data); qc.invalidateQueries({ queryKey: ["public", "contact"] }); toast.success("Homepage contact information saved"); },
    onError: (error) => toast.error(errorText(error)),
  });
  const update = (key: keyof ContactSettings, value: string | boolean) => setForm((current) => current ? { ...current, [key]: value } : current);
  return <>
    <PageHeader title="Contact Information" description="Manage the public contact details shown on the TURFBARI homepage." />
    {query.isPending && <Skeleton className="h-96" />}
    {query.isError && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
    {form && <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.8fr)]">
      <Card><CardHeader><CardTitle>Homepage contact settings</CardTitle></CardHeader><CardContent>
        <form className="flex flex-col gap-5" onSubmit={(event) => { event.preventDefault(); save.mutate(form); }}>
          <Checkbox label="Show the Contact Us section on homepage" checked={form.enabled} onChange={(e) => update("enabled", e.target.checked)} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Section heading">{(id) => <Input id={id} value={form.heading} onChange={(e) => update("heading", e.target.value)} placeholder="Get in Touch" />}</FormField>
            <FormField label="Phone number" hint="Use the verified public support number.">{(id) => <Input id={id} type="tel" value={form.phone} onChange={(e) => update("phone", e.target.value)} />}</FormField>
            <FormField label="Support email">{(id) => <Input id={id} type="email" value={form.email} onChange={(e) => update("email", e.target.value)} />}</FormField>
            <FormField label="Facebook page URL">{(id) => <Input id={id} type="url" value={form.facebook_url} onChange={(e) => update("facebook_url", e.target.value)} placeholder="https://www.facebook.com/…" />}</FormField>
            <FormField label="WhatsApp number" hint="Optional; Bangladesh country code accepted.">{(id) => <Input id={id} type="tel" value={form.whatsapp} onChange={(e) => update("whatsapp", e.target.value)} />}</FormField>
            <FormField label="Office / business address">{(id) => <Input id={id} value={form.address} onChange={(e) => update("address", e.target.value)} />}</FormField>
          </div>
          <FormField label="Section description">{(id) => <Textarea id={id} value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="Have questions about TURFBARI? We're here to help." />}</FormField>
          <fieldset className="flex flex-wrap gap-x-5 gap-y-3 rounded-lg border p-4"><legend className="px-1 text-sm font-semibold">Show contact methods</legend>
            {([ ["show_phone", "Phone"], ["show_email", "Email"], ["show_facebook", "Facebook"], ["show_whatsapp", "WhatsApp"], ["show_address", "Address"] ] as const).map(([key, label]) => <Checkbox key={key} label={label} checked={form[key]} onChange={(e) => update(key, e.target.checked)} />)}
          </fieldset>
          <div className="flex flex-wrap items-center justify-between gap-3">
            {form.updated_at && <span className="text-xs text-muted-foreground">Last updated {new Date(form.updated_at).toLocaleString()}</span>}
            <Button className="ml-auto min-h-11" type="submit" disabled={save.isPending}>{save.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Save Changes</Button>
          </div>
        </form>
      </CardContent></Card>
      <Card className="h-fit"><CardHeader><CardTitle>Preview</CardTitle></CardHeader><CardContent>
        <div className="rounded-xl border bg-muted/30 p-5"><p className="text-xs font-bold uppercase tracking-wider text-primary">Let's Talk</p><h3 className="mt-1 text-xl font-bold">{form.heading || "Get in Touch"}</h3><p className="mt-2 text-sm text-muted-foreground">{form.description || "Have questions about TURFBARI or want to bring your turf business online? We're here to help."}</p>
          <div className="mt-4 grid gap-2">
            {form.enabled && form.show_phone && form.phone && <PreviewLine icon={<Phone />} value={form.phone} />}
            {form.enabled && form.show_email && form.email && <PreviewLine icon={<Mail />} value={form.email} />}
            {form.enabled && form.show_facebook && form.facebook_url && <PreviewLine icon={<Share2 />} value="Visit Facebook Page" />}
            {form.enabled && form.show_whatsapp && form.whatsapp && <PreviewLine icon={<MessageSquareText />} value={form.whatsapp} />}
            {form.enabled && form.show_address && form.address && <PreviewLine icon={<MapPin />} value={form.address} />}
            {!form.enabled && <p className="text-sm text-muted-foreground">Contact section hidden.</p>}
            {form.enabled && !form.phone && !form.email && !form.facebook_url && !form.whatsapp && !form.address && <p className="text-sm text-muted-foreground">No contact methods configured yet.</p>}
          </div>
        </div>
      </CardContent></Card>
    </div>}
  </>;
}

function PreviewLine({ icon, value }: { icon: React.ReactNode; value: string }) {
  return <div className="flex min-h-11 items-center gap-3 rounded-lg border bg-card px-3 py-2 text-sm"><span className="text-primary">{icon}</span>{value}</div>;
}

function YouTubeConfigCard({ current, scope, onSaved }: {
  current: YoutubeVideoConfig;
  scope: "homepage" | "booking";
  onSaved: () => void;
}) {
  const isHomepage = scope === "homepage";
  const [url, setUrl] = useState(current.url ?? "");
  const [title, setTitle] = useState(current.title ?? "");
  const [enabled, setEnabled] = useState(current.enabled);
  const id = youtubeId(url);
  useEffect(() => {
    setUrl(current.url ?? "");
    setTitle(current.title ?? "");
    setEnabled(current.enabled);
  }, [current.url, current.title, current.enabled]);
  const save = useMutation({
    mutationFn: () => api<YoutubeVideoConfig>(`/admin/api-config/youtube/${scope}/`, {
      method: "PUT",
      json: { url, title, enabled },
    }),
    onSuccess: () => {
      toast.success(`${isHomepage ? "Homepage" : "Booking page"} video settings saved`);
      onSaved();
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const invalidUrl = Boolean(url.trim()) && !id;
  const endpointError = save.error instanceof ApiError ? save.error.fields?.url : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <YouTubeIcon className="h-5 w-auto" /> {isHomepage ? "Homepage Video" : "Public Booking Page Video"}
          {enabled && id ? <Badge tone="green">Enabled</Badge> : <Badge tone="neutral">Disabled</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          {isHomepage
            ? "Manage the YouTube video displayed on the main TurfBari homepage."
            : "Manage the YouTube video displayed next to the booking heading on public turf pages."}
        </p>
        <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
          <Checkbox
            label={isHomepage ? "Show homepage video" : "Show video on public booking pages"}
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <FormField label="Section title" hint="Optional title shown above the video popup.">
            {(fieldId) => <Input id={fieldId} maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} />}
          </FormField>
          <FormField
            label="YouTube video URL"
            hint="youtube.com/watch?v=…, youtu.be/…, /shorts/…, /embed/…"
            error={invalidUrl ? ["Paste a valid YouTube video link."] : endpointError}
          >
            {(fieldId) => (
              <div className="flex gap-2">
                <Input id={fieldId} placeholder="Paste the link here" value={url} onChange={(event) => setUrl(event.target.value)} />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigator.clipboard.readText().then((value) => setUrl(value.trim())).catch(() => toast.error("Couldn't read the clipboard — paste with Ctrl+V"))}
                >Paste</Button>
              </div>
            )}
          </FormField>
          {id && <Preview id={id} />}
          <div className="flex justify-end">
            <Button type="submit" disabled={save.isPending || invalidUrl || (enabled && !id)}>
              {save.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Save Changes
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
function BulkSmsCard({ current, onSaved }: { current: ApiConfig["bulksmsbd"]; onSaved: (b: ApiConfig["bulksmsbd"]) => void }) {
  const [key, setKey] = useState("");
  const [sender, setSender] = useState("");
  const [test, setTest] = useState<ApiConfig["bulksmsbd"] | null>(null);
  const save = useMutation({
    mutationFn: (body: object) => api<ApiConfig["bulksmsbd"]>("/admin/api-config/bulksmsbd/", { method: "PUT", json: body }),
    onSuccess: (b) => {
      toast.success("BulkSMSBD settings saved");
      setKey("");
      setSender("");
      setTest(null);
      onSaved(b);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const check = useMutation({
    mutationFn: () => api<ApiConfig["bulksmsbd"]>("/admin/api-config/bulksmsbd/", { method: "POST" }),
    onSuccess: (b) => {
      setTest(b);
      onSaved(b);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const source = { admin: "saved here (encrypted)", environment: "from the server environment", none: "not set" }[current.api_key_source];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquareText className="size-5 text-primary" /> BulkSMSBD
          {current.connected ? <Badge tone="green">Connected</Badge> : <Badge tone="red">Not connected</Badge>}
          {!current.enabled && <Badge tone="amber">Sending off</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">API key</dt>
            <dd className="font-mono">{current.api_key_masked || "—"}</dd>
            <dd className="text-xs text-muted-foreground">{source}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Sender ID</dt>
            <dd className="font-mono">{current.sender_id || "—"}</dd>
            <dd className="text-xs text-muted-foreground">{current.sender_id_source}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Provider mode</dt>
            <dd>{current.provider}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Balance</dt>
            <dd>{test?.balance ? `৳${test.balance}` : test ? "unavailable" : "Run a test to check"}</dd>
          </div>
        </dl>
        {current.stored_key_unreadable && (
          <p className="rounded-md bg-amber-500/10 p-2 text-sm">The saved key can't be read (the server secret changed). Enter it again.</p>
        )}
        {test?.test && (
          <p className={cn("flex items-center gap-2 rounded-md p-2 text-sm", test.test.ok ? "bg-green-500/10" : "bg-destructive/10 text-destructive")}>
            {test.test.ok ? <CheckCircle2 className="size-4 text-green-600" /> : <XCircle className="size-4" />} {test.test.message}
          </p>
        )}
        <form
          className="grid gap-3 sm:grid-cols-2"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            const body: Record<string, string> = {};
            if (key.trim()) body.api_key = key.trim();
            if (sender.trim()) body.sender_id = sender.trim();
            if (Object.keys(body).length) save.mutate(body);
          }}
        >
          <FormField label="New API key" hint="Leave empty to keep the current key. It is stored encrypted and never shown again.">
            {(id) => <Input id={id} type="password" autoComplete="new-password" value={key} onChange={(e) => setKey(e.target.value)} />}
          </FormField>
          <FormField label="Sender ID" hint="Exactly as approved in BulkSMSBD">
            {(id) => <Input id={id} placeholder={current.sender_id || "e.g. 8809617…"} value={sender} onChange={(e) => setSender(e.target.value)} />}
          </FormField>
          <div className="flex flex-wrap justify-end gap-2 sm:col-span-2">
            {current.api_key_source === "admin" && (
              <Button type="button" variant="ghost" onClick={() => window.confirm("Remove the saved key? The server environment key (if any) will be used.") && save.mutate({ clear_api_key: true })}>
                <Trash2 /> Remove saved key
              </Button>
            )}
            <Button type="button" variant="outline" disabled={check.isPending || !current.connected} onClick={() => check.mutate()}>
              {check.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test connection
            </Button>
            <Button type="submit" disabled={save.isPending || (!key.trim() && !sender.trim())}>
              <KeyRound /> Save
            </Button>
          </div>
        </form>
        <p className="text-xs text-muted-foreground">
          BulkSMSBD offers no embeddable dashboard, so TurfBari manages SMS through its API (test SMS, templates, logs and usage are on the{" "}
          <a href="/admin/sms" className="text-primary hover:underline">
            SMS page
          </a>
          ). Recharge and sender IDs:{" "}
          <a href={current.panel_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            BulkSMSBD panel <ExternalLink className="size-3" />
          </a>
        </p>
      </CardContent>
    </Card>
  );
}

function BookingLimitCard({ current, onSaved }: { current: number; onSaved: () => void }) {
  const [value, setValue] = useState(String(current));
  const save = useMutation({
    mutationFn: () => api("/admin/api-config/booking/", { method: "PUT", json: { max_slots_per_customer: Number(value) } }),
    onSuccess: () => {
      toast.success("Booking limit saved");
      onSaved();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer booking limit</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <FormField label="Slots one mobile number can book per day" hint="Per Bangladesh calendar day, across all turfs. Pending requests count; expired, rejected and cancelled don't." className="flex-1">
            {(id) => <Input id={id} type="number" min={1} max={20} step={1} value={value} onChange={(e) => setValue(e.target.value)} />}
          </FormField>
          <Button type="submit" disabled={save.isPending || Number(value) === current}>
            Save
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

interface PaymentSettings {
  recharge_enabled: boolean;
  recharge_bkash_number: string;
  recharge_instructions: string;
  recharge_fee_percent: string;
  recharge_min_amount: string;
  recharge_max_amount: string;
  subscription_bkash_number: string;
  subscription_instructions: string;
  subscription_bkash_account_type: string;
  subscription_fee_percent: string;
  platform_owner_sms: boolean;
}

/** bKash numbers and charges for SMS wallet recharges and subscription payments. */
function PaymentsCard() {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["admin", "payment-settings"], queryFn: () => api<PaymentSettings>("/admin/api-config/payments/") });
  const [form, setForm] = useState<PaymentSettings | null>(null);
  useEffect(() => {
    if (data.data && !form) setForm(data.data);
  }, [data.data, form]);
  const save = useMutation({
    mutationFn: () => api<PaymentSettings>("/admin/api-config/payments/", { method: "PUT", json: form }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "payment-settings"], d);
      setForm(d);
      toast.success("Payment settings saved");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  if (!form) return <Skeleton className="h-64" />;
  const text = (k: keyof PaymentSettings) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="rounded bg-[#e2136e] px-1.5 py-0.5 text-xs font-bold text-white">bKash</span> Payments to TurfBari
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-6 lg:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-2 font-semibold">SMS wallet recharge</legend>
            <div className="sm:col-span-2">
              <Checkbox label="Owners can recharge their SMS wallet" checked={form.recharge_enabled} onChange={(e) => setForm({ ...form, recharge_enabled: e.target.checked })} />
            </div>
            <FormField label="bKash number" error={fields?.recharge_bkash_number}>
              {(id) => <Input id={id} type="tel" value={form.recharge_bkash_number} onChange={text("recharge_bkash_number")} />}
            </FormField>
            <FormField label="Extra bKash charge (%)" error={fields?.recharge_fee_percent}>
              {(id) => <Input id={id} type="number" step="0.01" min={0} max={20} value={form.recharge_fee_percent} onChange={text("recharge_fee_percent")} />}
            </FormField>
            <FormField label="Minimum recharge (৳)">{(id) => <Input id={id} type="number" step="0.01" min={1} value={form.recharge_min_amount} onChange={text("recharge_min_amount")} />}</FormField>
            <FormField label="Maximum recharge (৳, 0 = none)">{(id) => <Input id={id} type="number" step="0.01" min={0} value={form.recharge_max_amount} onChange={text("recharge_max_amount")} />}</FormField>
            <FormField label="Instructions shown to owners" className="sm:col-span-2">
              {(id) => <Textarea id={id} rows={3} value={form.recharge_instructions} onChange={text("recharge_instructions")} />}
            </FormField>
          </fieldset>
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-2 font-semibold">Subscription payments</legend>
            <FormField label="bKash number" hint="Blank = TURFBARI_BKASH_NUMBER" error={fields?.subscription_bkash_number}>
              {(id) => <Input id={id} type="tel" value={form.subscription_bkash_number} onChange={text("subscription_bkash_number")} />}
            </FormField>
            <FormField label="bKash account type" hint="Shown to people paying (registrations, plans)">
              {(id) => (
                <Select id={id} value={form.subscription_bkash_account_type} onChange={text("subscription_bkash_account_type")}>
                  <option value="Personal">Personal (Send Money)</option>
                  <option value="Agent">Agent (Cash Out)</option>
                  <option value="Merchant">Merchant (Payment)</option>
                </Select>
              )}
            </FormField>
            <FormField label="Payment charge (%)" hint="Added to the plan price">
              {(id) => <Input id={id} type="number" step="0.01" min={0} max={20} value={form.subscription_fee_percent} onChange={text("subscription_fee_percent")} />}
            </FormField>
            <FormField label="Instructions shown to owners" className="sm:col-span-2">
              {(id) => <Textarea id={id} rows={3} value={form.subscription_instructions} onChange={text("subscription_instructions")} />}
            </FormField>
            <div className="sm:col-span-2">
              <Checkbox
                label="Send owners SMS when TurfBari approves/rejects a recharge or plan (from TurfBari's own SMS, free for them)"
                checked={form.platform_owner_sms}
                onChange={(e) => setForm({ ...form, platform_owner_sms: e.target.checked })}
              />
            </div>
          </fieldset>
          <Button type="submit" className="lg:col-span-2 lg:justify-self-end" disabled={save.isPending}>
            Save payment settings
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ login details by SMS
interface CredentialSms {
  enabled: boolean;
  language: "bn" | "en";
  temp_password_hours: number;
  created_en: string;
  created_bn: string;
  reset_en: string;
  reset_bn: string;
  defaults: Record<"created_en" | "created_bn" | "reset_en" | "reset_bn", string>;
  previews: Record<"created_en" | "created_bn" | "reset_en" | "reset_bn", string>;
  placeholders: string[];
  sms_available: boolean;
}
type TemplateKey = "created_en" | "created_bn" | "reset_en" | "reset_bn";

/** Temporary passwords for new accounts and admin resets, sent by SMS (paid by TurfBari). */
function CredentialSmsCard() {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["admin", "credential-sms"], queryFn: () => api<CredentialSms>("/admin/api-config/credentials/") });
  const [form, setForm] = useState<Omit<CredentialSms, "defaults" | "previews" | "placeholders" | "sms_available"> | null>(null);
  const [which, setWhich] = useState<TemplateKey>("created_bn");
  useEffect(() => {
    if (data.data && !form) {
      const { defaults: _d, previews: _p, placeholders: _ph, sms_available: _a, ...rest } = data.data;
      setForm(rest);
    }
  }, [data.data, form]);
  const save = useMutation({
    mutationFn: () => api<CredentialSms>("/admin/api-config/credentials/", { method: "PUT", json: form }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "credential-sms"], d);
      toast.success("Login-details SMS settings saved");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  const d = data.data;
  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <KeyRound className="size-5 text-primary" /> Login details by SMS
          {d && (d.sms_available ? <Badge tone="green">Active</Badge> : <Badge tone="amber">Not sending — shown once instead</Badge>)}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.isPending && <Skeleton className="h-48" />}
        {data.isError && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
        {d && form && (
          <form
            className="flex flex-col gap-4 text-sm"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <p className="text-muted-foreground">
              New accounts and admin password resets get a random temporary password by SMS to the account's mobile. TurfBari pays for these SMS
              (no turf wallet is charged), the password is never shown to anyone, and the user must change it at first sign-in. When this is off
              or SMS isn't connected, the password is shown once to whoever created the account instead.
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
              <Checkbox label="Send login details by SMS" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              <FormField label="SMS language">
                {(id) => (
                  <Select id={id} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value as "bn" | "en" })}>
                    <option value="bn">বাংলা</option>
                    <option value="en">English</option>
                  </Select>
                )}
              </FormField>
              <FormField label="Temporary password valid for (hours)" error={fields?.temp_password_hours}>
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={1}
                    max={168}
                    value={form.temp_password_hours}
                    onChange={(e) => setForm({ ...form, temp_password_hours: Number(e.target.value) })}
                  />
                )}
              </FormField>
            </div>
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="Template">
              {(
                [
                  ["created_bn", "New account · বাংলা"],
                  ["created_en", "New account · English"],
                  ["reset_bn", "Reset · বাংলা"],
                  ["reset_en", "Reset · English"],
                ] as [TemplateKey, string][]
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={which === k}
                  onClick={() => setWhich(k)}
                  className={cn("rounded-full border px-3 py-1 text-xs font-medium", which === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <FormField
                label="Message"
                hint={`Leave empty to use TurfBari's default. Placeholders: ${d.placeholders.map((p) => `{${p}}`).join(" ")} — {password} and {login_url} are required.`}
                error={fields?.[which]}
              >
                {(id) => (
                  <Textarea
                    id={id}
                    rows={7}
                    lang={which.endsWith("bn") ? "bn" : "en"}
                    placeholder={d.defaults[which]}
                    value={form[which]}
                    onChange={(e) => setForm({ ...form, [which]: e.target.value })}
                  />
                )}
              </FormField>
              <div>
                <p className="mb-1.5 text-sm font-medium">Saved preview (password hidden)</p>
                <pre className="whitespace-pre-wrap rounded-md border bg-secondary/50 p-3 font-sans text-xs" lang={which.endsWith("bn") ? "bn" : "en"}>
                  {d.previews[which]}
                </pre>
              </div>
            </div>
            <Button type="submit" className="self-start" disabled={save.isPending}>
              {save.isPending && <Loader2 className="animate-spin" />} Save
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ advance & recurring bookings
function RecurringPolicyCard({
  current,
  onSaved,
}: {
  current: { max_days: number; max_occurrences: number; hold_hours: number; limit_exempt: boolean };
  onSaved: () => void;
}) {
  const [form, setForm] = useState(current);
  const save = useMutation({
    mutationFn: () => api("/admin/api-config/recurring/", { method: "PUT", json: form }),
    onSuccess: () => {
      toast.success("Advance booking policy saved");
      onSaved();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const num = (k: "max_days" | "max_occurrences" | "hold_hours") => (e: { target: { value: string } }) => setForm({ ...form, [k]: Number(e.target.value) });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Advance &amp; recurring bookings</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (form.limit_exempt && !current.limit_exempt && !window.confirm("Let recurring series ignore the per-customer daily limit? This is recorded in the audit log.")) return;
            save.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Furthest date (days ahead)">{(id) => <Input id={id} type="number" min={1} max={366} value={form.max_days} onChange={num("max_days")} />}</FormField>
            <FormField label="Max dates per series">{(id) => <Input id={id} type="number" min={1} max={400} value={form.max_occurrences} onChange={num("max_occurrences")} />}</FormField>
            <FormField label="Unpaid hold (hours)">{(id) => <Input id={id} type="number" min={1} max={168} value={form.hold_hours} onChange={num("hold_hours")} />}</FormField>
          </div>
          <Checkbox
            label="Exempt recurring series from the per-customer daily limit (off by default)"
            checked={form.limit_exempt}
            onChange={(e) => setForm({ ...form, limit_exempt: e.target.checked })}
          />
          <Button type="submit" className="self-start" disabled={save.isPending || JSON.stringify(form) === JSON.stringify(current)}>
            Save
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
