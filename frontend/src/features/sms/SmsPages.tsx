import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
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
    queryFn: () => api<Paginated<SmsMessage>>(`${base}?${new URLSearchParams({ status, kind, q, page: String(page) })}`),
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

