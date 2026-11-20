import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, Input } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import { formatBDT } from "@/lib/utils";
import { PayCard, type RegistrationStatus, StatusCard } from "./RegisterTurfPage";

/** Applicants check their registration with the reference + the mobile number they registered with.
 * There is no account (and no dashboard access) until TurfBari approves the payment. */
export function RegistrationStatusPage() {
  const [params] = useSearchParams();
  const [form, setForm] = useState({ reference: params.get("ref") ?? "", phone: "" });
  const [pay, setPay] = useState({ sender_number: "", amount_sent: "", trx_id: "", payment_note: "" });
  const check = useMutation({ mutationFn: () => api<RegistrationStatus>("/public/registration/status/", { method: "POST", json: form }) });
  const resubmit = useMutation({
    mutationFn: () => api<RegistrationStatus>("/public/registration/resubmit/", { method: "POST", json: { ...form, ...pay, promo_code: check.data?.promo_code ?? "" } }),
    onSuccess: (s) => {
      check.reset();
      check.mutate();
      toast.success("Corrected payment submitted — TurfBari will check it again");
      void s;
    },
  });
  const s = resubmit.data ?? check.data;
  const fields = resubmit.error instanceof ApiError ? resubmit.error.fields : null;
  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="font-display text-4xl font-extrabold uppercase">Registration status</h1>
      <p className="mt-2 text-muted-foreground" lang="bn">
        রেজিস্ট্রেশন রেফারেন্স ও মোবাইল নম্বর দিয়ে অবস্থা দেখুন
      </p>
      <Card className="mt-6">
        <CardContent className="pt-6">
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              resubmit.reset();
              check.mutate();
            }}
          >
            <FormField label="Reference">{(id) => <Input id={id} required className="font-mono uppercase" placeholder="REG-…" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value.toUpperCase() })} />}</FormField>
            <FormField label="Mobile number">{(id) => <Input id={id} required type="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}</FormField>
            <Button type="submit" disabled={check.isPending}>
              {check.isPending ? <Loader2 className="animate-spin" /> : <Search />} Check
            </Button>
          </form>
          {check.error && <p className="mt-3 text-sm text-destructive">{check.error.message}</p>}
        </CardContent>
      </Card>
      {s && <StatusCard status={s} />}
      {s?.status === "approved" && (
        <p className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Approved! Your login details were sent by SMS to your mobile. Sign in and choose your own password.
        </p>
      )}
      {s?.can_resubmit && s.payable && (
        <div className="mt-6 flex flex-col gap-4">
          <PayCard receiving={s.receiving} amount={s.payable} />
          <Card>
            <CardHeader>
              <CardTitle>Submit corrected payment</CardTitle>
              <CardDescription>Your earlier submission is kept. Send {formatBDT(s.payable)} if you haven't yet, then enter the new details.</CardDescription>
            </CardHeader>
            <CardContent>
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  resubmit.mutate();
                }}
              >
                <FormField label="bKash number you sent from" error={fields?.sender_number}>
                  {(id) => <Input id={id} type="tel" required value={pay.sender_number} onChange={(e) => setPay({ ...pay, sender_number: e.target.value })} />}
                </FormField>
                <FormField label="Amount sent (৳)" error={fields?.amount_sent}>
                  {(id) => <Input id={id} type="number" step="0.01" required value={pay.amount_sent} onChange={(e) => setPay({ ...pay, amount_sent: e.target.value })} />}
                </FormField>
                <FormField label="bKash Transaction ID" error={fields?.trx_id}>
                  {(id) => <Input id={id} required className="font-mono uppercase" value={pay.trx_id} onChange={(e) => setPay({ ...pay, trx_id: e.target.value.toUpperCase().replace(/\s/g, "") })} />}
                </FormField>
                <FormField label="Note (optional)">{(id) => <Input id={id} value={pay.payment_note} onChange={(e) => setPay({ ...pay, payment_note: e.target.value })} />}</FormField>
                {resubmit.error && !fields?.trx_id && !fields?.amount_sent && !fields?.sender_number && (
                  <p className="text-sm text-destructive sm:col-span-2">{fields?.promo_code?.[0] ?? fields?.reference?.[0] ?? resubmit.error.message}</p>
                )}
                <Button type="submit" className="sm:col-span-2" disabled={resubmit.isPending}>
                  {resubmit.isPending && <Loader2 className="animate-spin" />} Submit corrected payment
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
