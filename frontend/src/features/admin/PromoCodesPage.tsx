import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, History, Loader2, Pencil, Plus, TicketPercent } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { fmtPlainDate } from "@/features/workspace/SubscriptionBanner";
import { ApiError, api } from "@/lib/api";
import type { PromoCode } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";

type PromoForm = {
  code: string;
  campaign_name: string;
  description: string;
  discount_type: "percent" | "fixed";
  percent_off: string;
  amount_off: string;
  max_discount: string;
  min_amount: string;
  is_active: boolean;
  valid_from: string;
  valid_until: string;
  max_uses: string;
  max_per_account: string;
  new_registrations_only: boolean;
  plans: string[];
  reservation_hours: string;
};

const EMPTY: PromoForm = {
  code: "",
  campaign_name: "",
  description: "",
  discount_type: "percent",
  percent_off: "10",
  amount_off: "",
  max_discount: "",
  min_amount: "",
  is_active: true,
  valid_from: "",
  valid_until: "",
  max_uses: "",
  max_per_account: "1",
  new_registrations_only: false,
  plans: [],
  reservation_hours: "72",
};

const PLAN_LABELS: Record<string, string> = { monthly: "Monthly", half_yearly: "Half-yearly", yearly: "Yearly" };

function promoStatus(p: PromoCode): { label: string; tone: BadgeTone } {
  if (p.is_archived) return { label: "Archived", tone: "neutral" };
  if (!p.is_active) return { label: "Off", tone: "neutral" };
  if (p.is_running) return { label: "Live", tone: "green" };
  const today = new Date().toISOString().slice(0, 10);
  if (p.valid_from && p.valid_from > today) return { label: "Scheduled", tone: "blue" };
  if (p.valid_until && p.valid_until < today) return { label: "Expired", tone: "red" };
  return { label: "Used up", tone: "amber" };
}

function validText(p: PromoCode): string {
  if (!p.valid_from && !p.valid_until) return "Always";
  return `${p.valid_from ? fmtPlainDate(p.valid_from) : "Now"} – ${p.valid_until ? fmtPlainDate(p.valid_until) : "no end"}`;
}

export function AdminPromoCodesPage() {
  const qc = useQueryClient();
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<PromoCode | "new" | null>(null);
  const [history, setHistory] = useState<PromoCode | null>(null);
  const codes = useQuery({
    queryKey: ["admin", "promo-codes", archived],
    queryFn: () => api<PromoCode[]>(`/admin/promo-codes/${archived ? "?archived=1" : ""}`),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "promo-codes"] });
  const patch = useMutation({
    mutationFn: ({ p, body }: { p: PromoCode; body: Partial<PromoCode> }) => api(`/admin/promo-codes/${p.id}/`, { method: "PATCH", json: body }),
    onSuccess: () => refresh(),
    onError: (e) => toast.error(errorText(e)),
  });
  const list = codes.data ?? [];
  const totals = list.reduce(
    (t, p) => ({ uses: t.uses + p.stats.redeemed, discount: t.discount + Number(p.stats.total_discount), reserved: t.reserved + p.stats.reserved }),
    { uses: 0, discount: 0, reserved: 0 },
  );

  return (
    <>
      <PageHeader
        title="Promo codes"
        description="Marketing discounts for new turf registrations and plan purchases. The server always calculates the discount; a code is only counted as used once TurfBari approves the payment."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus /> New promo code
          </Button>
        }
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <StatCard label="Paid uses" value={totals.uses} icon={<TicketPercent />} />
        <StatCard label="Reserved (awaiting payment check)" value={totals.reserved} />
        <StatCard label="Total discount given" value={formatBDT(totals.discount)} />
      </div>
      <Card>
        <CardContent className="pt-4">
          <div className="mb-3 flex justify-end">
            <Checkbox label="Show archived" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
          </div>
          {codes.isPending && <Skeleton className="h-48" />}
          {codes.isError && <ErrorState error={codes.error} onRetry={() => codes.refetch()} />}
          {codes.data && list.length === 0 && (
            <EmptyState icon={<TicketPercent />} title="No promo codes yet">
              Create one, e.g. TURFSTART20 for 20% off a new registration.
            </EmptyState>
          )}
          {list.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Discount</th>
                  <th>For</th>
                  <th className="text-right">Used</th>
                  <th className="text-right">Remaining</th>
                  <th className="text-right">Discount given</th>
                  <th>Valid</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((p) => {
                  const st = promoStatus(p);
                  return (
                    <tr key={p.id}>
                      <td>
                        <span className="font-mono font-semibold">{p.code}</span>
                        {p.campaign_name && <span className="block text-xs text-muted-foreground">{p.campaign_name}</span>}
                      </td>
                      <td>{p.label}</td>
                      <td className="text-xs">
                        {p.new_registrations_only ? "New registrations" : "Registrations & plans"}
                        <span className="block text-muted-foreground">{p.plans.length ? p.plans.map((x) => PLAN_LABELS[x] ?? x).join(", ") : "All plans"}</span>
                      </td>
                      <td className="tabular text-right">
                        {p.stats.redeemed}
                        {p.stats.reserved > 0 && <span className="block text-xs text-muted-foreground">+{p.stats.reserved} reserved</span>}
                      </td>
                      <td className="tabular text-right">{p.stats.remaining ?? "∞"}</td>
                      <td className="tabular text-right">{formatBDT(p.stats.total_discount)}</td>
                      <td className="whitespace-nowrap text-xs">{validText(p)}</td>
                      <td>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </td>
                      <td className="whitespace-nowrap text-right">
                        <Button size="sm" variant="ghost" aria-label={`Usage history of ${p.code}`} onClick={() => setHistory(p)}>
                          <History />
                        </Button>
                        <Button size="sm" variant="ghost" aria-label={`Edit ${p.code}`} onClick={() => setEditing(p)}>
                          <Pencil />
                        </Button>
                        {!p.is_archived && (
                          <>
                            <Button size="sm" variant="outline" disabled={patch.isPending} onClick={() => patch.mutate({ p, body: { is_active: !p.is_active } })}>
                              {p.is_active ? "Turn off" : "Turn on"}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Archive ${p.code}`}
                              onClick={() => window.confirm(`Archive ${p.code}? It can never be used again; its history is kept.`) && patch.mutate({ p, body: { is_archived: true } })}
                            >
                              <Archive />
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
      {editing && <PromoDialog promo={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} />}
      {history && <HistoryDialog promo={history} onClose={() => setHistory(null)} />}
    </>
  );
}

function PromoDialog({ promo, onClose, onSaved }: { promo: PromoCode | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<PromoForm>(
    promo
      ? {
          code: promo.code,
          campaign_name: promo.campaign_name,
          description: promo.description,
          discount_type: promo.discount_type,
          percent_off: String(promo.percent_off || ""),
          amount_off: Number(promo.amount_off) ? String(Number(promo.amount_off)) : "",
          max_discount: promo.max_discount ? String(Number(promo.max_discount)) : "",
          min_amount: promo.min_amount ? String(Number(promo.min_amount)) : "",
          is_active: promo.is_active,
          valid_from: promo.valid_from ?? "",
          valid_until: promo.valid_until ?? "",
          max_uses: promo.max_uses ? String(promo.max_uses) : "",
          max_per_account: String(promo.max_per_account),
          new_registrations_only: promo.new_registrations_only,
          plans: promo.plans,
          reservation_hours: String(promo.reservation_hours),
        }
      : EMPTY,
  );
  const set = (k: keyof PromoForm) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const save = useMutation({
    mutationFn: () => {
      const percent = form.discount_type === "percent";
      const body = {
        code: form.code,
        campaign_name: form.campaign_name,
        description: form.description,
        discount_type: form.discount_type,
        percent_off: percent ? Number(form.percent_off || 0) : 0,
        amount_off: percent ? "0" : form.amount_off || "0",
        max_discount: percent && form.max_discount ? form.max_discount : null,
        min_amount: form.min_amount || null,
        is_active: form.is_active,
        valid_from: form.valid_from || null,
        valid_until: form.valid_until || null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        max_per_account: Number(form.max_per_account || 1),
        new_registrations_only: form.new_registrations_only,
        plans: form.plans,
        reservation_hours: Number(form.reservation_hours || 72),
      };
      return promo ? api(`/admin/promo-codes/${promo.id}/`, { method: "PATCH", json: body }) : api("/admin/promo-codes/", { method: "POST", json: body });
    },
    onSuccess: () => {
      toast.success(promo ? "Promo code saved" : "Promo code created");
      onSaved();
      onClose();
    },
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  return (
    <Dialog open onClose={onClose} wide title={promo ? `Edit ${promo.code}` : "New promo code"} description="Changes never alter payments already submitted — each one keeps a snapshot of the code it used.">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Code" hint="Customers type this (letters, numbers, - or _)" error={fields?.code}>
          {(id) => <Input id={id} required className="font-mono uppercase" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />}
        </FormField>
        <FormField label="Campaign name (internal)">{(id) => <Input id={id} value={form.campaign_name} onChange={set("campaign_name")} />}</FormField>
        <FormField label="Description (internal)" className="sm:col-span-2">
          {(id) => <Input id={id} value={form.description} onChange={set("description")} />}
        </FormField>
        <FormField label="Discount type">
          {(id) => (
            <Select id={id} value={form.discount_type} onChange={(e) => setForm({ ...form, discount_type: e.target.value as PromoForm["discount_type"] })}>
              <option value="percent">Percentage</option>
              <option value="fixed">Fixed amount (৳)</option>
            </Select>
          )}
        </FormField>
        {form.discount_type === "percent" ? (
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Percent off" error={fields?.percent_off}>
              {(id) => <Input id={id} type="number" min={1} max={100} required value={form.percent_off} onChange={set("percent_off")} />}
            </FormField>
            <FormField label="Max discount (৳)" hint="Blank = no cap">{(id) => <Input id={id} type="number" min={0} value={form.max_discount} onChange={set("max_discount")} />}</FormField>
          </div>
        ) : (
          <FormField label="Amount off (৳)" error={fields?.amount_off}>
            {(id) => <Input id={id} type="number" min={1} required value={form.amount_off} onChange={set("amount_off")} />}
          </FormField>
        )}
        <FormField label="Starts">{(id) => <Input id={id} type="date" value={form.valid_from} onChange={set("valid_from")} />}</FormField>
        <FormField label="Expires (last day)" error={fields?.valid_until}>{(id) => <Input id={id} type="date" value={form.valid_until} onChange={set("valid_until")} />}</FormField>
        <FormField label="Max total uses" hint="Blank = unlimited">{(id) => <Input id={id} type="number" min={1} value={form.max_uses} onChange={set("max_uses")} />}</FormField>
        <FormField label="Max uses per account / person">{(id) => <Input id={id} type="number" min={1} value={form.max_per_account} onChange={set("max_per_account")} />}</FormField>
        <FormField label="Minimum price (৳)" hint="Blank = any price">{(id) => <Input id={id} type="number" min={0} value={form.min_amount} onChange={set("min_amount")} />}</FormField>
        <FormField label="Reservation (hours)" hint="How long a registration holds the code before release">
          {(id) => <Input id={id} type="number" min={1} max={720} value={form.reservation_hours} onChange={set("reservation_hours")} />}
        </FormField>
        <fieldset className="sm:col-span-2">
          <legend className="mb-1.5 text-sm font-medium">Eligible plans (none ticked = all plans)</legend>
          <div className="flex flex-wrap gap-3">
            {Object.entries(PLAN_LABELS).map(([period, label]) => (
              <Checkbox
                key={period}
                label={label}
                checked={form.plans.includes(period)}
                onChange={() => setForm({ ...form, plans: form.plans.includes(period) ? form.plans.filter((x) => x !== period) : [...form.plans, period] })}
              />
            ))}
          </div>
        </fieldset>
        <div className="flex flex-col gap-2 sm:col-span-2">
          <Checkbox label="Only for new turf registrations (existing accounts can't use it)" checked={form.new_registrations_only} onChange={(e) => setForm({ ...form, new_registrations_only: e.target.checked })} />
          <Checkbox label="Active" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        </div>
        {save.error && !fields && <p className="text-sm text-destructive sm:col-span-2">{errorText(save.error)}</p>}
        <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>
          {save.isPending && <Loader2 className="animate-spin" />} {promo ? "Save" : "Create"}
        </Button>
      </form>
    </Dialog>
  );
}

interface Redemption {
  kind: "invoice" | "registration";
  who: string;
  reference: string;
  status: string;
  discount: string;
  amount: string | null;
  at: string;
  reserved_until?: string;
}

function HistoryDialog({ promo, onClose }: { promo: PromoCode; onClose: () => void }) {
  const data = useQuery({ queryKey: ["admin", "promo-codes", promo.id, "history"], queryFn: () => api<{ results: Redemption[] }>(`/admin/promo-codes/${promo.id}/redemptions/`) });
  return (
    <Dialog open onClose={onClose} wide title={`${promo.code} — usage`} description={`${promo.label}. Paid uses ${promo.stats.redeemed}, reserved ${promo.stats.reserved}, discount given ${formatBDT(promo.stats.total_discount)}.`}>
      {data.isPending && <Skeleton className="h-40" />}
      {data.data?.results.length === 0 && <EmptyState title="Not used yet" />}
      {!!data.data?.results.length && (
        <Table>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Where</th>
              <th>Status</th>
              <th className="text-right">Discount</th>
            </tr>
          </thead>
          <tbody>
            {data.data.results.map((r) => (
              <tr key={`${r.kind}-${r.reference}`}>
                <td className="whitespace-nowrap text-xs">{fmtPlainDate(r.at.slice(0, 10))}</td>
                <td>{r.who}</td>
                <td className="text-xs">
                  {r.kind === "registration" ? "Registration" : "Plan invoice"} · <span className="font-mono">{r.reference}</span>
                </td>
                <td>
                  <Badge tone={r.status === "paid" || r.status === "redeemed" ? "green" : r.status === "reserved" || r.status === "pending_verification" || r.status === "unpaid" ? "amber" : "neutral"}>
                    {r.status.replace(/_/g, " ")}
                  </Badge>
                </td>
                <td className={cn("tabular text-right")}>{formatBDT(r.discount)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Dialog>
  );
}
