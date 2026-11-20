import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Pencil, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { STANDING_LABEL, STANDING_TONE, fmtPlainDate } from "@/features/workspace/SubscriptionBanner";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { AdminPayment, AdminTurf, Paginated, Plan } from "@/lib/types";
import { formatBDT } from "@/lib/utils";

export const PERIOD_TONE: Record<string, BadgeTone> = { monthly: "blue", half_yearly: "lime", yearly: "green" };

export function usePlans() {
  return useQuery({ queryKey: ["admin", "plans"], queryFn: () => api<Plan[]>("/admin/plans/"), staleTime: 60_000 });
}

/** Plan choice used when the admin creates a turf or approves an application. */
export function PlanPicker({
  value,
  onChange,
}: {
  value: { plan: string; payment_received: boolean };
  onChange: (v: { plan: string; payment_received: boolean }) => void;
}) {
  const plans = usePlans();
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3 sm:col-span-2">
      <p className="text-sm font-medium">Subscription plan</p>
      <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Subscription plan">
        {(plans.data ?? []).filter((p) => p.is_active).map((p) => (
          <label
            key={p.period}
            className={`flex cursor-pointer flex-col rounded-md border px-3 py-2 text-sm transition ${value.plan === p.period ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-secondary"}`}
          >
            <span className="flex items-center gap-2 font-semibold">
              <input type="radio" name="plan" aria-label={p.name} className="accent-[var(--primary)]" checked={value.plan === p.period} onChange={() => onChange({ ...value, plan: p.period })} />
              {p.name}
            </span>
            <span className="tabular text-xs text-muted-foreground">
              {formatBDT(p.price)} · {p.months === 1 ? "1 month" : `${p.months} months`}
            </span>
          </label>
        ))}
      </div>
      <Checkbox
        label="Payment already received (plan starts today)"
        checked={value.payment_received}
        onChange={(e) => onChange({ ...value, payment_received: e.target.checked })}
      />
      {!value.payment_received && (
        <p className="text-xs text-muted-foreground">
          The owner will see an unpaid invoice and can pay online from their workspace. Its booking page stays closed and bookings are paused until it is paid.
        </p>
      )}
    </div>
  );
}

/** Plan cell for the admin turf table. */
export function TurfPlanCell({ turf, onChange }: { turf: AdminTurf; onChange: () => void }) {
  const s = turf.subscription;
  return (
    <div className="flex min-w-36 flex-col items-start gap-1">
      {s.plan ? (
        <Badge tone={PERIOD_TONE[s.plan.period] ?? "neutral"}>{s.plan.name}</Badge>
      ) : (
        <Badge tone={STANDING_TONE[s.state]}>{STANDING_LABEL[s.state]}</Badge>
      )}
      {s.paid_until && (
        <span className={`text-xs ${s.state === "active" ? "text-muted-foreground" : "font-semibold text-destructive"}`}>
          {s.state === "grace" || s.state === "expired" ? "Ended" : "Until"} {fmtPlainDate(s.paid_until)}
          {s.state === "expiring" && ` · ${s.days_left}d left`}
        </span>
      )}
      {s.open_order && (
        <span className="text-xs text-amber-600">
          {s.open_order.plan} order {s.open_order.status === "pending_verification" ? "· payment to verify" : "· unpaid"}
        </span>
      )}
      <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={onChange}>
        Change plan
      </button>
    </div>
  );
}

export function AssignPlanDialog({ turf, onClose }: { turf: AdminTurf | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ plan: "monthly", paid: true, method: "cash", reference: "" });
  const assign = useMutation({
    mutationFn: () => api(`/admin/turfs/${turf?.id}/assign-plan/`, { method: "POST", json: form }),
    onSuccess: () => {
      toast.success(form.paid ? "Plan activated" : "Invoice sent to the owner");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Dialog open={turf !== null} onClose={onClose} title={`Plan for ${turf?.name ?? ""}`} description="A paid plan starts after any time already paid for. Plans never renew by themselves.">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          assign.mutate();
        }}
      >
        <PlanPicker value={{ plan: form.plan, payment_received: form.paid }} onChange={(v) => setForm({ ...form, plan: v.plan, paid: v.payment_received })} />
        {form.paid && (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Received by">
              {(id) => (
                <Select id={id} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
                  <option value="cash">Cash</option>
                  <option value="bkash">bKash</option>
                  <option value="nagad">Nagad</option>
                  <option value="rocket">Rocket</option>
                  <option value="bank">Bank transfer</option>
                </Select>
              )}
            </FormField>
            <FormField label="Reference (optional)">
              {(id) => <Input id={id} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />}
            </FormField>
          </div>
        )}
        <Button type="submit" disabled={assign.isPending} className="self-end">
          {assign.isPending && <Loader2 className="animate-spin" />} {form.paid ? "Activate plan" : "Send invoice"}
        </Button>
      </form>
    </Dialog>
  );
}

const TX_TONE: Record<string, BadgeTone> = {
  pending_verification: "amber",
  verified: "green",
  rejected: "red",
  failed: "red",
  cancelled: "neutral",
};

export function AdminBillingPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("pending_verification");
  const [editing, setEditing] = useState<Plan | null>(null);
  const plans = usePlans();
  const payments = useQuery({
    queryKey: ["admin", "payments", status],
    queryFn: () => api<Paginated<AdminPayment>>(`/admin/payments/?status=${status}`),
    placeholderData: keepPreviousData,
  });
  const review = useMutation({
    mutationFn: ({ id, approve, note }: { id: string; approve: boolean; note?: string }) =>
      api(`/admin/payments/${id}/${approve ? "verify" : "reject"}/`, { method: "POST", json: { note: note ?? "" } }),
    onSuccess: (_, v) => {
      toast.success(v.approve ? "Payment verified — plan activated" : "Payment rejected");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader title="Plans & payments" description="Subscription prices and owner payments waiting for verification." />

      <Card>
        <CardHeader>
          <CardTitle>Plans</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {plans.isPending && <Skeleton className="h-24 sm:col-span-3" />}
          {plans.data?.map((p) => (
            <div key={p.id} className="flex flex-col gap-1 rounded-xl border p-4">
              <div className="flex items-center justify-between">
                <Badge tone={PERIOD_TONE[p.period] ?? "neutral"}>{p.name}</Badge>
                <Button size="icon" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>
                  <Pencil />
                </Button>
              </div>
              <p className="tabular text-2xl font-bold">{formatBDT(p.price)}</p>
              <p className="text-xs text-muted-foreground">
                {p.months} month{p.months > 1 ? "s" : ""} · {p.is_active ? "Offered to owners" : "Hidden"}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Owner payments</CardTitle>
          <div className="flex flex-wrap gap-2">
            {[
              ["pending_verification", "To verify"],
              ["verified", "Verified"],
              ["rejected", "Rejected"],
              ["", "All"],
            ].map(([value, label]) => (
              <Button key={label} size="sm" variant={status === value ? "default" : "outline"} onClick={() => setStatus(value!)}>
                {label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="p-2 sm:p-4">
          {payments.isPending && <Skeleton className="h-32" />}
          {payments.isError && <ErrorState error={payments.error} onRetry={() => payments.refetch()} />}
          {payments.data?.results.length === 0 && <EmptyState title="Nothing here">No payments in this list.</EmptyState>}
          {payments.data && payments.data.results.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Turf</th>
                  <th>Request</th>
                  <th>Method</th>
                  <th>Transaction</th>
                  <th className="text-right">Amount</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {payments.data.results.map((t) => (
                  <tr key={t.id}>
                    <td className="font-medium">
                      {t.turf_name}
                      {t.owner && <span className="block text-xs text-muted-foreground">{t.owner.name || t.owner.email} · {t.owner.phone || t.owner.email}</span>}
                      <span className="block text-xs text-muted-foreground">{fmtDateTime(t.created_at)}</span>
                    </td>
                    <td>
                      <span className="capitalize">{t.change_type || "plan"}</span> → {t.plan_name} ({t.plan_months} mo)
                      <span className="block text-xs text-muted-foreground">
                        Now: {t.current.plan ?? "no plan"}
                        {t.current.paid_until && ` until ${t.current.paid_until}`}
                      </span>
                      {t.promo_code && <span className="block text-xs text-primary">Promo {t.promo_code}: {formatBDT(t.discount)} off {formatBDT(t.list_amount)} list price</span>}
                      <span className="block font-mono text-xs text-muted-foreground">{t.invoice_number}</span>
                    </td>
                    <td>{t.method_label}</td>
                    <td className="font-mono text-xs">
                      {t.reference || "—"}
                      {t.sender_number && <span className="block text-muted-foreground">from {t.sender_number}</span>}
                    </td>
                    <td className="tabular text-right">
                      {formatBDT(t.payable)}
                      {t.amount_sent && (
                        <span className={`block text-xs ${Number(t.amount_sent) + 1 < Number(t.payable) ? "text-destructive" : "text-muted-foreground"}`}>
                          sent {formatBDT(t.amount_sent)}
                        </span>
                      )}
                    </td>
                    <td>
                      <Badge tone={TX_TONE[t.status] ?? "neutral"}>{t.status_label}</Badge>
                    </td>
                    <td className="text-right">
                      {t.status === "pending_verification" && (
                        <div className="flex justify-end gap-1">
                          <Button size="sm" onClick={() => review.mutate({ id: t.id, approve: true })} disabled={review.isPending}>
                            <Check /> Verify
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={review.isPending}
                            onClick={() => {
                              const note = window.prompt("Reason for rejecting (shown to the owner):", "Transaction not found");
                              if (note !== null) review.mutate({ id: t.id, approve: false, note });
                            }}
                          >
                            <X /> Reject
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <p className="mt-3 px-2 text-xs text-muted-foreground">
            Check each transaction ID in your bKash / Nagad / Rocket merchant app or bank statement before verifying. Online card and gateway payments are confirmed automatically.
          </p>
        </CardContent>
      </Card>

      <EditPlanDialog plan={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function EditPlanDialog({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Pick<Plan, "name" | "price" | "description" | "is_active"> | null>(null);
  const current = form ?? (plan ? { name: plan.name, price: plan.price, description: plan.description, is_active: plan.is_active } : null);
  const save = useMutation({
    mutationFn: () => api(`/admin/plans/${plan?.id}/`, { method: "PATCH", json: current }),
    onSuccess: () => {
      toast.success("Plan updated. New orders use the new price.");
      qc.invalidateQueries({ queryKey: ["admin", "plans"] });
      setForm(null);
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Dialog
      open={plan !== null}
      onClose={() => {
        setForm(null);
        onClose();
      }}
      title={`Edit ${plan?.name ?? ""} plan`}
      description="Changes apply to new orders only; paid periods keep their price."
    >
      {current && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <FormField label="Name">
            {(id) => <Input id={id} required value={current.name} onChange={(e) => setForm({ ...current, name: e.target.value })} />}
          </FormField>
          <FormField label="Price (৳)">
            {(id) => <Input id={id} required type="number" min={1} step="0.01" value={current.price} onChange={(e) => setForm({ ...current, price: e.target.value })} />}
          </FormField>
          <FormField label="Short description">
            {(id) => <Input id={id} maxLength={200} value={current.description} onChange={(e) => setForm({ ...current, description: e.target.value })} />}
          </FormField>
          <Checkbox label="Offer this plan to owners" checked={current.is_active} onChange={(e) => setForm({ ...current, is_active: e.target.checked })} />
          <Button type="submit" disabled={save.isPending} className="self-end">
            Save plan
          </Button>
        </form>
      )}
    </Dialog>
  );
}
