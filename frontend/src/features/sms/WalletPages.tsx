import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Copy, Loader2, Megaphone, RotateCcw, Send, Upload, Wallet, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveMembership } from "@/features/auth/auth";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import type { Paginated } from "@/lib/types";
import { cn } from "@/lib/utils";

// Same rule as the server: GSM-7 160/153 chars per part, Unicode (Bengali) 70/67.
export function smsSegments(text: string) {
  const unicode = [...text].some((ch) => ch.charCodeAt(0) > 127);
  const [single, multi] = unicode ? [70, 67] : [160, 153];
  const n = text.length;
  return { unicode, chars: n, segments: n === 0 ? 0 : n <= single ? 1 : Math.ceil(n / multi) };
}

const bdt = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "—" : `৳${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const newKey = () => crypto.randomUUID();

interface RechargeRow {
  id: string;
  status: "pending" | "approved" | "rejected";
  status_label: string;
  wallet_amount: string;
  fee_percent: string;
  fee: string;
  total_expected: string;
  amount_sent: string;
  sender_number: string;
  trx_id: string;
  submitted_at: string;
  rejection_reason: string | null;
}
interface WalletInfo {
  balance: string;
  price_per_segment: string | null;
  bulk_price_per_segment: string | null;
  sms_disabled: boolean;
  disabled_types: string[];
  disabled_message_bn: string | null;
  blocked: Record<string, number>;
  insufficient_message_bn: string | null;
  recharge: { enabled: boolean; switched_off?: boolean; bkash_number: string | null; instructions: string; fee_percent: string; min_amount: string; max_amount: string | null };
  recharges: RechargeRow[];
}

const RECHARGE_TONE: Record<RechargeRow["status"], BadgeTone> = { pending: "amber", approved: "green", rejected: "red" };

export function useWallet() {
  return useQuery({ queryKey: ["ws", "sms", "wallet"], queryFn: () => api<WalletInfo>("/workspace/sms/wallet/") });
}

/** Balance, warnings, recharge and the ledger. */
export function WalletCard() {
  const qc = useQueryClient();
  const isOwner = useActiveMembership()?.role === "owner";
  const w = useWallet();
  const [recharging, setRecharging] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const retry = useMutation({
    mutationFn: () => api<{ tried: number; sent: number; still_blocked: number }>("/workspace/sms/retry-blocked/", { method: "POST" }),
    onSuccess: (r) => {
      toast.success(`${r.sent} of ${r.tried} SMS sent${r.still_blocked ? ` · ${r.still_blocked} still waiting for balance` : ""}`);
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const d = w.data;
  const lowBalance = d?.blocked.insufficient_balance ?? 0;
  const lastRejected = d?.recharges.find((r) => r.status === "rejected");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wallet className="size-5 text-primary" /> SMS Wallet
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {w.isPending && <Skeleton className="h-28" />}
        {w.isError && <ErrorState error={w.error} onRetry={() => w.refetch()} />}
        {d && (
          <>
            {d.disabled_message_bn && (
              <p lang="bn" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
                {d.disabled_message_bn}
              </p>
            )}
            {lowBalance > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
                <span className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                  <span>
                    <span lang="bn">{d.insufficient_message_bn}</span> ({lowBalance} SMS waiting)
                  </span>
                </span>
                <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate()}>
                  <RotateCcw /> Send waiting SMS
                </Button>
              </div>
            )}
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Balance</p>
                <p className="tabular font-display text-4xl font-bold">{bdt(d.balance)}</p>
                <p className="text-xs text-muted-foreground">
                  {d.price_per_segment ? `${bdt(d.price_per_segment)} per SMS part · bulk ${bdt(d.bulk_price_per_segment)}` : "SMS prices not set by TurfBari yet"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setShowLedger(!showLedger)}>
                  {showLedger ? "Hide" : "Show"} transactions
                </Button>
                {isOwner && (
                  <Button onClick={() => setRecharging(true)}>
                    <Wallet /> Recharge Wallet
                  </Button>
                )}
              </div>
            </div>
            {lastRejected && (
              <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
                Recharge of {bdt(lastRejected.wallet_amount)} (TrxID {lastRejected.trx_id}) was rejected
                {lastRejected.rejection_reason ? `: ${lastRejected.rejection_reason}` : "."}
              </p>
            )}
            {d.recharges.length > 0 && (
              <div>
                <p className="mb-1 text-sm font-medium">Recharge requests</p>
                <ul className="divide-y rounded-lg border text-sm">
                  {d.recharges.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                      <span>
                        {bdt(r.wallet_amount)} <span className="text-muted-foreground">· sent {bdt(r.amount_sent)} · TrxID {r.trx_id}</span>
                      </span>
                      <Badge tone={RECHARGE_TONE[r.status]}>{r.status_label}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {showLedger && <Ledger />}
          </>
        )}
      </CardContent>
      {recharging && d && <RechargeDialog info={d} onClose={() => setRecharging(false)} />}
    </Card>
  );
}

function Ledger() {
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["ws", "sms", "ledger", page],
    queryFn: () =>
      api<Paginated<{ id: number; at: string; kind_label: string; amount: string; balance_after: string; note: string; segments: number; price_per_segment: string | null }>>(
        `/workspace/sms/wallet/ledger/?page=${page}`,
      ),
    placeholderData: keepPreviousData,
  });
  if (!list.data) return <Skeleton className="h-24" />;
  if (list.data.results.length === 0) return <p className="text-sm text-muted-foreground">No wallet transactions yet.</p>;
  return (
    <div>
      <Table>
        <thead>
          <tr>
            <th>When</th>
            <th>What</th>
            <th className="text-right">Amount</th>
            <th className="text-right">Balance</th>
          </tr>
        </thead>
        <tbody>
          {list.data.results.map((t) => (
            <tr key={t.id}>
              <td className="whitespace-nowrap text-xs">{new Date(t.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</td>
              <td className="text-sm">
                {t.kind_label}
                <span className="block text-xs text-muted-foreground">
                  {t.note}
                  {t.segments ? ` · ${t.segments} part${t.segments > 1 ? "s" : ""} × ${bdt(t.price_per_segment)}` : ""}
                </span>
              </td>
              <td className={cn("tabular text-right", Number(t.amount) < 0 ? "text-destructive" : "text-green-700 dark:text-green-400")}>
                {Number(t.amount) > 0 ? "+" : ""}
                {Number(t.amount).toFixed(2)}
              </td>
              <td className="tabular text-right">{bdt(t.balance_after)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      {list.data.count > 20 && (
        <div className="mt-2 flex justify-end gap-2">
          <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft />
          </Button>
          <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
            <ChevronRight />
          </Button>
        </div>
      )}
    </div>
  );
}

function RechargeDialog({ info, onClose }: { info: WalletInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ wallet_amount: "", amount_sent: "", sender_number: "", trx_id: "", note: "" });
  const amount = Number(form.wallet_amount) || 0;
  const pct = Number(info.recharge.fee_percent);
  // Shown for guidance; the server recomputes with exact decimals and checks the amount sent.
  const fee = Math.round(amount * pct) / 100;
  const total = amount + fee;
  const submit = useMutation({
    mutationFn: () => api<RechargeRow>("/workspace/sms/wallet/recharge/", { method: "POST", json: form }),
    onSuccess: () => {
      toast.success("Recharge request sent — TurfBari will verify the bKash payment and add the credit");
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
      onClose();
    },
  });
  const fields = submit.error instanceof ApiError ? submit.error.fields : null;
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  if (!info.recharge.enabled) {
    return (
      <Dialog open onClose={onClose} title="Recharge SMS Wallet">
        <div className="flex flex-col gap-3 text-sm">
          <p>
            {info.recharge.switched_off
              ? "TurfBari has paused wallet recharges for now."
              : "TurfBari hasn't set the bKash number for recharges yet."}{" "}
            Please contact TurfBari to add SMS credit.
          </p>
          <Button onClick={onClose}>OK</Button>
        </div>
      </Dialog>
    );
  }
  return (
    <Dialog open onClose={onClose} title="Recharge SMS Wallet" description="Send the total by bKash Send Money, then submit the details. Credit is added after TurfBari checks the payment.">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <FormField label="Wallet credit you want (৳)" hint={`Minimum ${bdt(info.recharge.min_amount)}${info.recharge.max_amount ? `, maximum ${bdt(info.recharge.max_amount)}` : ""}`} error={fields?.wallet_amount}>
          {(id) => <Input id={id} type="number" min={info.recharge.min_amount} step="0.01" required value={form.wallet_amount} onChange={set("wallet_amount")} />}
        </FormField>
        <div className="rounded-xl border-2 border-[#e2136e]/30 bg-[#e2136e]/5 p-4 text-sm">
          <dl className="grid grid-cols-[1fr_auto] gap-y-1">
            <dt>Requested wallet credit</dt>
            <dd className="tabular text-right">{bdt(amount)}</dd>
            <dt>Additional bKash charge ({info.recharge.fee_percent}%)</dt>
            <dd className="tabular text-right">{bdt(fee)}</dd>
            <dt className="font-semibold">Total bKash payment</dt>
            <dd className="tabular text-right font-bold">{bdt(total)}</dd>
          </dl>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded bg-[#e2136e] px-1.5 py-0.5 text-xs font-bold text-white">bKash</span>
            Send Money to <span className="font-mono text-base font-bold">{info.recharge.bkash_number}</span>
            <Button type="button" size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(info.recharge.bkash_number ?? "").then(() => toast.success("Copied"))}>
              <Copy />
            </Button>
          </div>
          {info.recharge.instructions && <p className="mt-2 whitespace-pre-line text-xs text-muted-foreground">{info.recharge.instructions}</p>}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Total amount sent (৳)" error={fields?.amount_sent}>
            {(id) => <Input id={id} type="number" step="0.01" required placeholder={total ? total.toFixed(2) : ""} value={form.amount_sent} onChange={set("amount_sent")} />}
          </FormField>
          <FormField label="bKash number you sent from" error={fields?.sender_number}>
            {(id) => <Input id={id} type="tel" required placeholder="01XXXXXXXXX" value={form.sender_number} onChange={set("sender_number")} />}
          </FormField>
          <FormField label="Transaction ID (TrxID)" error={fields?.trx_id}>
            {(id) => <Input id={id} required className="font-mono uppercase" value={form.trx_id} onChange={(e) => setForm({ ...form, trx_id: e.target.value.toUpperCase().replace(/\s/g, "") })} />}
          </FormField>
          <FormField label="Note (optional)">{(id) => <Input id={id} maxLength={200} value={form.note} onChange={set("note")} />}</FormField>
        </div>
        {submit.error && !fields && <p className="text-sm text-destructive">{errorText(submit.error)}</p>}
        {fields?.non_field_errors && <p className="text-sm text-destructive">{fields.non_field_errors[0]}</p>}
        <Button type="submit" disabled={submit.isPending || amount <= 0}>
          {submit.isPending && <Loader2 className="animate-spin" />} Submit recharge request
        </Button>
      </form>
    </Dialog>
  );
}

// ------------------------------------------------------------------ single SMS
export function SingleSmsCard() {
  const qc = useQueryClient();
  const w = useWallet();
  const [to, setTo] = useState("");
  const [body, setBody] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [key, setKey] = useState(newKey);
  const seg = smsSegments(body);
  const price = Number(w.data?.price_per_segment ?? 0);
  const cost = seg.segments * price;
  const send = useMutation({
    mutationFn: () =>
      api<{ status: string; status_label: string; provider_message: string; charged: string }>("/workspace/sms/send/", {
        method: "POST",
        json: { to, body, confirm: true, idempotency_key: key },
      }),
    onSuccess: (r) => {
      setConfirming(false);
      if (r.status === "sent") {
        toast.success(`SMS sent · ${bdt(r.charged)} charged`);
        setBody("");
        setTo("");
      } else toast.error(`${r.status_label}: ${r.provider_message}`);
      setKey(newKey());
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
    },
    onError: (e) => {
      setConfirming(false);
      toast.error(errorText(e));
    },
  });
  const enough = Number(w.data?.balance ?? 0) >= cost;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="size-5 text-primary" /> Send an SMS
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setConfirming(true);
          }}
        >
          <FormField label="Mobile number">{(id) => <Input id={id} type="tel" required placeholder="01XXXXXXXXX" value={to} onChange={(e) => setTo(e.target.value)} />}</FormField>
          <FormField label="Message (Bengali or English)">{(id) => <Textarea id={id} rows={4} required maxLength={1000} value={body} onChange={(e) => setBody(e.target.value)} />}</FormField>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              {seg.chars} characters · {seg.segments} SMS part{seg.segments === 1 ? "" : "s"} {seg.unicode && "(Bengali: 70 per part, 67 when longer)"}
            </span>
            <span>
              Estimated cost <strong className="text-foreground">{bdt(cost)}</strong> · Balance {bdt(w.data?.balance)}
            </span>
          </div>
          {!enough && body && <p lang="bn" className="text-sm text-destructive">{w.data && "আপনার SMS Wallet-এ পর্যাপ্ত ব্যালেন্স নেই। SMS পাঠাতে অনুগ্রহ করে Wallet Recharge করুন।"}</p>}
          <Button type="submit" className="self-end" disabled={!to || !body || !enough || !w.data?.price_per_segment}>
            <Send /> Send SMS
          </Button>
        </form>
      </CardContent>
      {confirming && (
        <Dialog open onClose={() => setConfirming(false)} title="Send this SMS?" description={`To ${to} · ${seg.segments} part(s) · ${bdt(cost)} from your wallet`}>
          <div className="flex flex-col gap-3">
            <p className="whitespace-pre-wrap rounded-md bg-secondary p-3 text-sm">{body}</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button disabled={send.isPending} onClick={() => send.mutate()}>
                {send.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send and charge {bdt(cost)}
              </Button>
            </div>
          </div>
        </Dialog>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ bulk SMS
const STATUSES = [
  ["confirmed", "Confirmed"],
  ["completed", "Played"],
  ["pending", "Awaiting verification"],
  ["cancelled", "Cancelled"],
] as const;
const VARIABLES = ["customer_name", "turf_name", "booking_date", "booking_time", "booking_id", "customer_phone"];

interface Preview {
  valid: number;
  invalid: number;
  invalid_examples: string[];
  duplicates: number;
  segments: number;
  price_per_segment: string | null;
  estimated_cost: string;
  balance: string;
  enough_balance: boolean;
  samples: { to: string; text: string; segments: number }[];
}
interface Campaign {
  id: string;
  name: string;
  status: "sending" | "completed" | "cancelled";
  status_label: string;
  created_at: string;
  recipients: number;
  sent: number;
  failed: number;
  pending: number;
  not_sent: number;
  segments: number;
  cost: string;
  estimated_cost: string;
}

export function BulkSmsSection() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    template: "প্রিয় {{customer_name}}, {{turf_name}}-এ আপনার জন্য বিশেষ অফার রয়েছে। বিস্তারিত জানতে যোগাযোগ করুন।",
    from_bookings: true,
    booking_from: "",
    booking_to: "",
    booking_statuses: ["confirmed", "completed"] as string[],
    all_customers: false,
    numbers: "",
    csv: "",
  });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [key, setKey] = useState(newKey);
  const payload = useMemo(
    () => ({ ...form, booking_from: form.booking_from || null, booking_to: form.booking_to || null }),
    [form],
  );
  const check = useMutation({
    mutationFn: () => api<Preview>("/workspace/sms/campaigns/preview/", { method: "POST", json: payload }),
    onSuccess: setPreview,
    onError: (e) => toast.error(errorText(e)),
  });
  const start = useMutation({
    mutationFn: () => api<Campaign>("/workspace/sms/campaigns/", { method: "POST", json: { ...payload, confirm: true, idempotency_key: key } }),
    onSuccess: (c) => {
      toast.success(`“${c.name}” started — ${c.recipients} SMS`);
      setPreview(null);
      setKey(newKey());
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const set = (patch: Partial<typeof form>) => {
    setForm({ ...form, ...patch });
    setPreview(null);
  };
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Megaphone className="size-5 text-primary" /> Bulk SMS campaign
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FormField label="Campaign name">{(id) => <Input id={id} maxLength={120} placeholder="e.g. Eid offer" value={form.name} onChange={(e) => set({ name: e.target.value })} />}</FormField>
          <FormField label="Message" hint={`Personalise with: ${VARIABLES.map((v) => `{{${v}}}`).join(" ")}`}>
            {(id) => <Textarea id={id} rows={4} maxLength={1000} value={form.template} onChange={(e) => set({ template: e.target.value })} />}
          </FormField>
          <div className="flex flex-wrap gap-1">
            {VARIABLES.map((v) => (
              <button key={v} type="button" className="rounded-full border px-2 py-0.5 font-mono text-xs hover:bg-secondary" onClick={() => set({ template: `${form.template}{{${v}}}` })}>
                {`{{${v}}}`}
              </button>
            ))}
          </div>
          <fieldset className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2">
            <legend className="px-1 text-sm font-medium">Who gets it</legend>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Checkbox label="Customers from my bookings" checked={form.from_bookings} onChange={(e) => set({ from_bookings: e.target.checked })} />
              {form.from_bookings && (
                <div className="grid gap-2 pl-6 sm:grid-cols-2">
                  <FormField label="Booked from">{(id) => <Input id={id} type="date" value={form.booking_from} onChange={(e) => set({ booking_from: e.target.value })} />}</FormField>
                  <FormField label="Booked until">{(id) => <Input id={id} type="date" value={form.booking_to} onChange={(e) => set({ booking_to: e.target.value })} />}</FormField>
                  <div className="flex flex-wrap gap-3 sm:col-span-2">
                    {STATUSES.map(([value, label]) => (
                      <Checkbox
                        key={value}
                        label={label}
                        checked={form.booking_statuses.includes(value)}
                        onChange={(e) =>
                          set({ booking_statuses: e.target.checked ? [...form.booking_statuses, value] : form.booking_statuses.filter((s) => s !== value) })
                        }
                      />
                    ))}
                  </div>
                </div>
              )}
              <Checkbox label="All my saved customers" checked={form.all_customers} onChange={(e) => set({ all_customers: e.target.checked })} />
            </div>
            <FormField label="Extra numbers (comma or new line)">
              {(id) => <Textarea id={id} rows={3} placeholder="01712345678, 01812345678" value={form.numbers} onChange={(e) => set({ numbers: e.target.value })} />}
            </FormField>
            <FormField label="CSV contact list" hint="Columns: phone (or mobile), optional name. Max 300 KB.">
              {(id) => (
                <label htmlFor={id} className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed p-3 text-sm hover:bg-secondary">
                  <Upload className="size-4" /> {form.csv ? `${form.csv.split(/\r?\n/).filter(Boolean).length} lines loaded` : "Choose a .csv file"}
                  <input
                    id={id}
                    type="file"
                    accept=".csv,text/csv"
                    className="sr-only"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (file.size > 300_000) return toast.error("The CSV is too large (max 300 KB).");
                      void file.text().then((text) => set({ csv: text }));
                    }}
                  />
                  {form.csv && (
                    <button type="button" aria-label="Remove CSV" onClick={(e) => (e.preventDefault(), set({ csv: "" }))}>
                      <X className="size-4" />
                    </button>
                  )}
                </label>
              )}
            </FormField>
          </fieldset>
          <Button variant="outline" className="self-start" disabled={check.isPending || !form.template.trim()} onClick={() => check.mutate()}>
            {check.isPending && <Loader2 className="animate-spin" />} Check recipients &amp; cost
          </Button>
          {preview && (
            <div className="flex flex-col gap-3 rounded-lg border p-3 text-sm">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Metric label="Valid recipients" value={preview.valid} />
                <Metric label="Invalid / duplicate" value={`${preview.invalid} / ${preview.duplicates}`} />
                <Metric label="SMS parts" value={preview.segments} />
                <Metric label="Estimated charge" value={bdt(preview.estimated_cost)} hint={`Balance ${bdt(preview.balance)}`} />
              </div>
              {preview.invalid_examples.length > 0 && <p className="text-xs text-muted-foreground">Invalid: {preview.invalid_examples.join(", ")}</p>}
              <div>
                <p className="mb-1 font-medium">Preview</p>
                <ul className="flex flex-col gap-2">
                  {preview.samples.map((s) => (
                    <li key={s.to} className="rounded-md bg-secondary p-2">
                      <span className="font-mono text-xs text-muted-foreground">
                        {s.to} · {s.segments} part(s)
                      </span>
                      <p className="whitespace-pre-wrap">{s.text}</p>
                    </li>
                  ))}
                </ul>
              </div>
              {!preview.enough_balance && (
                <p lang="bn" className="text-destructive">
                  আপনার SMS Wallet-এ পর্যাপ্ত ব্যালেন্স নেই। SMS পাঠাতে অনুগ্রহ করে Wallet Recharge করুন।
                </p>
              )}
              <Button
                className="self-end"
                disabled={!preview.enough_balance || preview.valid === 0 || !form.name.trim() || start.isPending}
                onClick={() => window.confirm(`Send to ${preview.valid} customers and charge about ${bdt(preview.estimated_cost)}?`) && start.mutate()}
              >
                {start.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send to {preview.valid} customers
              </Button>
              {!form.name.trim() && <p className="text-right text-xs text-muted-foreground">Give the campaign a name to send.</p>}
            </div>
          )}
        </CardContent>
      </Card>
      <CampaignHistory />
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-md border p-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="tabular font-bold">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

const CAMPAIGN_TONE: Record<Campaign["status"], BadgeTone> = { sending: "blue", completed: "green", cancelled: "neutral" };

function CampaignHistory() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const list = useQuery({
    queryKey: ["ws", "sms", "campaigns", page, status],
    queryFn: () => api<Paginated<Campaign>>(`/workspace/sms/campaigns/?page=${page}&status=${status}`),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.results.some((c) => c.status === "sending") ? 5000 : false),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api(`/workspace/sms/campaigns/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Campaign cancelled — unsent messages won't be charged");
      qc.invalidateQueries({ queryKey: ["ws", "sms"] });
    },
  });
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Campaign history</CardTitle>
          <select aria-label="Status" className="rounded-md border bg-background px-2 py-1 text-sm" value={status} onChange={(e) => (setStatus(e.target.value), setPage(1))}>
            <option value="">All</option>
            <option value="sending">Sending</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </CardHeader>
      <CardContent className="p-2 sm:p-4">
        {!list.data && <Skeleton className="h-24" />}
        {list.data?.results.length === 0 && <EmptyState icon={<Megaphone />} title="No campaigns yet" />}
        {list.data && list.data.results.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th className="text-right">Recipients</th>
                <th className="text-right">Sent</th>
                <th className="text-right">Failed</th>
                <th className="text-right">Parts</th>
                <th className="text-right">Cost</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.data.results.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.name}
                    <span className="block text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</span>
                  </td>
                  <td className="tabular text-right">{c.recipients}</td>
                  <td className="tabular text-right">{c.sent}</td>
                  <td className="tabular text-right">{c.failed + c.not_sent}</td>
                  <td className="tabular text-right">{c.segments}</td>
                  <td className="tabular text-right">{bdt(c.cost)}</td>
                  <td>
                    <Badge tone={CAMPAIGN_TONE[c.status]}>{c.status_label}</Badge>
                    {c.status === "sending" && <span className="block text-xs text-muted-foreground">{c.pending} waiting</span>}
                  </td>
                  <td className="text-right">
                    {c.status === "sending" && (
                      <Button size="sm" variant="ghost" onClick={() => window.confirm("Stop this campaign? Messages not yet sent are dropped and not charged.") && cancel.mutate(c.id)}>
                        Stop
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && list.data.count > 20 && (
          <div className="mt-2 flex justify-end gap-2">
            <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft />
            </Button>
            <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
