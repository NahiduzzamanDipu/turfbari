import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, Loader2, Wallet, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import type { Paginated } from "@/lib/types";
import { cn } from "@/lib/utils";

const bdt = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "—" : `৳${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "—");

function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2" role="tablist">
      {tabs.map(([k, label]) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={value === k}
          onClick={() => onChange(k)}
          className={cn("rounded-full border px-3 py-1.5 text-sm font-medium", value === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function AdminSmsWalletPage() {
  const [tab, setTab] = useState("recharges");
  return (
    <>
      <PageHeader title="SMS wallets" description="Prepaid SMS: verify bKash recharges, set prices, and control each account's SMS." />
      <Tabs
        tabs={[
          ["recharges", "Recharge requests"],
          ["accounts", "Accounts"],
          ["pricing", "Pricing"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "recharges" && <RechargeRequests />}
      {tab === "accounts" && <Accounts />}
      {tab === "pricing" && <Pricing />}
    </>
  );
}

// ------------------------------------------------------------------ recharges
interface Recharge {
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
  note: string;
  submitted_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
  turf: { id: string; name: string };
  owner: { name: string; email: string; phone: string } | null;
  reviewed_by: string | null;
}
const RTONE: Record<Recharge["status"], BadgeTone> = { pending: "amber", approved: "green", rejected: "red" };

function RechargeRequests() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [rejecting, setRejecting] = useState<Recharge | null>(null);
  const [reason, setReason] = useState("");
  const list = useQuery({
    queryKey: ["admin", "recharges", status, page],
    queryFn: () => api<Paginated<Recharge> & { counts: Record<string, number> }>(`/admin/sms/recharges/?status=${status}&page=${page}`),
    placeholderData: keepPreviousData,
  });
  const decide = useMutation({
    mutationFn: ({ r, decision, reason }: { r: Recharge; decision: "approve" | "reject"; reason?: string }) =>
      api<Recharge>(`/admin/sms/recharges/${r.id}/${decision}/`, { method: "POST", json: { reason: reason ?? "" } }),
    onSuccess: (r) => {
      toast.success(r.status === "approved" ? `${bdt(r.wallet_amount)} added to ${r.turf.name}'s wallet` : "Recharge rejected");
      setRejecting(null);
      setReason("");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <>
      <Tabs
        tabs={(["pending", "approved", "rejected"] as const).map((s) => [s, `${s[0]!.toUpperCase()}${s.slice(1)} (${list.data?.counts[s] ?? 0})`])}
        value={status}
        onChange={(s) => {
          setStatus(s);
          setPage(1);
        }}
      />
      {list.isPending && <Skeleton className="h-40" />}
      {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.results.length === 0 && (
        <Card>
          <CardContent>
            <EmptyState icon={<Wallet />} title="Nothing here" />
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 xl:grid-cols-2">
        {list.data?.results.map((r) => {
          const mismatch = Math.abs(Number(r.amount_sent) - Number(r.total_expected)) > 1;
          return (
            <Card key={r.id} className={cn(r.status === "pending" && "border-l-4 border-l-amber-500")}>
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">{r.turf.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {r.owner ? `${r.owner.name || r.owner.email} · ${r.owner.phone || r.owner.email}` : "No owner"} · {when(r.submitted_at)}
                    </p>
                  </div>
                  <Badge tone={RTONE[r.status]}>{r.status_label}</Badge>
                </div>
                <dl className="grid grid-cols-2 gap-2 rounded-lg bg-secondary/60 p-3 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-muted-foreground">Wallet credit</dt>
                    <dd className="tabular font-bold">{bdt(r.wallet_amount)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">bKash charge ({r.fee_percent}%)</dt>
                    <dd className="tabular">{bdt(r.fee)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Expected total</dt>
                    <dd className="tabular">{bdt(r.total_expected)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Amount sent</dt>
                    <dd className={cn("tabular font-semibold", mismatch && "text-destructive")}>{bdt(r.amount_sent)}</dd>
                  </div>
                </dl>
                <p className="text-sm">
                  From <span className="font-mono">{r.sender_number}</span> · TrxID <span className="font-mono font-semibold">{r.trx_id}</span>
                  {r.note && <span className="block text-xs text-muted-foreground">Note: {r.note}</span>}
                </p>
                {r.reviewed_by && (
                  <p className="text-xs text-muted-foreground">
                    {r.status === "approved" ? "Approved" : "Rejected"} by {r.reviewed_by} · {when(r.reviewed_at)}
                    {r.rejection_reason && ` — “${r.rejection_reason}”`}
                  </p>
                )}
                {r.status === "pending" && (
                  <div className="flex gap-2">
                    <Button
                      className="flex-1"
                      disabled={decide.isPending}
                      onClick={() =>
                        window.confirm(`Have you seen ${bdt(r.amount_sent)} (TrxID ${r.trx_id}) in the bKash account? ${bdt(r.wallet_amount)} will be added to the wallet.`) &&
                        decide.mutate({ r, decision: "approve" })
                      }
                    >
                      <Check /> Approve
                    </Button>
                    <Button className="flex-1" variant="outline" onClick={() => setRejecting(r)}>
                      <X /> Reject
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      {list.data && list.data.count > 20 && (
        <div className="mt-4 flex justify-end gap-2">
          <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft />
          </Button>
          <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
            <ChevronRight />
          </Button>
        </div>
      )}
      {rejecting && (
        <Dialog open onClose={() => setRejecting(null)} title="Reject this recharge?" description="Nothing is credited. The owner sees the reason and gets an SMS.">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              decide.mutate({ r: rejecting, decision: "reject", reason });
            }}
          >
            <FormField label="Reason (optional)">{(id) => <Textarea id={id} rows={2} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />}</FormField>
            <Button type="submit" variant="destructive" disabled={decide.isPending}>
              Reject recharge
            </Button>
          </form>
        </Dialog>
      )}
    </>
  );
}

// ------------------------------------------------------------------ accounts
interface WalletRow {
  turf: { id: string; name: string };
  balance: string;
  recharged: string;
  sms_spent: string;
  sms_enabled: boolean;
}
function Accounts() {
  const wallets = useQuery({ queryKey: ["admin", "wallets"], queryFn: () => api<WalletRow[]>("/admin/sms/wallets/") });
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<WalletRow | null>(null);
  const rows = (wallets.data ?? []).filter((w) => w.turf.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-2 sm:p-4">
        <Input placeholder="Search turf" aria-label="Search turf" value={q} onChange={(e) => setQ(e.target.value)} />
        {wallets.isPending && <Skeleton className="h-40" />}
        {rows.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th>Turf</th>
                <th className="text-right">Balance</th>
                <th className="text-right">Recharged</th>
                <th className="text-right">SMS spent</th>
                <th>SMS</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.turf.id}>
                  <td className="font-medium">{w.turf.name}</td>
                  <td className="tabular text-right">{bdt(w.balance)}</td>
                  <td className="tabular text-right">{bdt(w.recharged)}</td>
                  <td className="tabular text-right">{bdt(w.sms_spent)}</td>
                  <td>{w.sms_enabled ? <Badge tone="green">On</Badge> : <Badge tone="red">Off</Badge>}</td>
                  <td className="text-right">
                    <Button size="sm" variant="outline" onClick={() => setOpen(w)}>
                      Manage
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </CardContent>
      {open && <AccountDialog turfId={open.turf.id} name={open.turf.name} onClose={() => setOpen(null)} />}
    </Card>
  );
}

interface TurfSms {
  controls: Record<string, boolean | number>;
  controls_updated_at: string | null;
  controls_updated_by: string | null;
  balance: string;
  blocked: Record<string, number>;
  ledger: { id: number; at: string; kind_label: string; amount: string; balance_after: string; note: string }[];
}
const SWITCHES: [string, string][] = [
  ["booking_confirmed", "Booking confirmation (online)"],
  ["owner_booking", "Booking made by the turf"],
  ["rejection_cancellation", "Payment rejected / booking cancelled"],
  ["reminder", "Booking reminder"],
  ["single", "Single SMS"],
  ["bulk", "Bulk SMS"],
];
const BLOCK_LABEL: Record<string, string> = {
  insufficient_balance: "low balance",
  account_disabled: "account SMS off",
  type_disabled: "type off",
  no_pricing: "no price set",
  monthly_limit: "monthly limit",
  cancelled: "cancelled campaign",
};

function AccountDialog({ turfId, name, onClose }: { turfId: string; name: string; onClose: () => void }) {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["admin", "turf-sms", turfId], queryFn: () => api<TurfSms>(`/admin/turfs/${turfId}/sms/`) });
  const [adjust, setAdjust] = useState({ amount: "", reason: "" });
  const save = useMutation({
    mutationFn: (patch: Record<string, boolean | number>) => api<TurfSms>(`/admin/turfs/${turfId}/sms/`, { method: "PUT", json: patch }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "turf-sms", turfId], d);
      qc.invalidateQueries({ queryKey: ["admin", "wallets"] });
      toast.success("SMS controls saved");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const credit = useMutation({
    mutationFn: () => api<TurfSms>(`/admin/turfs/${turfId}/sms/adjust/`, { method: "POST", json: { ...adjust, idempotency_key: crypto.randomUUID() } }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "turf-sms", turfId], d);
      qc.invalidateQueries({ queryKey: ["admin", "wallets"] });
      setAdjust({ amount: "", reason: "" });
      toast.success("Wallet updated");
    },
  });
  const d = data.data;
  const c = d?.controls;
  return (
    <Dialog open onClose={onClose} title={`${name} — SMS`} wide>
      {!d && <Skeleton className="h-48" />}
      {d && c && (
        <div className="flex flex-col gap-5 text-sm">
          <section>
            <h3 className="mb-2 font-semibold">SMS permissions</h3>
            <Checkbox label="All SMS for this account" checked={Boolean(c.all_enabled)} disabled={save.isPending} onChange={(e) => save.mutate({ all_enabled: e.target.checked })} />
            <div className={cn("mt-2 grid gap-2 pl-6 sm:grid-cols-2", !c.all_enabled && "opacity-50")}>
              {SWITCHES.map(([k, label]) => (
                <Checkbox key={k} label={label} checked={Boolean(c[k])} disabled={save.isPending || !c.all_enabled} onChange={(e) => save.mutate({ [k]: e.target.checked })} />
              ))}
            </div>
            <div className="mt-3 flex items-end gap-2">
              <FormField label="Monthly SMS limit (0 = none)">
                {(id) => <Input id={id} type="number" min={0} className="w-32" defaultValue={Number(c.monthly_limit)} onBlur={(e) => Number(e.target.value) !== c.monthly_limit && save.mutate({ monthly_limit: Number(e.target.value) })} />}
              </FormField>
            </div>
            {d.controls_updated_by && (
              <p className="mt-2 text-xs text-muted-foreground">
                Last changed by {d.controls_updated_by} · {when(d.controls_updated_at)}
              </p>
            )}
            {Object.keys(d.blocked).length > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Blocked SMS: {Object.entries(d.blocked).map(([k, n]) => `${n} ${BLOCK_LABEL[k] ?? k}`).join(" · ")}
              </p>
            )}
          </section>
          <section>
            <h3 className="mb-2 font-semibold">Wallet · {bdt(d.balance)}</h3>
            <form
              className="flex flex-col gap-2 sm:flex-row sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                credit.mutate();
              }}
            >
              <FormField label="Amount (− to take back)">{(id) => <Input id={id} type="number" step="0.01" required value={adjust.amount} onChange={(e) => setAdjust({ ...adjust, amount: e.target.value })} />}</FormField>
              <FormField label="Reason (kept in the ledger)" className="flex-1">
                {(id) => <Input id={id} required minLength={5} maxLength={200} value={adjust.reason} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />}
              </FormField>
              <Button type="submit" disabled={credit.isPending}>
                Apply
              </Button>
            </form>
            {credit.error && <p className="mt-1 text-xs text-destructive">{errorText(credit.error)}</p>}
            <ul className="mt-3 max-h-56 divide-y overflow-y-auto rounded-md border">
              {d.ledger.map((t) => (
                <li key={t.id} className="flex justify-between gap-2 px-3 py-1.5">
                  <span>
                    {t.kind_label}
                    <span className="block text-xs text-muted-foreground">
                      {t.note} · {when(t.at)}
                    </span>
                  </span>
                  <span className={cn("tabular", Number(t.amount) < 0 ? "text-destructive" : "text-green-700 dark:text-green-400")}>{Number(t.amount).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Dialog>
  );
}

// ------------------------------------------------------------------ pricing
interface PricingRow {
  id: number;
  price_per_segment: string;
  masking_price_per_segment: string;
  bulk_price_per_segment: string;
  effective_from: string;
  note: string;
}
function Pricing() {
  const qc = useQueryClient();
  const data = useQuery({
    queryKey: ["admin", "sms-pricing"],
    queryFn: () => api<{ current: PricingRow | null; scheduled: PricingRow[]; history: PricingRow[]; sender_is_masking: boolean }>("/admin/sms/pricing/"),
  });
  const [form, setForm] = useState({ price_per_segment: "", masking_price_per_segment: "", bulk_price_per_segment: "", effective_from: "", note: "" });
  const save = useMutation({
    mutationFn: () =>
      api("/admin/sms/pricing/", {
        method: "POST",
        json: { ...form, effective_from: form.effective_from ? new Date(form.effective_from).toISOString() : undefined },
      }),
    onSuccess: () => {
      toast.success("SMS price saved — applies to new messages from its effective time");
      qc.invalidateQueries({ queryKey: ["admin", "sms-pricing"] });
    },
  });
  const masking = useMutation({
    mutationFn: (v: boolean) => api("/admin/sms/pricing/", { method: "POST", json: { sender_is_masking: v } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "sms-pricing"] }),
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  const d = data.data;
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Current price (BDT per SMS part)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {!d && <Skeleton className="h-24" />}
          {d && !d.current && <p className="text-destructive">No price set — turf SMS are blocked until you set one.</p>}
          {d?.current && (
            <dl className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Non-masking</dt>
                <dd className="tabular text-lg font-bold">{bdt(d.current.price_per_segment)}</dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Masking</dt>
                <dd className="tabular text-lg font-bold">{bdt(d.current.masking_price_per_segment)}</dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Bulk</dt>
                <dd className="tabular text-lg font-bold">{bdt(d.current.bulk_price_per_segment)}</dd>
              </div>
            </dl>
          )}
          {d && (
            <Checkbox label="Our sender ID is a masking (brand name) sender — charge the masking price" checked={d.sender_is_masking} onChange={(e) => masking.mutate(e.target.checked)} />
          )}
          <p className="text-xs text-muted-foreground">
            A Bengali SMS part holds 70 characters (67 when longer); English 160 (153). Every charge keeps the price it used, so changing the price never changes history.
          </p>
          {d && d.history.length > 0 && (
            <ul className="divide-y rounded-md border text-xs">
              {d.history.map((p) => (
                <li key={p.id} className="flex justify-between px-3 py-1.5">
                  <span>
                    {when(p.effective_from)} {p.note && `· ${p.note}`}
                  </span>
                  <span className="tabular">
                    {p.price_per_segment} / {p.masking_price_per_segment} / {p.bulk_price_per_segment}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>New price</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            {(
              [
                ["price_per_segment", "Non-masking"],
                ["masking_price_per_segment", "Masking"],
                ["bulk_price_per_segment", "Bulk"],
              ] as const
            ).map(([k, label]) => (
              <FormField key={k} label={`${label} (৳/part)`} error={fields?.[k]}>
                {(id) => <Input id={id} type="number" min={0} step="0.0001" required value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />}
              </FormField>
            ))}
            <FormField label="Effective from (blank = now)" className="sm:col-span-2">
              {(id) => <Input id={id} type="datetime-local" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />}
            </FormField>
            <FormField label="Note">{(id) => <Input id={id} maxLength={200} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />}</FormField>
            <Button type="submit" className="sm:col-span-3" disabled={save.isPending}>
              {save.isPending && <Loader2 className="animate-spin" />} Save price
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ finance
interface Finance {
  sms_wallets: { total_balance: string; sms_charged: string; segments_billed: number; admin_credit: string };
  recharges: { total: number; pending: number; pending_amount: string; approved: number; approved_amount: string; bkash_charges_collected: string; rejected: number };
  subscriptions: { pending: number; pending_amount: string; approved: number; received: string; rejected: number };
  platform_sms: { sent: number; segments: number; cost: string };
  top_sms_spenders_30d: { turf: string; turf_id: string; spent: string; segments: number }[];
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="tabular mt-1 font-display text-2xl font-bold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function AdminFinancePage() {
  const data = useQuery({ queryKey: ["admin", "finance"], queryFn: () => api<Finance>("/admin/finance/") });
  const f = data.data;
  return (
    <>
      <PageHeader title="Finance" description="Real numbers only. SMS wallet money, bKash charges and subscription revenue are kept separate; unverified payments are not counted as received." />
      {data.isPending && <Skeleton className="h-64" />}
      {data.isError && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
      {f && (
        <div className="flex flex-col gap-6">
          <section>
            <h2 className="mb-2 font-semibold">SMS wallets (customers' prepaid money)</h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Balance held for turfs" value={bdt(f.sms_wallets.total_balance)} />
              <Stat label="SMS charged (net of refunds)" value={bdt(f.sms_wallets.sms_charged)} hint={`${f.sms_wallets.segments_billed} SMS parts`} />
              <Stat label="Approved recharges" value={bdt(f.recharges.approved_amount)} hint={`${f.recharges.approved} requests`} />
              <Stat label="Credit added by TurfBari" value={bdt(f.sms_wallets.admin_credit)} />
            </div>
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Recharge requests</h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Pending" value={f.recharges.pending} hint={`${bdt(f.recharges.pending_amount)} — not counted until approved`} />
              <Stat label="Rejected" value={f.recharges.rejected} />
              <Stat label="All requests" value={f.recharges.total} />
              <Stat label="bKash charges collected" value={bdt(f.recharges.bkash_charges_collected)} hint="Separate from wallet balance" />
            </div>
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Subscription payments</h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Received (verified)" value={bdt(f.subscriptions.received)} hint={`${f.subscriptions.approved} payments`} />
              <Stat label="Pending verification" value={f.subscriptions.pending} hint={`${bdt(f.subscriptions.pending_amount)} not yet counted`} />
              <Stat label="Rejected" value={f.subscriptions.rejected} />
              <Stat label="TurfBari's own SMS" value={bdt(f.platform_sms.cost)} hint={`${f.platform_sms.sent} sent · ${f.platform_sms.segments} parts (platform expense)`} />
            </div>
          </section>
          <Card>
            <CardHeader>
              <CardTitle>Top SMS spenders (30 days)</CardTitle>
            </CardHeader>
            <CardContent>
              {f.top_sms_spenders_30d.length === 0 ? (
                <p className="text-sm text-muted-foreground">No SMS charges yet.</p>
              ) : (
                <Table>
                  <tbody>
                    {f.top_sms_spenders_30d.map((r) => (
                      <tr key={r.turf_id}>
                        <td>{r.turf}</td>
                        <td className="tabular text-right">{r.segments} parts</td>
                        <td className="tabular text-right font-semibold">{bdt(r.spent)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
