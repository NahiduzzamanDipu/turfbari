import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  Clock,
  CreditCard,
  Hourglass,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import type React from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { LegalAcceptBox, legalPayload, usePendingLegal } from "@/components/legal/Legal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, ErrorState, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Invoice, Plan } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { SubscriptionCheckoutDialog, type CheckoutStep } from "./SubscriptionCheckoutDialog";
import { errorText, useIsOwner } from "./hooks";
import { resolvePlanCardState } from "./planCardState";
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
  // Plan policies are asked for only when there's a version this owner hasn't accepted yet.
  const legal = usePendingLegal("subscription", isOwner);
  const legalDocs = legal.data?.documents ?? [];
  const [agree, setAgree] = useState(false);
  const [checkout, setCheckout] = useState<{ invoice: Invoice; step: CheckoutStep } | null>(null);
  const [paymentSubmitting, setPaymentSubmitting] = useState(false);

  const closeCheckout = () => {
    if (!paymentSubmitting) setCheckout(null);
  };

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
    mutationFn: (period: string) =>
      api<Invoice>("/workspace/subscription/order/", { method: "POST", json: { plan: period, ...legalPayload(legalDocs, agree) } }),
    onSuccess: (invoice) => {
      setCheckout({ invoice, step: "promo" });
      toast.success("Plan selected. Continue in the payment window.");
      setAgree(false);
      qc.invalidateQueries({ queryKey: ["ws", "subscription"] });
      qc.invalidateQueries({ queryKey: ["legal"] });
    },
    onError: (e) => {
      toast.error(errorText(e));
      qc.invalidateQueries({ queryKey: ["legal", "pending"] });
    },
  });

  if (sub.isPending) return <Skeleton className="h-96" />;
  if (sub.isError) return <ErrorState error={sub.error} onRetry={() => sub.refetch()} />;
  const { standing, plans, open_invoice, invoices, periods, payment_options, turf_status } = sub.data;
  const scheduled = periods.filter((p) => p.state === "scheduled");
  const planCardState = resolvePlanCardState({
    turfStatus: turf_status,
    standingState: standing.state,
    hasCurrent: Boolean(standing.current),
    invoiceStatus: open_invoice?.status ?? null,
  });
  const planCardTone = {
    active: "border-2 border-emerald-300/50 bg-gradient-to-br from-emerald-700 via-emerald-800 to-slate-900 !text-white shadow-lg shadow-emerald-950/15",
    expiring: "border-2 border-amber-300/50 bg-gradient-to-br from-amber-700 via-amber-800 to-stone-950 !text-white shadow-lg shadow-amber-950/15",
    grace: "border-2 border-rose-300/45 bg-gradient-to-br from-rose-800 via-rose-950 to-slate-950 !text-white shadow-lg shadow-rose-950/15",
    expired: "border-2 border-rose-300/45 bg-gradient-to-br from-rose-900 via-red-950 to-slate-950 !text-white shadow-lg shadow-red-950/15",
    none: "border-border bg-gradient-to-br from-muted via-card to-muted/50",
    pending: "border-2 border-sky-300/45 bg-gradient-to-br from-sky-800 via-indigo-950 to-slate-950 !text-white shadow-lg shadow-indigo-950/15",
    suspended: "border-2 border-slate-300/40 bg-gradient-to-br from-slate-700 via-slate-900 to-zinc-950 !text-white shadow-lg shadow-slate-950/15",
  }[planCardState];
  const planStatusLabel = turf_status === "suspended" ? "Suspended" :
    !standing.current && open_invoice?.status === "pending_verification" ? "Pending approval" : STANDING_LABEL[standing.state];
  const planStatusTone: BadgeTone = turf_status === "suspended" || standing.state === "expired" || standing.state === "grace"
    ? "red" : planCardState === "pending" ? "blue" : STANDING_TONE[standing.state];

  return (
    <>
      <PageHeader title="Subscription" description="Your TurfBari plan. Plans never renew automatically — you choose and pay for each period." />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <Card
          className={cn("h-fit rounded-2xl transition-shadow duration-200 hover:shadow-lg", planCardTone)}
          style={planCardState === "active" ? {
            background: "linear-gradient(135deg, #064E3B 0%, #087F5B 100%)",
            color: "#FFFFFF",
          } : undefined}
        >
          <CardHeader className="gap-1.5 px-4 pt-3 pb-1">
            <CardTitle className="flex items-center justify-between gap-2 !text-white">
              <span className="flex items-center gap-2"><Sparkles className="size-4 text-lime-300" /> Current Plan</span>
              <Badge
                tone={planStatusTone}
                className={cn(
                  "border border-current/20 bg-background/15 text-current backdrop-blur-sm",
                  planCardState === "active" && "!border-lime-100 !bg-lime-200 !text-emerald-950",
                )}
              >{planStatusLabel}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className={cn("flex flex-col gap-1.5 px-4 pt-1 pb-2 text-sm", planCardState !== "none" && "!text-white")}>
            {standing.current ? (
              <>
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-100">Your subscription</p>
                    <p className="mt-0.5 break-words font-display text-2xl font-extrabold uppercase leading-tight">{standing.current.plan.name}</p>
                  </div>
                  {standing.current.plan.months > 1 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-current/20 bg-background/10 px-3 py-1.5 text-xs font-semibold backdrop-blur-sm">
                      <CalendarClock className="size-4" /> {standing.current.plan.months === 1 ? "Monthly" : `${standing.current.plan.months} months`}
                    </span>
                  )}
                </div>
                {standing.current.plan.description && <p className="max-w-xl text-[13px] leading-snug text-emerald-50">{standing.current.plan.description}</p>}
                <dl className="grid grid-cols-2 gap-1">
                  <PlanInfo icon={<CalendarDays />} label="Start date" value={fmtPlainDate(standing.current.starts_on)} onDark={planCardState !== "none"} />
                  <PlanInfo icon={<CalendarClock />} label="Expiry date · paid through" value={fmtPlainDate(standing.paid_until)} emphasis onDark={planCardState !== "none"} />
                  <PlanInfo icon={<Clock />} label="Time remaining" value={standing.days_left === null ? "—" : `${Math.max(0, standing.days_left)} ${Math.max(0, standing.days_left) === 1 ? "day" : "days"}`} emphasis={standing.state === "expiring"} onDark={planCardState !== "none"} />
                  <PlanInfo icon={<CreditCard />} label="Billing period · plan price" value={`${standing.current.plan.months === 1 ? "Monthly" : `${standing.current.plan.months} months`} · ${formatBDT(standing.current.price)}`} onDark={planCardState !== "none"} />
                </dl>
                <div className="flex flex-wrap items-center justify-between gap-1.5 border-t border-white/20 pt-1.5">
                  <p className="flex items-center gap-2 text-xs font-medium text-emerald-100"><ShieldCheck className="size-4 text-lime-300" /> No automatic renewal · paid plan</p>
                  {isOwner && planCardState !== "suspended" && standing.state === "expiring" && !open_invoice && <Button type="button" variant="accent" size="sm" className="min-h-11" onClick={() => document.getElementById("plan-options")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Request renewal <ArrowRight /></Button>}
                </div>
              </>
            ) : (
              <div className="flex flex-col items-start gap-4">
                {planCardState === "pending" ? <Hourglass className="size-8" /> : <AlertTriangle className="size-8" />}
                <div>
                  <h4 className="text-xl font-bold">{planCardState === "suspended" ? "Turf account suspended" : planCardState === "pending" ? "Payment awaiting review" : standing.state === "grace" ? "Plan period has ended" : standing.state === "expired" ? "Subscription expired" : "Choose your first plan"}</h4>
                  <p className="mt-1 max-w-xl opacity-80">
                    {planCardState === "pending"
                      ? "Your payment and plan request are pending administrator verification. This request is not active yet."
                      : turf_status === "suspended"
                        ? "This turf account is suspended. Contact TurfBari support for help with account access."
                        : standing.state === "grace"
                          ? `Your plan ended on ${fmtPlainDate(standing.paid_until)}. Service can continue until ${fmtPlainDate(standing.grace_until)}; request renewal to keep your booking page open.`
                          : standing.state === "expired"
                            ? `Your paid period ended ${fmtPlainDate(standing.paid_until)}. Request a renewal to restore plan access.`
                            : "Select a plan below to submit a renewal request. It becomes active only after payment verification."}
                  </p>
                </div>
                {isOwner && planCardState !== "pending" && planCardState !== "suspended" && <Button type="button" variant="accent" className="min-h-11" onClick={() => document.getElementById("plan-options")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Request a plan <ArrowRight /></Button>}
              </div>
            )}
            {open_invoice?.status === "pending_verification" && standing.current && (
              <div role="status" className="flex items-start gap-3 rounded-xl border border-current/20 bg-background/10 p-3 backdrop-blur-sm">
                <Hourglass className="mt-0.5 size-5 shrink-0" />
                <p><strong>Plan request pending approval.</strong> {open_invoice.subscription.plan.name} will not become active until the administrator verifies payment.</p>
              </div>
            )}
            {turf_status === "suspended" && <div role="status" className="flex items-start gap-3 rounded-xl border border-current/20 bg-background/10 p-3"><ShieldAlert className="mt-0.5 size-5 shrink-0" /><p>This turf account is suspended. The subscription dates above show the paid record; suspension is managed separately.</p></div>}
            {scheduled.map((p) => (
              <p key={p.id} className="flex items-center gap-2 rounded-md border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs text-emerald-50">
                <Clock className="size-4" /> Next: {p.plan.name}, {fmtPlainDate(p.starts_on)} – {fmtPlainDate(p.ends_on)} (paid)
              </p>
            ))}
            {standing.state === "expiring" && !open_invoice && (
              <p className="flex items-center gap-2 rounded-lg border border-current/20 bg-background/10 px-3 py-2 text-sm"><AlertTriangle className="size-4" />Your plan ends soon. Request a renewal below.</p>
            )}
          </CardContent>
        </Card>

        <Card id="plan-options" className="scroll-mt-24">
          <CardHeader>
            <CardTitle>{standing.current ? "Renew or change plan" : "Choose a plan"}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <LegalAcceptBox
              id="agree-plan-legal"
              docs={legalDocs}
              checked={agree}
              onChange={setAgree}
              intro="প্ল্যান বেছে নেওয়ার আগে: আমি সাবস্ক্রিপশন, বিলিং ও রিফান্ড নীতিমালা পড়েছি এবং সম্মত হয়েছি।"
            />
            <div className="grid gap-3 sm:grid-cols-3">
              {plans.map((plan) => {
                const save = savings(plan, plans);
                const isCurrent = standing.current?.plan.period === plan.period;
                const isOrdered = open_invoice?.subscription.plan.period === plan.period;
                const canContinueOrder = isOrdered && open_invoice.status === "unpaid";
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
                        disabled={
                          order.isPending ||
                          (isOrdered && !canContinueOrder) ||
                          open_invoice?.status === "pending_verification" ||
                          (legalDocs.length > 0 && !agree)
                        }
                        onClick={() => canContinueOrder ? setCheckout({ invoice: open_invoice, step: "promo" }) : order.mutate(plan.period)}
                      >
                        {canContinueOrder ? "Continue payment" : isOrdered ? "Under review" : isCurrent ? "Renew Plan" : standing.current ? "Switch Plan" : "Choose Plan"}
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

      <SubscriptionCheckoutDialog
        invoice={checkout?.invoice ?? null}
        options={payment_options}
        canPay={isOwner}
        step={checkout?.step ?? "promo"}
        onStepChange={(step) => setCheckout((current) => current ? { ...current, step } : current)}
        onInvoiceChange={(invoice) => setCheckout((current) => current ? { ...current, invoice } : current)}
        onClose={closeCheckout}
        onDone={() => setCheckout(null)}
        onSubmittingChange={setPaymentSubmitting}
      />

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
                    <td className="tabular text-right">
                      {formatBDT(inv.amount)}
                      {inv.promo_code && (
                        <span className="block text-xs text-primary">
                          {inv.promo_code.code} · {inv.promo_code.label ?? `−${inv.promo_code.percent_off}%`}
                        </span>
                      )}
                    </td>
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

function PlanInfo({ icon, label, value, emphasis = false, onDark = false }: {
  icon: React.ReactNode; label: string; value: string; emphasis?: boolean; onDark?: boolean;
}) {
  return (
    <div className={cn("min-w-0 rounded-lg border p-2", onDark ? "border-white/20 bg-white/10 text-white" : "border-border bg-background/70 text-card-foreground")}>
      <dt className={cn("flex items-center gap-1.5 text-[11px] font-medium leading-tight [&>svg]:size-3.5 [&>svg]:shrink-0", onDark ? "text-emerald-100" : "text-muted-foreground")}>{icon}<span>{label}</span></dt>
      <dd className={cn("mt-0.5 break-words text-[13px] font-semibold leading-snug tabular-nums", emphasis && (onDark ? "text-lime-300" : "text-primary"))}>{value}</dd>
    </div>
  );
}
