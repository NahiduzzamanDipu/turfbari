import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Loader2,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  Send,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, EmptyState, ErrorState, FormField, Input, Select, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveMembership } from "@/features/auth/auth";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import type { Paginated } from "@/lib/types";

// ------------------------------------------------------------------ shared
export interface SmsMessage {
  id: string;
  created_at: string;
  sent_at: string | null;
  kind: string;
  kind_label: string;
  to: string;
  body: string;
  status: "queued" | "sending" | "sent" | "failed" | "unknown" | "skipped";
  segments: number;
  attempts: number;
  provider_code: string;
  provider_message: string;
  booking_reference: string | null;
  turf?: { id: string; name: string } | null;
}

interface Counts {
  total: number;
  sent: number;
  failed: number;
  pending: number;
  skipped: number;
  segments: number;
}

const STATUS: Record<SmsMessage["status"], { label: string; tone: BadgeTone }> = {
  queued: { label: "Queued", tone: "blue" },
  sending: { label: "Sending", tone: "blue" },
  sent: { label: "Sent", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  unknown: { label: "Check", tone: "amber" },
  skipped: { label: "Not sent", tone: "neutral" },
};

const KINDS = [
  ["booking_confirmed", "Booking confirmed"],
  ["payment_rejected", "Payment rejected"],
  ["booking_cancelled", "Booking cancelled"],
  ["booking_reminder", "Booking reminder"],
  ["subscription_reminder", "Plan ends soon"],
  ["subscription_expired", "Plan ended"],
  ["password_reset", "Password reset code"],
  ["test", "Test message"],
] as const;

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="tabular mt-1 font-display text-3xl font-bold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function MessageLog({
  base,
  admin,
  onRetry,
}: {
  base: string;
  admin?: boolean;
  onRetry?: (m: SmsMessage) => void;
}) {
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["sms", base, status, kind, q, page],
    queryFn: () =>
      api<Paginated<SmsMessage>>(
        `${base}${base.includes("?") ? "" : "?"}${new URLSearchParams({ status, kind, q, page: String(page) })}`,
      ),
    placeholderData: keepPreviousData,
  });
  const reset = () => setPage(1);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Message log</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            placeholder="Search number, text or booking ID"
            aria-label="Search messages"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              reset();
            }}
          />
          <Select aria-label="Status" value={status} onChange={(e) => {
              setStatus(e.target.value);
              reset();
            }} className="sm:max-w-40">
            <option value="">All statuses</option>
            {Object.entries(STATUS).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </Select>
          <Select aria-label="Type" value={kind} onChange={(e) => {
              setKind(e.target.value);
              reset();
            }} className="sm:max-w-52">
            <option value="">All types</option>
            {KINDS.filter(([k]) => admin || !["password_reset", "test", "subscription_reminder", "subscription_expired"].includes(k)).map(
              ([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ),
            )}
          </Select>
        </div>
        {list.isPending && <Skeleton className="h-40" />}
        {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data?.results.length === 0 && <EmptyState icon={<MessageSquareText />} title="No messages yet" />}
        {list.data && list.data.results.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th>When</th>
                <th>To</th>
                <th>Message</th>
                <th>Status</th>
                {onRetry && <th />}
              </tr>
            </thead>
            <tbody>
              {list.data.results.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap text-sm">
                    {when(m.created_at)}
                    <span className="block text-xs text-muted-foreground">{m.kind_label}</span>
                  </td>
                  <td className="whitespace-nowrap font-mono text-xs">
                    {m.to}
                    {admin && m.turf && <span className="block font-sans text-muted-foreground">{m.turf.name}</span>}
                  </td>
                  <td className="max-w-md text-sm">
                    <p className="line-clamp-2" title={m.body}>
                      {m.body}
                    </p>
                    {m.booking_reference && <span className="text-xs text-muted-foreground">{m.booking_reference}</span>}
                  </td>
                  <td>
                    <Badge tone={STATUS[m.status].tone}>{STATUS[m.status].label}</Badge>
                    {m.status !== "sent" && m.provider_message && (
                      <span className="mt-1 block max-w-48 text-xs text-muted-foreground">{m.provider_message}</span>
                    )}
                    {m.segments > 1 && <span className="block text-xs text-muted-foreground">{m.segments} parts</span>}
                  </td>
                  {onRetry && (
                    <td className="text-right">
                      {(m.status === "failed" || m.status === "unknown") && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            window.confirm(
                              m.status === "unknown"
                                ? "This message may already have been delivered (BulkSMSBD didn't answer in time). Send it again?"
                                : "Try sending this message again?",
                            ) && onRetry(m)
                          }
                        >
                          <RotateCcw /> Retry
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && list.data.count > 20 && (
          <div className="flex items-center justify-end gap-2 text-sm">
            <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft />
            </Button>
            <span className="tabular">Page {page}</span>
            <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ workspace
interface TurfSmsSettings {
  booking_confirmed: boolean;
  payment_rejected: boolean;
  booking_cancelled: boolean;
  booking_reminder: boolean;
  reminder_hours: number;
}

export function WorkspaceSmsPage() {
  const qc = useQueryClient();
  const isOwner = useActiveMembership()?.role === "owner";
  const summary = useQuery({
    queryKey: ["ws", "sms", "summary"],
    queryFn: () =>
      api<Paginated<SmsMessage> & { usage: Counts & { limit: number; used: number }; platform_sms_on: boolean; settings: TurfSmsSettings }>(
        "/workspace/sms/?page_size=1",
      ),
  });
  const save = useMutation({
    mutationFn: (patch: Partial<TurfSmsSettings>) => api<TurfSmsSettings>("/workspace/sms/settings/", { method: "PATCH", json: patch }),
    onSuccess: () => {
      toast.success("SMS settings saved");
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const s = summary.data?.settings;
  const usage = summary.data?.usage;

  return (
    <>
      <PageHeader title="SMS" description="Text messages TurfBari sends to your customers, and what this month has used." />
      {summary.isPending && <Skeleton className="h-40" />}
      {summary.isError && <ErrorState error={summary.error} onRetry={() => summary.refetch()} />}
      {summary.data && usage && s && (
        <div className="flex flex-col gap-6">
          {!summary.data.platform_sms_on && (
            <p className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
              SMS sending is not switched on for TurfBari yet, so messages are logged as “Not sent”. Your settings below are kept.
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Sent this month" value={usage.sent} hint={`${usage.segments} SMS parts`} />
            <Stat label="Failed or not sent" value={usage.failed + usage.skipped} />
            <Stat
              label="Monthly allowance"
              value={usage.limit ? `${usage.used} / ${usage.limit}` : "No limit"}
              hint={usage.limit ? "Set by TurfBari" : undefined}
            />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Send customers an SMS when…</CardTitle>
            </CardHeader>
            <CardContent>
              <fieldset disabled={!isOwner || save.isPending} className="grid gap-3 sm:grid-cols-2">
                <Checkbox label="You approve their bKash payment (booking confirmed)" checked={s.booking_confirmed} onChange={(e) => save.mutate({ booking_confirmed: e.target.checked })} />
                <Checkbox label="You reject their payment" checked={s.payment_rejected} onChange={(e) => save.mutate({ payment_rejected: e.target.checked })} />
                <Checkbox label="A confirmed booking is cancelled" checked={s.booking_cancelled} onChange={(e) => save.mutate({ booking_cancelled: e.target.checked })} />
                <div className="flex flex-wrap items-center gap-2">
                  <Checkbox label="Remind them before the game" checked={s.booking_reminder} onChange={(e) => save.mutate({ booking_reminder: e.target.checked })} />
                  <Select
                    aria-label="Hours before"
                    value={s.reminder_hours}
                    className="w-auto"
                    disabled={!s.booking_reminder}
                    onChange={(e) => save.mutate({ reminder_hours: Number(e.target.value) })}
                  >
                    {[1, 2, 3, 4, 6, 12, 24].map((h) => (
                      <option key={h} value={h}>
                        {h} hour{h > 1 ? "s" : ""} before
                      </option>
                    ))}
                  </Select>
                </div>
              </fieldset>
              {!isOwner && <p className="mt-3 text-xs text-muted-foreground">Only the turf owner can change these.</p>}
            </CardContent>
          </Card>
          <SmsUsageCard />
          <MessageLog base="/workspace/sms/" />
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ admin
interface SmsOverview {
  provider: string;
  configured: boolean;
  api_key_set: boolean;
  sender_id: string;
  balance: string | null;
  config: { enabled: boolean; sender_id: string; per_turf_monthly_limit: number; subscription_reminder_days: number[] };
  today: Counts;
  month: Counts;
  by_turf: { turf_id: string; turf: string; sent: number; segments: number; failed: number }[];
  last_tick: { at: string; results: Record<string, unknown> } | null;
  panel_url: string;
}

interface SmsTemplateRow {
  kind: string;
  label: string;
  body: string;
  default: string;
  customised: boolean;
  placeholders: string[];
}

export function AdminSmsPage() {
  const qc = useQueryClient();
  const overview = useQuery({ queryKey: ["admin", "sms"], queryFn: () => api<SmsOverview>("/admin/sms/") });
  const [config, setConfig] = useState<SmsOverview["config"] | null>(null);
  const [testTo, setTestTo] = useState("");
  const refresh = useMutation({
    mutationFn: () => api<SmsOverview>("/admin/sms/?refresh=1"),
    onSuccess: (d) => qc.setQueryData(["admin", "sms"], d),
  });
  const saveConfig = useMutation({
    mutationFn: (c: SmsOverview["config"]) =>
      api("/admin/sms/", { method: "PATCH", json: { ...c, subscription_reminder_days: c.subscription_reminder_days } }),
    onSuccess: () => {
      toast.success("SMS settings saved");
      setConfig(null);
      qc.invalidateQueries({ queryKey: ["admin", "sms"] });
    },
  });
  const test = useMutation({
    mutationFn: () => api<SmsMessage>("/admin/sms/test/", { method: "POST", json: { to: testTo } }),
    onSuccess: (m) => {
      (m.status === "sent" ? toast.success : toast.error)(m.status === "sent" ? "Test SMS accepted by BulkSMSBD" : `Not sent: ${m.provider_message}`);
      qc.invalidateQueries({ queryKey: ["sms"] });
      qc.invalidateQueries({ queryKey: ["admin", "sms"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const retry = useMutation({
    mutationFn: (m: SmsMessage) => api<SmsMessage>(`/admin/sms/messages/${m.id}/retry/`, { method: "POST" }),
    onSuccess: (m) => {
      (m.status === "sent" ? toast.success : toast.error)(m.status === "sent" ? "Sent" : `Still failing: ${m.provider_message}`);
      qc.invalidateQueries({ queryKey: ["sms"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const o = overview.data;
  const c = config ?? o?.config;
  const configErrors = saveConfig.error instanceof ApiError ? saveConfig.error.fields : null;

  return (
    <>
      <PageHeader
        title="SMS"
        description="BulkSMSBD connection, usage across turfs, message wording and the delivery log."
        actions={
          o && (
            <Button asChild variant="outline">
              <a href={o.panel_url} target="_blank" rel="noreferrer">
                <ExternalLink /> BulkSMSBD panel
              </a>
            </Button>
          )
        }
      />
      {overview.isPending && <Skeleton className="h-48" />}
      {overview.isError && <ErrorState error={overview.error} onRetry={() => overview.refetch()} />}
      {o && c && (
        <div className="flex flex-col gap-6">
          {!o.configured && (
            <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
              <p className="font-semibold">BulkSMSBD is not connected.</p>
              <p className="mt-1 text-muted-foreground">
                Add <code>BULKSMSBD_API_KEY</code> and <code>BULKSMSBD_SENDER_ID</code> to the server's environment (Render → Environment), then
                redeploy. The key is never stored in the database or shown here. Until then every SMS is logged as “Not sent”.
              </p>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="BulkSMSBD balance"
              value={
                <span className="flex items-center gap-2">
                  {o.balance === null ? "—" : o.balance === "unavailable" ? "?" : `৳${o.balance}`}
                  {o.configured && (
                    <Button size="icon" variant="ghost" aria-label="Refresh balance" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
                      {refresh.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                    </Button>
                  )}
                </span>
              }
              hint={o.balance === "unavailable" ? "BulkSMSBD didn't return a balance" : `Provider: ${o.provider} · Sender ID: ${o.sender_id || "not set"}`}
            />
            <Stat label="Sent today" value={o.today.sent} hint={`${o.today.failed} failed · ${o.today.pending} waiting`} />
            <Stat label="Sent this month" value={o.month.sent} hint={`${o.month.segments} SMS parts billed`} />
            <Stat label="Failed this month" value={o.month.failed} hint={`${o.month.skipped} not sent (off / limit / bad number)`} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Settings</CardTitle>
              </CardHeader>
              <CardContent>
                <form
                  className="grid gap-3 sm:grid-cols-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    saveConfig.mutate(c);
                  }}
                >
                  <div className="sm:col-span-2">
                    <Checkbox label="Send SMS (turn off to stop every message platform-wide)" checked={c.enabled} onChange={(e) => setConfig({ ...c, enabled: e.target.checked })} />
                  </div>
                  <FormField label="Sender ID override" hint="Blank = BULKSMSBD_SENDER_ID" error={configErrors?.sender_id}>
                    {(id) => <Input id={id} value={c.sender_id} onChange={(e) => setConfig({ ...c, sender_id: e.target.value })} />}
                  </FormField>
                  <FormField label="SMS per turf per month" hint="0 = no limit" error={configErrors?.per_turf_monthly_limit}>
                    {(id) => (
                      <Input id={id} type="number" min={0} step={1} value={c.per_turf_monthly_limit} onChange={(e) => setConfig({ ...c, per_turf_monthly_limit: Number(e.target.value) })} />
                    )}
                  </FormField>
                  <FormField
                    label="Plan-ending SMS (days before)"
                    hint="Comma-separated, e.g. 7, 3, 1. Owners also get one SMS when the plan has ended."
                    className="sm:col-span-2"
                    error={configErrors?.subscription_reminder_days}
                  >
                    {(id) => (
                      <Input
                        id={id}
                        value={c.subscription_reminder_days.join(", ")}
                        onChange={(e) =>
                          setConfig({
                            ...c,
                            subscription_reminder_days: e.target.value
                              .split(",")
                              .map((x) => Number(x.trim()))
                              .filter((x) => Number.isFinite(x) && x > 0),
                          })
                        }
                      />
                    )}
                  </FormField>
                  {saveConfig.error && !configErrors && <p className="text-sm text-destructive sm:col-span-2">{errorText(saveConfig.error)}</p>}
                  <Button type="submit" disabled={!config || saveConfig.isPending} className="sm:col-span-2 sm:justify-self-end">
                    Save settings
                  </Button>
                </form>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Send a test SMS</CardTitle>
              </CardHeader>
              <CardContent>
                <form
                  className="flex flex-col gap-3 sm:flex-row sm:items-end"
                  onSubmit={(e) => {
                    e.preventDefault();
                    test.mutate();
                  }}
                >
                  <FormField label="Mobile number" className="flex-1">
                    {(id) => <Input id={id} type="tel" placeholder="01XXXXXXXXX" required value={testTo} onChange={(e) => setTestTo(e.target.value)} />}
                  </FormField>
                  <Button type="submit" disabled={test.isPending}>
                    {test.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send test
                  </Button>
                </form>
                <p className="mt-3 text-xs text-muted-foreground">
                  “Sent” means BulkSMSBD accepted the message. BulkSMSBD offers no delivery-report API, so handset delivery can't be confirmed here.
                </p>
                {o.last_tick && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Background tasks last ran {when(o.last_tick.at)} (retries, reminders, expired holds).
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {o.by_turf.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Usage by turf this month</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr>
                      <th>Turf</th>
                      <th className="text-right">Sent</th>
                      <th className="text-right">Parts</th>
                      <th className="text-right">Failed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.by_turf.map((r) => (
                      <tr key={r.turf_id}>
                        <td>{r.turf}</td>
                        <td className="tabular text-right">{r.sent}</td>
                        <td className="tabular text-right">{r.segments}</td>
                        <td className="tabular text-right">{r.failed}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>
          )}

          <TemplatesCard />
          <MessageLog base="/admin/sms/messages/" admin onRetry={(m) => retry.mutate(m)} />
        </div>
      )}
    </>
  );
}

function TemplatesCard() {
  const qc = useQueryClient();
  const templates = useQuery({ queryKey: ["admin", "sms", "templates"], queryFn: () => api<SmsTemplateRow[]>("/admin/sms/templates/") });
  const [editing, setEditing] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: ({ kind, body }: { kind: string; body: string }) =>
      api<SmsTemplateRow[]>(`/admin/sms/templates/${kind}/`, { method: "PUT", json: { body } }),
    onSuccess: (rows, { kind }) => {
      qc.setQueryData(["admin", "sms", "templates"], rows);
      setEditing(({ [kind]: _, ...rest }) => rest);
      toast.success("Template saved");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Message wording</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Bengali messages are billed per 70 characters (67 per part when longer). Keep them short. Words in {"{braces}"} are filled in for each message.
        </p>
        {templates.isPending && <Skeleton className="h-32" />}
        {templates.data?.map((t) => {
          const value = editing[t.kind] ?? t.body;
          const parts = value.length <= 70 ? 1 : Math.ceil(value.length / 67);
          return (
            <div key={t.kind} className="rounded-lg border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  {t.label} {t.customised && <Badge tone="blue">Edited</Badge>}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t.placeholders.map((p) => `{${p}}`).join(" ")}
                </p>
              </div>
              <Textarea aria-label={`${t.label} message`} rows={2} value={value} onChange={(e) => setEditing({ ...editing, [t.kind]: e.target.value })} />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  ~{value.length} characters · about {parts} SMS part{parts > 1 ? "s" : ""} before filling in names
                </span>
                <span className="flex gap-2">
                  {t.customised && (
                    <Button size="sm" variant="ghost" onClick={() => save.mutate({ kind: t.kind, body: t.default })}>
                      Reset to default
                    </Button>
                  )}
                  {editing[t.kind] !== undefined && editing[t.kind] !== t.body && (
                    <Button size="sm" disabled={save.isPending} onClick={() => save.mutate({ kind: t.kind, body: value })}>
                      Save
                    </Button>
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}


// ------------------------------------------------------------------ usage (counted by TurfBari)
interface UsageSummary {
  total: number;
  sent: number;
  failed: number;
  pending: number;
  not_sent: number;
  parts: number;
  attempts: number;
  booking_confirmations: number;
  rejections_cancellations: number;
}
interface WorkspaceUsage {
  all_time: UsageSummary;
  this_month: UsageSummary & { since: string };
  history: { month: string; sent: number; failed: number; parts: number }[];
  plan_notices_from_turfbari: number;
  first_sms_at: string | null;
  source: string;
}

const monthLabel = (ym: string) => new Date(`${ym}-01T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** Owner / manager view of this turf's own SMS usage. */
export function SmsUsageCard() {
  const usage = useQuery({ queryKey: ["ws", "sms", "usage"], queryFn: () => api<WorkspaceUsage>("/workspace/sms/usage/") });
  const u = usage.data;
  const max = Math.max(1, ...(u?.history.map((h) => h.sent + h.failed) ?? [1]));
  return (
    <Card>
      <CardHeader>
        <CardTitle>SMS usage</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {usage.isPending && <Skeleton className="h-32" />}
        {usage.isError && <ErrorState error={usage.error} onRetry={() => usage.refetch()} />}
        {u && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Sent (all time)" value={u.all_time.sent} hint={`${u.all_time.parts} SMS parts`} />
              <Stat label="This month" value={u.this_month.sent} hint={`since ${fmtDate(u.this_month.since)}`} />
              <Stat label="Failed" value={u.all_time.failed} hint={`${u.all_time.not_sent} not sent`} />
              <Stat label="Waiting" value={u.all_time.pending} />
            </div>
            <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
              <div className="rounded-lg border p-3">
                <dt className="text-muted-foreground">Booking confirmations &amp; reminders</dt>
                <dd className="tabular text-lg font-bold">{u.all_time.booking_confirmations}</dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-muted-foreground">Rejections &amp; cancellations</dt>
                <dd className="tabular text-lg font-bold">{u.all_time.rejections_cancellations}</dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-muted-foreground">Plan notices from TurfBari</dt>
                <dd className="tabular text-lg font-bold">{u.plan_notices_from_turfbari}</dd>
                <dd className="text-xs text-muted-foreground">Not counted as your usage</dd>
              </div>
            </dl>
            {u.history.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium">Month by month</p>
                <ul className="flex flex-col gap-1.5 text-sm">
                  {u.history.map((h) => (
                    <li key={h.month} className="grid grid-cols-[6rem_1fr_auto] items-center gap-3">
                      <span className="text-muted-foreground">{monthLabel(h.month)}</span>
                      <span className="flex h-2.5 overflow-hidden rounded-full bg-secondary" aria-hidden>
                        <span className="bg-primary" style={{ width: `${(h.sent / max) * 100}%` }} />
                        <span className="bg-destructive/70" style={{ width: `${(h.failed / max) * 100}%` }} />
                      </span>
                      <span className="tabular text-xs">
                        {h.sent} sent{h.failed ? ` · ${h.failed} failed` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {u.source} BulkSMSBD's balance belongs to TurfBari's account and isn't split per turf.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface AdminUsage {
  from: string | null;
  to: string | null;
  totals: UsageSummary;
  platform: UsageSummary;
  turfs: {
    turf: { id: string; name: string; slug: string };
    total: number;
    sent: number;
    failed: number;
    pending: number;
    not_sent: number;
    parts: number;
    attempts: number;
    high_usage: boolean;
  }[];
  high_usage_threshold: number;
}

function monthStartISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

export function AdminSmsUsagePage() {
  const [from, setFrom] = useState(monthStartISO());
  const [to, setTo] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [account, setAccount] = useState<{ id: string; name: string } | null>(null);
  const params = new URLSearchParams({ from, to, status, q });
  const usage = useQuery({
    queryKey: ["admin", "sms-usage", from, to, status, q],
    queryFn: () => api<AdminUsage>(`/admin/sms/usage/?${params}`),
    placeholderData: keepPreviousData,
  });
  const u = usage.data;
  return (
    <>
      <PageHeader
        title="SMS usage"
        description="Every SMS counted by TurfBari per turf account (retries count once). TurfBari's own plan notices and sign-in codes are shown separately."
        actions={
          <Button asChild variant="outline">
            <a href={`/api/admin/sms/usage/?${params}&export=csv`}>
              <Download /> Export CSV
            </a>
          </Button>
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <FormField label="From">{(id) => <Input id={id} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}</FormField>
        <FormField label="To">{(id) => <Input id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}</FormField>
        <FormField label="Status">
          {(id) => (
            <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="sent">Sent</option>
              <option value="failed">Failed / check</option>
              <option value="queued">Waiting</option>
              <option value="skipped">Not sent</option>
            </Select>
          )}
        </FormField>
        <FormField label="Turf">{(id) => <Input id={id} placeholder="Search turf name" value={q} onChange={(e) => setQ(e.target.value)} />}</FormField>
      </div>
      {usage.isPending && <Skeleton className="h-64" />}
      {usage.isError && <ErrorState error={usage.error} onRetry={() => usage.refetch()} />}
      {u && (
        <div className="flex flex-col gap-6">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Stat label="Sent" value={u.totals.sent} hint={`${u.totals.parts} parts billed`} />
            <Stat label="Failed / check" value={u.totals.failed} />
            <Stat label="Waiting" value={u.totals.pending} />
            <Stat label="Not sent" value={u.totals.not_sent} hint="SMS off, limit, bad number" />
            <Stat label="Provider attempts" value={u.totals.attempts} hint="Retries included" />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>By turf account</CardTitle>
            </CardHeader>
            <CardContent className="p-2 sm:p-4">
              {u.turfs.length === 0 ? (
                <EmptyState icon={<MessageSquareText />} title="No turf SMS in this period" />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th>Turf</th>
                      <th className="text-right">Sent</th>
                      <th className="text-right">Failed</th>
                      <th className="text-right">Waiting</th>
                      <th className="text-right">Not sent</th>
                      <th className="text-right">Parts</th>
                      <th className="text-right">Attempts</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {u.turfs.map((r) => (
                      <tr key={r.turf.id}>
                        <td className="font-medium">
                          {r.turf.name} {r.high_usage && <Badge tone="amber">High usage</Badge>}
                        </td>
                        <td className="tabular text-right">{r.sent}</td>
                        <td className="tabular text-right">{r.failed}</td>
                        <td className="tabular text-right">{r.pending}</td>
                        <td className="tabular text-right">{r.not_sent}</td>
                        <td className="tabular text-right">{r.parts}</td>
                        <td className="tabular text-right">{r.attempts}</td>
                        <td className="text-right">
                          <Button size="sm" variant="ghost" onClick={() => setAccount({ id: r.turf.id, name: r.turf.name })}>
                            View log
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
              <div className="mt-3 flex flex-wrap justify-between gap-2 rounded-lg bg-secondary/50 px-3 py-2 text-sm">
                <span className="font-medium">TurfBari platform messages (plan notices, sign-in codes, tests)</span>
                <span className="tabular">
                  {u.platform.sent} sent · {u.platform.failed} failed · {u.platform.parts} parts
                </span>
              </div>
              <p className="mt-3 px-2 text-xs text-muted-foreground">
                “High usage” = at least {u.high_usage_threshold} sent in the period (3× the typical turf, minimum 20).
              </p>
            </CardContent>
          </Card>
          {account && (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="font-semibold">Log: {account.name}</p>
                <Button size="sm" variant="ghost" onClick={() => setAccount(null)}>
                  Close
                </Button>
              </div>
              <MessageLog key={account.id} base={`/admin/sms/messages/?turf=${account.id}&from=${from}&to=${to}&`} admin />
            </div>
          )}
        </div>
      )}
    </>
  );
}
