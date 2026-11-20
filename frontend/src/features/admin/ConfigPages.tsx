import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Eye, KeyRound, Loader2, MessageSquareText, PlugZap, Send, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FormattedText } from "@/components/content/FormattedText";
import { YouTubeIcon } from "@/components/content/YouTube";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Checkbox, ErrorState, FormField, Input, Textarea } from "@/components/ui/form";
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
  youtube: { video_id: string | null; url: string | null };
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
}

function Preview({ id }: { id: string }) {
  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg bg-black">
      <iframe
        className="size-full"
        src={`https://www.youtube-nocookie.com/embed/${id}?rel=0`}
        title="Video preview"
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
      <PageHeader title="API" description="Platform integrations shared by every turf: the booking-guide video and BulkSMSBD. Credentials never leave the server." />
      {config.isPending && <Skeleton className="h-96" />}
      {config.isError && <ErrorState error={config.error} onRetry={() => config.refetch()} />}
      {c && (
        <div className="grid gap-6 xl:grid-cols-2">
          <YouTubeCard current={c.youtube} onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "api-config"] })} />
          <BulkSmsCard current={c.bulksmsbd} onSaved={(b) => qc.setQueryData(["admin", "api-config"], { ...c, bulksmsbd: b })} />
          <BookingLimitCard current={c.booking.max_slots_per_customer} onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "api-config"] })} />
          <PaymentsCard />
        </div>
      )}
    </>
  );
}

function YouTubeCard({ current, onSaved }: { current: ApiConfig["youtube"]; onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [editing, setEditing] = useState(!current.video_id);
  const id = youtubeId(url);
  const save = useMutation({
    mutationFn: (value: string) => api<ApiConfig["youtube"]>("/admin/api-config/youtube/", { method: "PUT", json: { url: value } }),
    onSuccess: (r) => {
      toast.success(r.video_id ? "Video saved — every turf page shows it now" : "Video removed from every turf page");
      setUrl("");
      setEditing(!r.video_id);
      onSaved();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <YouTubeIcon className="h-5 w-auto" /> YouTube
          {current.video_id ? <Badge tone="green">Showing on all turf pages</Badge> : <Badge tone="neutral">Off</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          The <span lang="bn">“বুকিং করার নিয়ম”</span> video next to “Book a slot” on every turf's booking page. Turf owners can't change it.
        </p>
        {current.video_id && !editing && (
          <>
            <div className="rounded-lg border p-3 text-sm">
              <p className="text-xs text-muted-foreground">Current video</p>
              <p className="break-all font-medium">{current.url}</p>
              <p className="font-mono text-xs text-muted-foreground">ID {current.video_id}</p>
            </div>
            <Preview id={current.video_id} />
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" disabled={save.isPending} onClick={() => window.confirm("Remove the video from every turf page?") && save.mutate("")}>
                <Trash2 /> Remove
              </Button>
              <Button variant="outline" onClick={() => setEditing(true)}>
                Change video
              </Button>
            </div>
          </>
        )}
        {editing && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (id) save.mutate(url);
            }}
          >
            <FormField
              label="YouTube video URL"
              hint="youtube.com/watch?v=…, youtu.be/…, /shorts/…, /embed/…"
              error={url && !id ? ["That isn't a YouTube video link."] : save.error instanceof ApiError ? save.error.fields?.url : null}
            >
              {(fid) => (
                <div className="flex gap-2">
                  <Input id={fid} placeholder="Paste the link here" value={url} onChange={(e) => setUrl(e.target.value)} />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      navigator.clipboard
                        .readText()
                        .then((t) => setUrl(t.trim()))
                        .catch(() => toast.error("Couldn't read the clipboard — paste with Ctrl+V"))
                    }
                  >
                    Paste
                  </Button>
                </div>
              )}
            </FormField>
            {id && <Preview id={id} />}
            <div className="flex justify-end gap-2">
              {current.video_id && (
                <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              )}
              <Button type="submit" disabled={!id || save.isPending}>
                {save.isPending && <Loader2 className="animate-spin" />} Save video
              </Button>
            </div>
          </form>
        )}
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

// ------------------------------------------------------------------ terms
interface TermsRow {
  id: number;
  version: number;
  status: string;
  terms_body: string;
  rules_body: string;
  published_at: string | null;
  updated_at: string;
  published_by: string | null;
  bookings_agreed: number;
}
interface TermsAdmin {
  enabled: boolean;
  published: TermsRow | null;
  draft: TermsRow | null;
  history: { version: number; status: string; published_at: string | null; bookings_agreed: number }[];
}

export function AdminTermsPage() {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["admin", "terms"], queryFn: () => api<TermsAdmin>("/admin/terms/") });
  const [form, setForm] = useState<{ terms_body: string; rules_body: string } | null>(null);
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    if (data.data && !form) {
      const src = data.data.draft ?? data.data.published;
      setForm({ terms_body: src?.terms_body ?? "", rules_body: src?.rules_body ?? "" });
    }
  }, [data.data, form]);
  const set = (d: TermsAdmin, message: string) => {
    qc.setQueryData(["admin", "terms"], d);
    toast.success(message);
  };
  const saveDraft = useMutation({
    mutationFn: () => api<TermsAdmin>("/admin/terms/", { method: "PUT", json: form }),
    onSuccess: (d) => set(d, "Draft saved — customers still see the published version"),
    onError: (e) => toast.error(errorText(e)),
  });
  const publish = useMutation({
    mutationFn: async () => {
      await api<TermsAdmin>("/admin/terms/", { method: "PUT", json: form });
      return api<TermsAdmin>("/admin/terms/publish/", { method: "POST" });
    },
    onSuccess: (d) => set(d, `Version ${d.published?.version} published — new bookings must accept it`),
    onError: (e) => toast.error(errorText(e)),
  });
  const discard = useMutation({
    mutationFn: () => api<TermsAdmin>("/admin/terms/publish/", { method: "DELETE" }),
    onSuccess: (d) => {
      setForm({ terms_body: d.published?.terms_body ?? "", rules_body: d.published?.rules_body ?? "" });
      set(d, "Draft discarded");
    },
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api<TermsAdmin>("/admin/terms/switch/", { method: "PUT", json: { enabled } }),
    onSuccess: (d) => set(d, d.enabled ? "Customers must accept the terms again" : "Terms agreement turned off"),
  });
  const d = data.data;
  const dirty = d && form && (form.terms_body !== (d.draft ?? d.published)?.terms_body || form.rules_body !== (d.draft ?? d.published)?.rules_body);

  return (
    <>
      <PageHeader
        title="Terms & Rules"
        description="Terms & Conditions and Booking Rules for every turf's booking page. Each publish is a new version; bookings keep the version the customer accepted."
      />
      {data.isPending && <Skeleton className="h-96" />}
      {data.isError && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
      {d && form && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                {preview ? "Preview" : "Edit"}
                {d.published && <Badge tone="green">Live: v{d.published.version}</Badge>}
                {d.draft && <Badge tone="amber">Draft v{d.draft.version}</Badge>}
                {!d.enabled && <Badge tone="red">Agreement off</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {preview ? (
                <div className="flex flex-col gap-6 rounded-lg border p-4">
                  <section>
                    <h2 className="mb-2 text-lg font-bold">General Terms &amp; Conditions</h2>
                    <FormattedText text={form.terms_body} />
                  </section>
                  <section>
                    <h2 className="mb-2 text-lg font-bold">Booking Rules &amp; Regulations</h2>
                    <FormattedText text={form.rules_body} />
                  </section>
                </div>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground">
                    Bengali and English welcome. Formatting: <code># Heading</code>, <code>## Subheading</code>, <code>- bullet</code>, <code>1. numbered</code>,{" "}
                    <code>**bold**</code>, blank line between paragraphs.
                  </p>
                  <FormField label="General Terms & Conditions">
                    {(id) => <Textarea id={id} rows={12} value={form.terms_body} onChange={(e) => setForm({ ...form, terms_body: e.target.value })} />}
                  </FormField>
                  <FormField label="Booking Rules & Regulations">
                    {(id) => <Textarea id={id} rows={12} value={form.rules_body} onChange={(e) => setForm({ ...form, rules_body: e.target.value })} />}
                  </FormField>
                </>
              )}
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="ghost" onClick={() => setPreview(!preview)}>
                  <Eye /> {preview ? "Back to editing" : "Preview"}
                </Button>
                {d.draft && (
                  <Button variant="ghost" disabled={discard.isPending} onClick={() => window.confirm("Discard the draft?") && discard.mutate()}>
                    Discard draft
                  </Button>
                )}
                <Button variant="outline" disabled={!form.terms_body.trim() || !form.rules_body.trim() || saveDraft.isPending} onClick={() => saveDraft.mutate()}>
                  Save draft
                </Button>
                <Button
                  disabled={!form.terms_body.trim() || !form.rules_body.trim() || publish.isPending || (!dirty && !d.draft)}
                  onClick={() =>
                    window.confirm("Publish this as a new version? From now on every new booking must accept it.") && publish.mutate()
                  }
                >
                  {publish.isPending ? <Loader2 className="animate-spin" /> : <Send />} Publish
                </Button>
              </div>
            </CardContent>
          </Card>
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>On booking pages</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <Checkbox
                  label="Customers must accept the terms to book"
                  checked={d.enabled}
                  disabled={toggle.isPending}
                  onChange={(e) => toggle.mutate(e.target.checked)}
                />
                <a href="/terms" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                  Open the public page <ExternalLink className="size-3" />
                </a>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Versions</CardTitle>
              </CardHeader>
              <CardContent>
                {d.history.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nothing published yet.</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {d.history.map((h) => (
                      <li key={h.version} className="flex justify-between gap-2 py-2">
                        <span>
                          v{h.version} {h.status === "published" ? <Badge tone="green">Live</Badge> : <Badge tone="neutral">Replaced</Badge>}
                          <span className="block text-xs text-muted-foreground">
                            {h.published_at && new Date(h.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                          </span>
                        </span>
                        <span className="text-xs text-muted-foreground">{h.bookings_agreed} bookings accepted</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
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
