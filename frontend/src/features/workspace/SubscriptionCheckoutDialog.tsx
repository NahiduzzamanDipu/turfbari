import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CheckCircle2, Clock3, Loader2, ShieldCheck, Smartphone, TicketPercent } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, Dialog, FormField, Input } from "@/components/ui/form";
import type { Invoice, PaymentTx, SubscriptionOverview } from "@/lib/types";
import { api } from "@/lib/api";
import { formatBDT } from "@/lib/utils";
import { errorText } from "./hooks";

export type CheckoutStep = "promo" | "payment" | "success";

export function SubscriptionCheckoutDialog({
  invoice,
  options,
  canPay,
  step,
  onStepChange,
  onInvoiceChange,
  onClose,
  onDone,
  onSubmittingChange,
}: {
  invoice: Invoice | null;
  options: SubscriptionOverview["payment_options"];
  canPay: boolean;
  step: CheckoutStep;
  onStepChange: (step: CheckoutStep) => void;
  onInvoiceChange: (invoice: Invoice) => void;
  onClose: () => void;
  onDone: () => void;
  onSubmittingChange: (submitting: boolean) => void;
}) {
  const qc = useQueryClient();
  const [promoChoice, setPromoChoice] = useState<"yes" | "no" | null>(null);
  const [sender, setSender] = useState("");
  const [reference, setReference] = useState("");
  const [submitted, setSubmitted] = useState<PaymentTx | null>(null);

  useEffect(() => {
    setPromoChoice(invoice?.promo_code ? "yes" : null);
    setSender("");
    setReference("");
    setSubmitted(null);
  }, [invoice?.id]);

  const bkash = options.manual.find((method) => method.method === "bkash");
  const removePromo = useMutation({
    mutationFn: () => api<Invoice>(`/workspace/subscription/invoices/${invoice?.id}/promo/`, { method: "DELETE" }),
    onSuccess: (updated) => onInvoiceChange(updated),
    onError: (error) => toast.error(errorText(error)),
  });
  const submit = useMutation({
    mutationFn: () => api<PaymentTx>(`/workspace/subscription/invoices/${invoice?.id}/manual-payment/`, {
      method: "POST",
      json: {
        method: "bkash",
        sender_number: sender,
        reference,
        amount_sent: invoice?.payable_total,
      },
    }),
    onMutate: () => onSubmittingChange(true),
    onSuccess: (payment) => {
      setSubmitted(payment);
      onStepChange("success");
      qc.invalidateQueries({ queryKey: ["ws", "subscription"] });
    },
    onError: (error) => toast.error(errorText(error)),
    onSettled: () => onSubmittingChange(false),
  });

  const close = () => {
    if (submit.isPending) return;
    onClose();
  };

  if (!invoice) return null;
  const changeType = invoice.subscription.change_type ?? "new";
  const changeTypeLabel = changeType === "renewal" ? "Renewal" : changeType === "new" ? "New plan" : changeType === "upgrade" ? "Plan upgrade" : "Plan downgrade";
  const progressStep: 1 | 2 | 3 = step === "success" ? 3 : step === "payment" ? 2 : 1;
  const payable = Number(invoice.payable_total);
  const fee = Number(invoice.payable_total) - Number(invoice.amount);

  return (
    <Dialog
      open={Boolean(invoice)}
      onClose={close}
      title={step === "success" ? "Payment Request Submitted!" : changeType === "renewal" ? "Renew Plan" : changeType === "new" ? "Choose Plan" : "Switch Plan"}
      description={step === "success" ? "Your subscription will be updated after administrator verification." : "Submit your payment for secure administrator approval."}
      wide
    >
      <Progress step={progressStep} />
      {step === "promo" && (
        <div className="flex flex-col gap-5">
          <div>
            <h3 className="text-lg font-semibold">Do you have a promo code?</h3>
            <p className="mt-1 text-sm text-muted-foreground">You can apply a valid code before sending your payment.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <button type="button" className={`min-h-14 rounded-xl border px-4 text-left font-semibold transition ${promoChoice === "yes" ? "border-primary bg-primary/10 ring-2 ring-primary/25" : "hover:border-primary/40"}`} onClick={() => setPromoChoice("yes")}>
              <TicketPercent className="mr-2 inline size-4 text-primary" /> Yes, I have a promo code
            </button>
            <button
              type="button"
              className={`min-h-14 rounded-xl border px-4 text-left font-semibold transition ${promoChoice === "no" ? "border-primary bg-primary/10 ring-2 ring-primary/25" : "hover:border-primary/40"}`}
              disabled={removePromo.isPending}
              onClick={() => {
                if (invoice.promo_code) removePromo.mutate(undefined, { onSuccess: () => setPromoChoice("no") });
                else setPromoChoice("no");
              }}
            >
              No, continue without promo code
            </button>
          </div>
          {promoChoice === "yes" && <PromoCodeBox invoice={invoice} onInvoiceChange={onInvoiceChange} />}
          <div className="flex justify-end border-t pt-4">
            <Button
              type="button"
              className="min-h-11"
              disabled={promoChoice === null || (promoChoice === "yes" && !invoice.promo_code) || removePromo.isPending}
              onClick={() => {
                if (invoice.status === "pending_verification" && invoice.amount === "0.00") onStepChange("success");
                else onStepChange("payment");
              }}
            >
              Continue <ArrowRight />
            </Button>
          </div>
        </div>
      )}

      {step === "payment" && (
        <div className="flex flex-col gap-5">
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Payment instructions</p><h3 className="mt-1 text-lg font-semibold">Send money with bKash</h3></div>
            <Badge tone="blue">{changeType}</Badge>
          </div>
          <Card className="border-primary/20 bg-primary/[0.04]">
            <CardContent className="grid gap-4 p-4 sm:grid-cols-2">
              <Summary label="Requested plan" value={`${invoice.subscription.plan.name} · ${invoice.subscription.plan.months} months`} />
              <Summary label="Payment type" value={changeTypeLabel} />
              <Summary label="Plan amount" value={formatBDT(invoice.list_amount)} />
              {Number(invoice.discount) > 0 && <Summary label={`Promo ${invoice.promo_code?.code ?? "discount"}`} value={`−${formatBDT(invoice.discount)}`} accent />}
              {fee > 0 && <Summary label="Payment charge" value={formatBDT(String(fee))} />}
              <Summary label="Exact amount to send" value={formatBDT(invoice.payable_total)} accent strong />
            </CardContent>
          </Card>
          {bkash ? (
            <div className="rounded-xl border p-4">
              <div className="flex items-center gap-3">
                <span className="rounded-lg bg-pink-600 p-2 text-white"><Smartphone className="size-5" /></span>
                <div><p className="text-xs text-muted-foreground">Send Money to {options.bkash_account_type || "bKash"}</p><p className="font-mono text-xl font-bold tracking-wide">{bkash.account}</p></div>
              </div>
              {options.instructions && <p className="mt-3 whitespace-pre-line text-sm text-muted-foreground">{options.instructions}</p>}
              <ol className="mt-4 list-inside list-decimal space-y-1.5 text-sm text-muted-foreground">
                <li>Open your bKash application and choose Send Money.</li>
                <li>Send exactly <strong className="text-foreground">{formatBDT(invoice.payable_total)}</strong> to the number above.</li>
                <li>Copy the Transaction ID after the transfer completes.</li>
                <li>Return here and submit the payment details for approval.</li>
              </ol>
            </div>
          ) : (
            <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">The platform bKash receiving number is not configured yet. Please contact TurfBari support.</p>
          )}
          {invoice.transactions.find((tx) => tx.status === "rejected")?.note && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">Previous payment was rejected: {invoice.transactions.find((tx) => tx.status === "rejected")?.note}</p>
          )}
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); submit.mutate(); }}>
            <FormField label="bKash sender number">
              {(id) => <Input id={id} required type="tel" autoComplete="tel" inputMode="tel" placeholder="01XXXXXXXXX" value={sender} onChange={(event) => setSender(event.target.value)} />}
            </FormField>
            <FormField label="Transaction ID (TrxID)">
              {(id) => <Input id={id} required minLength={6} maxLength={40} autoCapitalize="characters" className="font-mono uppercase" placeholder="Enter bKash TrxID" value={reference} onChange={(event) => setReference(event.target.value.toUpperCase())} />}
            </FormField>
            <FormField label="Payment amount (BDT)" hint="Read-only amount calculated by TurfBari.">
              {(id) => <Input id={id} readOnly value={payable.toFixed(2)} className="font-semibold tabular-nums" />}
            </FormField>
            <FormField label="Selected plan">
              {(id) => <Input id={id} readOnly value={`${invoice.subscription.plan.name} · ${invoice.subscription.plan.months} months`} />}
            </FormField>
            <FormField label="Payment type">
              {(id) => <Input id={id} readOnly value={changeTypeLabel} />}
            </FormField>
            <FormField label="Promo code">
              {(id) => <Input id={id} readOnly value={invoice.promo_code?.code ?? "No promo code"} />}
            </FormField>
            <div className="flex flex-wrap justify-between gap-2 border-t pt-4 sm:col-span-2">
              <Button type="button" variant="ghost" className="min-h-11" onClick={() => onStepChange("promo")} disabled={submit.isPending}><ArrowLeft /> Back</Button>
              <Button type="submit" className="min-h-11" disabled={!canPay || !bkash || submit.isPending}>
                {submit.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />}
                Submit Payment & Request Approval
              </Button>
            </div>
          </form>
        </div>
      )}

      {step === "success" && (
        <div className="flex flex-col items-center gap-4 py-3 text-center">
          <span className="rounded-full bg-emerald-100 p-4 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200"><CheckCircle2 className="size-9" /></span>
          <p className="max-w-md text-sm text-muted-foreground">Your payment request has been successfully submitted. Your subscription will be activated or updated after admin verification and approval.</p>
          <div className="grid w-full gap-3 rounded-xl border bg-muted/30 p-4 text-left sm:grid-cols-2">
            <Summary label="Requested plan" value={`${invoice.subscription.plan.name} · ${invoice.subscription.plan.months} months`} />
            <Summary label="Amount" value={formatBDT(invoice.payable_total)} />
            <Summary label="Transaction ID" value={submitted?.reference || invoice.promo_code?.code || "—"} />
            <Summary label="Request status" value="Pending Approval" accent />
          </div>
          <p className="flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="size-4" /> Your current subscription remains unchanged while approval is pending.</p>
          <Button className="mt-2 min-h-11" onClick={onDone}>Done</Button>
        </div>
      )}
    </Dialog>
  );
}

function Progress({ step }: { step: 1 | 2 | 3 }) {
  const names = ["Promo code", "Payment", "Approval"];
  return (
    <ol aria-label="Payment request progress" className="mb-6 grid grid-cols-3 gap-2">
      {names.map((name, index) => {
        const active = index + 1 === step;
        const complete = index + 1 < step;
        return <li key={name} className="flex min-w-0 items-center gap-2">
          <span className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${active ? "bg-primary text-primary-foreground" : complete ? "bg-emerald-600 text-white" : "bg-secondary text-muted-foreground"}`}>{complete ? <CheckCircle2 className="size-4" /> : index + 1}</span>
          <span className={`truncate text-xs font-medium sm:text-sm ${active ? "text-foreground" : "text-muted-foreground"}`}>{name}</span>
          {index < names.length - 1 && <span aria-hidden className="h-px min-w-2 flex-1 bg-border" />}
        </li>;
      })}
    </ol>
  );
}

function PromoCodeBox({ invoice, onInvoiceChange }: { invoice: Invoice; onInvoiceChange: (invoice: Invoice) => void }) {
  const [code, setCode] = useState("");
  const apply = useMutation({
    mutationFn: () => api<Invoice>(`/workspace/subscription/invoices/${invoice.id}/promo/`, { method: "POST", json: { code } }),
    onSuccess: (updated) => {
      onInvoiceChange(updated);
      setCode("");
      toast.success(updated.promo_code ? `Promo code ${updated.promo_code.code} applied.` : "Promo code applied.");
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const remove = useMutation({
    mutationFn: () => api<Invoice>(`/workspace/subscription/invoices/${invoice.id}/promo/`, { method: "DELETE" }),
    onSuccess: onInvoiceChange,
    onError: (error) => toast.error(errorText(error)),
  });
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-dashed p-4">
      {invoice.promo_code ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-sm"><TicketPercent className="size-4 text-primary" /> <span><strong className="font-mono">{invoice.promo_code.code}</strong> applied · {formatBDT(invoice.discount)} off</span></p>
          <Button type="button" size="sm" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>{remove.isPending && <Loader2 className="animate-spin" />} Remove</Button>
        </div>
      ) : (
        <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(event) => { event.preventDefault(); apply.mutate(); }}>
          <FormField label="Promo code" className="flex-1">
            {(id) => <Input id={id} required maxLength={40} autoCapitalize="characters" className="font-mono uppercase" placeholder="Enter promo code" value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />}
          </FormField>
          <Button type="submit" variant="outline" className="min-h-11" disabled={apply.isPending || !code.trim()}>{apply.isPending ? <Loader2 className="animate-spin" /> : <TicketPercent />} Apply</Button>
        </form>
      )}
      <div className="flex justify-between border-t pt-3 text-sm"><span className="text-muted-foreground">Updated amount to pay</span><strong className="tabular-nums">{formatBDT(invoice.payable_total)}</strong></div>
    </div>
  );
}

function Summary({ label, value, accent = false, strong = false }: { label: string; value: string; accent?: boolean; strong?: boolean }) {
  return <div className="min-w-0"><p className="text-xs text-muted-foreground">{label}</p><p className={`mt-0.5 break-words ${strong ? "text-lg font-bold" : "font-semibold"} ${accent ? "text-primary" : ""}`}>{value}</p></div>;
}
