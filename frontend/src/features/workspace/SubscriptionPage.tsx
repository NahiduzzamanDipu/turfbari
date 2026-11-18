import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock, CreditCard, Loader2, ShieldCheck, Smartphone, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, ErrorState, FormField, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Invoice, Plan, SubscriptionOverview } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText, useIsOwner } from "./hooks";
import { STANDING_LABEL, STANDING_TONE, fmtPlainDate, useSubscription } from "./SubscriptionBanner";

const INVOICE_TONE: Record<Invoice["status"], BadgeTone> = {
  unpaid: "red",
  pending_verification: "amber",
  paid: "green",
  cancelled: "neutral",
};

function savings(plan: Plan, plans: Plan[]): number {
  const monthly = plans.find((p) => p.period === "monthly");
  if (!monthly || plan.period === "monthly") return 0;
  return Number(monthly.price) * plan.months - Number(plan.price);
}

export function SubscriptionPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const sub = useSubscription();
  const [params, setParams] = useSearchParams();

  // Result of returning from the online checkout.
  useEffect(() => {
    const result = params.get("payment");
    if (!result) return;
    if (result === "success") toast.success("Payment received. Your plan is active.");
    else if (result === "cancelled") toast("Payment cancelled. Nothing was charged.");
    else toast.error("The payment did not go through. You can try again.");
    params.delete("payment");
    setParams(params, { replace: true });
    qc.invalidateQueries({ queryKey: ["ws", "subscription"] });
  }, [params, setParams, qc]);

  const order = useMutation({
    mutationFn: (period: string) => api<Invoice>("/workspace/subscription/order/", { method: "POST", json: { plan: period } }),
    onSuccess: () => {
      toast.success("Plan selected. Pay below to activate it.");
      qc.invalidateQueries({ queryKey: ["ws", "subscription"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  if (sub.isPending) return <Skeleton className="h-96" />;
  if (sub.isError) return <ErrorState error={sub.error} onRetry={() => sub.refetch()} />;
  const { standing, plans, open_invoice, invoices, periods, payment_options } = sub.data;
  const scheduled = periods.filter((p) => p.state === "scheduled");

  return (
    <>
      <PageHeader title="Subscription" description="Your TurfBari plan. Plans never renew automatically — you choose and pay for each period." />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              Current plan
              <Badge tone={STANDING_TONE[standing.state]}>{STANDING_LABEL[standing.state]}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {standing.current ? (
              <>
                <p className="font-display text-3xl font-extrabold uppercase">{standing.current.plan.name}</p>
                <dl className="grid grid-cols-2 gap-3">
                  <div>
                    <dt className="text-muted-foreground">This period</dt>
                    <dd className="font-medium">
                      {fmtPlainDate(standing.current.starts_on)} – {fmtPlainDate(standing.current.ends_on)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Paid until</dt>
                    <dd className="font-medium">{fmtPlainDate(standing.paid_until)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Days left</dt>
                    <dd className={cn("tabular font-semibold", standing.state === "expiring" && "text-amber-600")}>
                      {standing.days_left}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Auto-renew</dt>
                    <dd className="font-medium">Off — pay to continue</dd>
                  </div>
                </dl>
              </>
            ) : (
              <div className="flex items-start gap-3 rounded-lg bg-destructive/10 p-3 text-destructive">
                <AlertTriangle className="mt-0.5 size-5 shrink-0" />
                <p>
                  {standing.state === "grace"
                    ? `Your plan ended on ${fmtPlainDate(standing.paid_until)}. You can keep working until ${fmtPlainDate(standing.grace_until)}; renew before then to stay on TurfBari Explore.`
                    : "You have no active plan. Your turf is hidden from players and new bookings are paused until you pay for a plan."}
                </p>
              </div>
            )}
            {scheduled.map((p) => (
              <p key={p.id} className="flex items-center gap-2 rounded-md bg-secondary px-3 py-2">
                <Clock className="size-4" /> Next: {p.plan.name}, {fmtPlainDate(p.starts_on)} – {fmtPlainDate(p.ends_on)} (paid)
              </p>
            ))}
            {standing.state === "expiring" && !open_invoice && (
              <p className="text-amber-700 dark:text-amber-400">Your plan ends soon. Choose a plan below to renew it.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{standing.current ? "Renew or change plan" : "Choose a plan"}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-3">
              {plans.map((plan) => {
                const save = savings(plan, plans);
                const isCurrent = standing.current?.plan.period === plan.period;
                const isOrdered = open_invoice?.subscription.plan.period === plan.period;
                return (
                  <div
                    key={plan.id}
                    className={cn("flex flex-col gap-2 rounded-xl border p-4", isOrdered && "border-primary ring-2 ring-primary/30")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold">{plan.name}</p>
                      {isCurrent && <Badge tone="green">Current</Badge>}
                    </div>
                    <p className="tabular text-2xl font-bold">{formatBDT(plan.price)}</p>
                    <p className="text-xs text-muted-foreground">
                      {plan.months === 1 ? "per month" : `for ${plan.months} months`}
                      {save > 0 && <span className="font-semibold text-primary"> · save {formatBDT(String(save))}</span>}
                    </p>
                    {plan.description && <p className="text-xs text-muted-foreground">{plan.description}</p>}
                    {isOwner && (
                      <Button
                        size="sm"
                        variant={isOrdered ? "default" : "outline"}
                        className="mt-auto"
                        disabled={order.isPending || isOrdered || open_invoice?.status === "pending_verification"}
                        onClick={() => order.mutate(plan.period)}
                      >
                        {isOrdered ? "Selected" : isCurrent ? "Renew" : standing.current ? "Switch" : "Choose"}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              A new plan starts the day after your paid time ends, so you never lose days. Nothing is charged automatically.
            </p>
            {!isOwner && <p className="text-sm text-muted-foreground">Only the turf owner can change or pay for the plan.</p>}
          </CardContent>
        </Card>
      </div>

      {open_invoice && <PayInvoice invoice={open_invoice} options={payment_options} canPay={isOwner} />}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
        </CardHeader>
        <CardContent className="p-2 sm:p-4">
          {invoices.length === 0 ? (
            <p className="px-2 text-sm text-muted-foreground">No invoices yet.</p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Plan</th>
                  <th>Period</th>
                  <th className="text-right">Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => (
                  <tr key={inv.id}>
                    <td className="font-mono text-xs">{inv.number}</td>
                    <td>{inv.subscription.plan.name}</td>
                    <td className="text-sm">
                      {inv.subscription.starts_on
                        ? `${fmtPlainDate(inv.subscription.starts_on)} – ${fmtPlainDate(inv.subscription.ends_on)}`
                        : "—"}
                    </td>
                    <td className="tabular text-right">{formatBDT(inv.amount)}</td>
                    <td>
                      <Badge tone={INVOICE_TONE[inv.status]}>{inv.status_label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}

function PayInvoice({
  invoice,
  options,
  canPay,
}: {
  invoice: Invoice;
  options: SubscriptionOverview["payment_options"];
  canPay: boolean;
}) {
  const qc = useQueryClient();
  const [method, setMethod] = useState(options.manual[0]?.method ?? "");
  const [reference, setReference] = useState("");
  const [sender, setSender] = useState("");
  const account = options.manual.find((m) => m.method === method);
  const lastRejected = invoice.transactions.find((t) => t.status === "rejected");
  const reviewing = invoice.transactions.find((t) => t.status === "pending_verification");

  const refresh = () => qc.invalidateQueries({ queryKey: ["ws", "subscription"] });
  const online = useMutation({
    mutationFn: () => api<{ redirect_url: string }>(`/workspace/subscription/invoices/${invoice.id}/pay-online/`, { method: "POST" }),
    onSuccess: ({ redirect_url }) => window.location.assign(redirect_url),
    onError: (e) => toast.error(errorText(e)),
  });
  const manual = useMutation({
    mutationFn: () =>
      api(`/workspace/subscription/invoices/${invoice.id}/manual-payment/`, {
        method: "POST",
        json: { method, reference, sender_number: sender },
      }),
    onSuccess: () => {
      toast.success("Payment submitted. TurfBari will verify it shortly.");
      setReference("");
      refresh();
    },
  });
  const cancel = useMutation({
    mutationFn: () => api(`/workspace/subscription/invoices/${invoice.id}/cancel/`, { method: "POST" }),
    onSuccess: refresh,
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <Card className="mt-6 border-primary/40">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>
            Pay for {invoice.subscription.plan.name} · <span className="tabular">{formatBDT(invoice.amount)}</span>
          </span>
          <span className="font-mono text-xs font-normal text-muted-foreground">{invoice.number}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {reviewing ? (
          <div className="flex items-start gap-3 rounded-lg bg-amber-400/15 p-4 text-sm">
            <Clock className="mt-0.5 size-5 shrink-0 text-amber-600" />
            <div>
              <p className="font-semibold">Payment under review</p>
              <p className="text-muted-foreground">
                {reviewing.method_label} transaction <span className="font-mono">{reviewing.reference}</span> was submitted.
                Your plan activates as soon as TurfBari confirms it.
              </p>
            </div>
          </div>
        ) : !canPay ? (
          <p className="text-sm text-muted-foreground">Waiting for the turf owner to pay.</p>
        ) : (
          <>
            {lastRejected && (
              <p className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <XCircle className="mt-0.5 size-4 shrink-0" />
                Your last payment ({lastRejected.reference}) could not be verified{lastRejected.note ? `: ${lastRejected.note}` : ""}. Please try again.
              </p>
            )}
            <div className="grid gap-5 md:grid-cols-2">
              <section className="flex flex-col gap-3 rounded-xl border p-4">
                <h3 className="flex items-center gap-2 font-semibold">
                  <CreditCard className="size-4" /> Pay online
                </h3>
                <p className="text-sm text-muted-foreground">
                  Card (Visa, Mastercard, Amex), bKash, Nagad, Rocket or internet banking through SSLCommerz secure checkout. Activates instantly.
                </p>
                {options.online ? (
                  <>
                    <Button size="lg" onClick={() => online.mutate()} disabled={online.isPending}>
                      {online.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Pay {formatBDT(invoice.amount)} now
                    </Button>
                    {options.online_sandbox && <p className="text-xs text-amber-600">Test mode: no real money is taken.</p>}
                  </>
                ) : (
                  <p className="rounded-md bg-secondary px-3 py-2 text-sm text-muted-foreground">
                    Online checkout is not switched on yet. Use mobile banking on the right.
                  </p>
                )}
              </section>

              <section className="flex flex-col gap-3 rounded-xl border p-4">
                <h3 className="flex items-center gap-2 font-semibold">
                  <Smartphone className="size-4" /> Send money & submit transaction ID
                </h3>
                {options.manual.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Contact TurfBari support for payment details.</p>
                ) : (
                  <form
                    className="flex flex-col gap-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      manual.mutate();
                    }}
                  >
                    <FormField label="Method">
                      {(id) => (
                        <Select id={id} value={method} onChange={(e) => setMethod(e.target.value)}>
                          {options.manual.map((m) => (
                            <option key={m.method} value={m.method}>
                              {m.label}
                            </option>
                          ))}
                        </Select>
                      )}
                    </FormField>
                    {account && (
                      <div className="rounded-md bg-secondary px-3 py-2 text-sm">
                        {method === "bank" ? "Transfer to: " : `Send money to ${account.label} `}
                        <span className="font-mono font-semibold">{account.account}</span>
                        <span className="block text-xs text-muted-foreground">
                          Amount: {formatBDT(invoice.amount)} · Reference: {invoice.number}
                        </span>
                      </div>
                    )}
                    <FormField label="Transaction ID (TrxID)" error={manual.error ? errorText(manual.error) : undefined}>
                      {(id) => (
                        <Input id={id} required placeholder="e.g. 9BG7XK2LQ1" className="font-mono uppercase" value={reference} onChange={(e) => setReference(e.target.value)} />
                      )}
                    </FormField>
                    {method !== "bank" && (
                      <FormField label="Sent from number">
                        {(id) => <Input id={id} type="tel" placeholder="01XXXXXXXXX" value={sender} onChange={(e) => setSender(e.target.value)} />}
                      </FormField>
                    )}
                    <Button type="submit" variant="outline" disabled={manual.isPending}>
                      {manual.isPending && <Loader2 className="animate-spin" />} Submit payment
                    </Button>
                  </form>
                )}
              </section>
            </div>
            <button
              type="button"
              className="self-start text-xs text-muted-foreground hover:text-foreground"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              Cancel this order
            </button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
