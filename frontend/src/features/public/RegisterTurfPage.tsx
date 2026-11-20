import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CheckCircle2, Copy, Loader2, ShieldCheck, TicketPercent, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { LegalAcceptBox } from "@/components/legal/Legal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import type { LegalRef } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { useLocations } from "./shared";

const EMPTY = {
  turf_name: "",
  owner_name: "",
  phone: "",
  email: "",
  district: "",
  area: "",
  address: "",
  turf_type: "outdoor",
  number_of_fields: "1",
  message: "",
  website: "",
  sector: "",
};

interface RequiredLegal {
  sector: { slug: string; name_en: string; name_bn: string } | null;
  sectors: { slug: string; name_en: string; name_bn: string }[];
  documents: LegalRef[];
}
interface PlanOption {
  id: string;
  period: string;
  name: string;
  months: number;
  price: string;
  description: string;
}
interface Receiving {
  number: string;
  account_type: string;
  instructions: string;
}
interface Options {
  plans: PlanOption[];
  receiving: Receiving;
  payments_open: boolean;
}
interface Quote {
  plan: { id: string; period: string; name: string; months: number };
  original: string;
  discount: string;
  payable: string;
  promo: { code: string; label: string; discount: string } | null;
  receiving: Receiving;
}
export interface RegistrationStatus {
  reference: string;
  turf_name: string;
  status: string;
  status_label: string;
  plan: string | null;
  promo_code: string | null;
  original: string | null;
  discount: string | null;
  payable: string | null;
  amount_sent: string | null;
  trx: string;
  submitted_at: string;
  rejection_reason: string;
  can_resubmit: boolean;
  receiving: Receiving;
  history: { submitted_at: string; amount_sent: string; trx: string; status: string; status_label: string; rejection_reason: string }[];
}

// Only non-sensitive progress is remembered (never payment details), per browser tab.
const DRAFT_KEY = "turfbari:register-draft";
function loadDraft(): { form: typeof EMPTY; plan: string; promo: string; step: number } | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function saveDraft(d: { form: typeof EMPTY; plan: string; promo: string; step: number }) {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  } catch {
    /* storage unavailable: progress just isn't remembered */
  }
}
function clearDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}

export function copy(text: string, what: string) {
  void navigator.clipboard.writeText(text).then(
    () => toast.success(`${what} copied`),
    () => toast.error("Couldn't copy — please copy it by hand"),
  );
}

const STEPS = ["Your turf", "Plan", "Promo & total", "Pay with bKash", "Done"];

export function RegisterTurfPage() {
  const [searchParams] = useSearchParams();
  const requestedPlan = searchParams.get("plan") ?? "";
  const draft = loadDraft();
  const locations = useLocations();
  const [form, setForm] = useState(draft?.form ?? EMPTY);
  const [step, setStep] = useState(draft?.step && draft.step < 4 ? draft.step : 0);
  const [plan, setPlan] = useState(draft?.plan || requestedPlan);
  const [promoInput, setPromoInput] = useState(draft?.promo ?? "");
  const [applied, setApplied] = useState(draft?.promo ?? "");
  const [pay, setPay] = useState({ sender_number: "", amount_sent: "", trx_id: "", payment_note: "" });
  const [agree, setAgree] = useState(false);
  const [done, setDone] = useState<RegistrationStatus | null>(null);
  const qc = useQueryClient();

  const options = useQuery({ queryKey: ["public", "registration-options"], queryFn: () => api<Options>("/public/registration/options/") });
  const legal = useQuery({
    queryKey: ["public", "legal-required", "registration", form.sector],
    queryFn: () => api<RequiredLegal>(`/public/legal/required/?action=registration${form.sector ? `&sector=${form.sector}` : ""}`),
  });
  const docs = legal.data?.documents ?? [];
  const withPayment = options.data?.payments_open ?? false;
  const chosenPlan = plan || options.data?.plans[0]?.period || "";

  useEffect(() => {
    if (!done) saveDraft({ form, plan: chosenPlan, promo: applied, step });
  }, [form, chosenPlan, applied, step, done]);

  // The price always comes from the server (plan + applied promo code).
  const quote = useQuery({
    queryKey: ["public", "registration-quote", chosenPlan, applied, form.phone, form.email],
    queryFn: () =>
      api<Quote>("/public/registration/quote/", { method: "POST", json: { plan: chosenPlan, promo_code: applied, phone: form.phone, email: form.email } }),
    // Stops once submitted: the code is then reserved for this person, so a re-check would say "already used".
    enabled: withPayment && step >= 2 && step < 4 && !done && Boolean(chosenPlan),
    retry: false,
  });
  const promoError = quote.error instanceof ApiError ? quote.error.fields?.promo_code?.[0] : undefined;
  useEffect(() => {
    if (promoError && applied && !done) {
      toast.error(promoError);
      setApplied("");
    }
  }, [promoError, applied, done]);
  const q = quote.data;

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value, ...(key === "district" ? { area: "" } : {}) }));

  const submit = useMutation({
    mutationFn: () =>
      api<RegistrationStatus | { detail: string }>("/public/applications/", {
        method: "POST",
        json: {
          ...form,
          sector: form.sector || legal.data?.sector?.slug || null,
          area: form.area || null,
          number_of_fields: Number(form.number_of_fields),
          agree_legal: agree,
          accepted_versions: docs.map((d) => d.version_id),
          ...(withPayment ? { plan: chosenPlan, promo_code: applied, expected_payable: q?.payable, ...pay } : {}),
        },
      }),
    onSuccess: (r) => {
      clearDraft();
      if ("reference" in r) setDone(r);
      else setDone({ reference: "", status: "pending" } as RegistrationStatus);
      setStep(4);
      window.scrollTo({ top: 0 });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fields?.code?.[0] === "legal_versions_changed") {
        setAgree(false);
        void qc.invalidateQueries({ queryKey: ["public", "legal-required"] });
      }
      if (e instanceof ApiError && (e.fields?.code?.[0] === "price_changed" || e.fields?.promo_code)) {
        void quote.refetch();
        setStep(2);
      }
    },
  });
  const errors = submit.error instanceof ApiError ? submit.error.fields : null;
  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));
  const areas = districts.find((d) => d.slug === form.district)?.areas ?? [];
  const step1Ok = Boolean(form.turf_name && form.owner_name && form.phone && form.email && form.district && form.address);
  const free = q ? Number(q.payable) === 0 : false;
  const payOk = free || Boolean(pay.sender_number && pay.amount_sent && pay.trx_id);

  if (step === 4 && done) return <Confirmation status={done} />;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="font-display text-4xl font-extrabold uppercase leading-none sm:text-5xl">List your turf on TurfBari</h1>
      <p className="mt-3 text-muted-foreground">
        {withPayment
          ? "Choose a plan, pay the first period with bKash, and TurfBari activates your workspace after checking the payment."
          : "Tell us about your turf. After a quick call we set up your workspace and send your login."}
      </p>
      {withPayment && (
        <ol className="mt-6 flex flex-wrap gap-2" aria-label="Steps">
          {STEPS.map((label, i) => (
            <li key={label}>
              <span
                aria-current={i === step ? "step" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs sm:text-sm",
                  i === step ? "border-primary bg-primary text-primary-foreground" : i < step ? "border-primary/40 text-primary" : "text-muted-foreground",
                )}
              >
                <span className="font-semibold">{i + 1}</span> {label}
              </span>
            </li>
          ))}
        </ol>
      )}

      <form
        className="mt-6 flex flex-col gap-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (!withPayment || step === 3) submit.mutate();
        }}
      >
        {step === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Business &amp; owner</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <FormField label="Turf name" error={errors?.turf_name}>
                {(id) => <Input id={id} required value={form.turf_name} onChange={set("turf_name")} />}
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Your name" error={errors?.owner_name}>
                  {(id) => <Input id={id} required autoComplete="name" value={form.owner_name} onChange={set("owner_name")} />}
                </FormField>
                <FormField label="Mobile number" error={errors?.phone}>
                  {(id) => <Input id={id} required type="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={set("phone")} />}
                </FormField>
              </div>
              <FormField label="Email" error={errors?.email} hint="Your owner login will use this email.">
                {(id) => <Input id={id} required type="email" autoComplete="email" value={form.email} onChange={set("email")} />}
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="District" error={errors?.district}>
                  {(id) => (
                    <Select id={id} required value={form.district} onChange={set("district")}>
                      <option value="">Choose…</option>
                      {districts.map((d) => (
                        <option key={d.slug} value={d.slug}>
                          {d.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Area (optional)" error={errors?.area}>
                  {(id) => (
                    <Select id={id} value={form.area} onChange={set("area")} disabled={areas.length === 0}>
                      <option value="">{areas.length ? "Choose…" : "—"}</option>
                      {areas.map((a) => (
                        <option key={a.slug} value={a.slug}>
                          {a.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
              </div>
              <FormField label="Address" error={errors?.address}>
                {(id) => <Input id={id} required value={form.address} onChange={set("address")} />}
              </FormField>
              {(legal.data?.sectors.length ?? 0) > 1 && (
                <FormField label="Business sector" error={errors?.sector}>
                  {(id) => (
                    <Select
                      id={id}
                      value={form.sector || legal.data?.sector?.slug || ""}
                      onChange={(e) => {
                        setAgree(false);
                        setForm((f) => ({ ...f, sector: e.target.value }));
                      }}
                    >
                      {legal.data?.sectors.map((s) => (
                        <option key={s.slug} value={s.slug}>
                          {s.name_en}
                          {s.name_bn ? ` · ${s.name_bn}` : ""}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Type" error={errors?.turf_type}>
                  {(id) => (
                    <Select id={id} value={form.turf_type} onChange={set("turf_type")}>
                      <option value="outdoor">Outdoor</option>
                      <option value="indoor">Indoor</option>
                      <option value="rooftop">Rooftop</option>
                    </Select>
                  )}
                </FormField>
                <FormField label="Number of fields" error={errors?.number_of_fields}>
                  {(id) => <Input id={id} type="number" min={1} max={20} required value={form.number_of_fields} onChange={set("number_of_fields")} />}
                </FormField>
              </div>
              <FormField label="Anything else? (optional)">{(id) => <Textarea id={id} rows={3} value={form.message} onChange={set("message")} />}</FormField>
              <input type="text" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={form.website} onChange={set("website")} />
              {!withPayment && (
                <>
                  <LegalAcceptBox docs={docs} checked={agree} onChange={setAgree} error={errors?.agree_legal?.[0]} />
                  {submit.error && !errors && <p role="alert" className="text-sm text-destructive">{submit.error.message}</p>}
                  <Button type="submit" size="lg" disabled={submit.isPending || legal.isPending || (docs.length > 0 && !agree)}>
                    {submit.isPending && <Loader2 className="animate-spin" />} Submit application
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>Choose your plan</CardTitle>
              <CardDescription>Plans never renew by themselves — you choose and pay for each period.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Plan">
              {options.data?.plans.map((p) => (
                <button
                  key={p.period}
                  type="button"
                  role="radio"
                  aria-checked={chosenPlan === p.period}
                  onClick={() => setPlan(p.period)}
                  className={cn("rounded-xl border p-4 text-left transition", chosenPlan === p.period ? "border-primary bg-primary/5 ring-2 ring-primary" : "hover:bg-secondary")}
                >
                  <span className="block text-sm font-medium text-muted-foreground">{p.name}</span>
                  <span className="tabular mt-1 block text-2xl font-bold">{formatBDT(p.price)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {p.months} month{p.months === 1 ? "" : "s"}
                    {p.description && ` · ${p.description}`}
                  </span>
                </button>
              ))}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TicketPercent className="size-5 text-primary" /> Have a promo code?
                </CardTitle>
                <CardDescription lang="bn">প্রোমো কোড থাকলে এখানে লিখুন</CardDescription>
              </CardHeader>
              <CardContent>
                {applied && q?.promo ? (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-100">
                    <span className="flex items-center gap-2">
                      <CheckCircle2 className="size-4" /> Promo code <strong className="font-mono">{q.promo.code}</strong> applied — {q.promo.label}
                    </span>
                    <Button type="button" size="sm" variant="ghost" onClick={() => (setApplied(""), setPromoInput(""))}>
                      <X /> Remove
                    </Button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Input
                      aria-label="Promo code"
                      placeholder="e.g. TURFSTART20"
                      className="font-mono uppercase"
                      value={promoInput}
                      onChange={(e) => setPromoInput(e.target.value.toUpperCase().replace(/\s/g, ""))}
                    />
                    <Button type="button" variant="outline" disabled={!promoInput || quote.isFetching} onClick={() => setApplied(promoInput)}>
                      {quote.isFetching && applied ? <Loader2 className="animate-spin" /> : null} Apply promo code
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
            <Summary quote={q} loading={quote.isPending} />
          </div>
        )}

        {step === 3 && q && (
          <div className="flex flex-col gap-6">
            {free ? (
              <Card>
                <CardContent className="pt-6 text-sm">Your promo code covers the full price — nothing to pay. TurfBari still checks and approves the registration.</CardContent>
              </Card>
            ) : (
              <>
                <PayCard receiving={q.receiving} amount={q.payable} />
                <Card>
                  <CardHeader>
                    <CardTitle>After sending the money</CardTitle>
                    <CardDescription lang="bn">টাকা পাঠানোর পর নিচের তথ্যগুলো দিন</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4 sm:grid-cols-2">
                    <FormField label="bKash number you sent from" error={errors?.sender_number}>
                      {(id) => <Input id={id} type="tel" required placeholder="01XXXXXXXXX" value={pay.sender_number} onChange={(e) => setPay({ ...pay, sender_number: e.target.value })} />}
                    </FormField>
                    <FormField label="Amount sent (৳)" hint={`Must be exactly ${formatBDT(q.payable)}`} error={errors?.amount_sent}>
                      {(id) => <Input id={id} type="number" step="0.01" required value={pay.amount_sent} onChange={(e) => setPay({ ...pay, amount_sent: e.target.value })} />}
                    </FormField>
                    <FormField label="bKash Transaction ID (TrxID)" error={errors?.trx_id}>
                      {(id) => (
                        <Input id={id} required className="font-mono uppercase" placeholder="e.g. 9C7A6B5D4E" value={pay.trx_id} onChange={(e) => setPay({ ...pay, trx_id: e.target.value.toUpperCase().replace(/\s/g, "") })} />
                      )}
                    </FormField>
                    <FormField label="Note (optional)">{(id) => <Input id={id} maxLength={255} value={pay.payment_note} onChange={(e) => setPay({ ...pay, payment_note: e.target.value })} />}</FormField>
                  </CardContent>
                </Card>
              </>
            )}
            <LegalAcceptBox docs={docs} checked={agree} onChange={setAgree} error={errors?.agree_legal?.[0]} />
            {submit.error && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {errors?.email?.[0] ?? errors?.promo_code?.[0] ?? errors?.plan?.[0] ?? (errors ? "Please check the highlighted fields." : submit.error.message)}
              </p>
            )}
          </div>
        )}

        {withPayment && (
          <div className="flex items-center justify-between gap-3">
            <Button type="button" variant="outline" disabled={step === 0 || submit.isPending} onClick={() => setStep((s) => s - 1)}>
              <ArrowLeft /> Back
            </Button>
            {step < 3 ? (
              <Button
                type="button"
                disabled={(step === 0 && !step1Ok) || (step === 1 && !chosenPlan) || (step === 2 && (!q || quote.isFetching))}
                onClick={() => setStep((s) => s + 1)}
              >
                {step === 2 ? "Continue to payment" : "Continue"} <ArrowRight />
              </Button>
            ) : (
              <Button type="submit" size="lg" disabled={submit.isPending || !payOk || legal.isPending || (docs.length > 0 && !agree)}>
                {submit.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Submit registration
              </Button>
            )}
          </div>
        )}
      </form>
    </div>
  );
}

function Summary({ quote, loading }: { quote?: Quote; loading: boolean }) {
  if (!quote) return loading ? <Card className="h-40 animate-pulse" /> : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Payment summary</CardTitle>
        <CardDescription>
          {quote.plan.name} plan · {quote.plan.months} month{quote.plan.months === 1 ? "" : "s"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between">
            <dt>Plan price</dt>
            <dd className="tabular">{formatBDT(quote.original)}</dd>
          </div>
          {quote.promo && (
            <div className="flex justify-between text-emerald-700 dark:text-emerald-300">
              <dt>
                Promo <span className="font-mono">{quote.promo.code}</span> ({quote.promo.label})
              </dt>
              <dd className="tabular">−{formatBDT(quote.discount)}</dd>
            </div>
          )}
          <div className="mt-1 flex justify-between border-t pt-3 text-base font-bold">
            <dt>You pay</dt>
            <dd className="tabular">{formatBDT(quote.payable)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

export function PayCard({ receiving, amount }: { receiving: Receiving; amount: string }) {
  return (
    <Card className="border-2 border-[#e2136e]/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="rounded bg-[#e2136e] px-1.5 py-0.5 text-xs font-bold text-white">bKash</span> Send the payment
        </CardTitle>
        <CardDescription lang="bn">
          বিকাশ অ্যাপ থেকে নিচের নম্বরে ঠিক এই পরিমাণ টাকা {receiving.account_type === "Personal" ? "Send Money" : receiving.account_type === "Agent" ? "Cash Out" : "Payment"} করুন
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-secondary p-3">
          <div>
            <p className="text-xs text-muted-foreground">bKash number ({receiving.account_type})</p>
            <p className="font-mono text-xl font-bold">{receiving.number}</p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={() => copy(receiving.number, "Number")}>
            <Copy /> Copy number
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-secondary p-3">
          <div>
            <p className="text-xs text-muted-foreground">Exact amount to send</p>
            <p className="tabular text-2xl font-bold">{formatBDT(amount)}</p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={() => copy(String(Number(amount)), "Amount")}>
            <Copy /> Copy amount
          </Button>
        </div>
        {receiving.instructions && <p className="whitespace-pre-line text-muted-foreground">{receiving.instructions}</p>}
      </CardContent>
    </Card>
  );
}

function Confirmation({ status }: { status: RegistrationStatus }) {
  if (!status.reference) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-3 px-4 py-16 text-center" role="status">
        <CheckCircle2 className="size-12 text-primary" />
        <p className="text-lg font-semibold">Application received</p>
        <p className="text-muted-foreground">Thanks! Our team will contact you within 2 working days.</p>
        <Button asChild variant="outline">
          <Link to="/">Back to home</Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-xl px-4 py-12" role="status">
      <div className="flex flex-col items-center gap-3 text-center">
        <CheckCircle2 className="size-12 text-primary" />
        <h1 className="text-2xl font-bold">Registration submitted</h1>
        <p lang="bn" className="text-muted-foreground">
          আপনার রেজিস্ট্রেশন এবং পেমেন্ট তথ্য সফলভাবে জমা হয়েছে। TURFBARI কর্তৃপক্ষ আপনার bKash পেমেন্ট যাচাই করার পর অ্যাকাউন্ট অনুমোদন করবে।
        </p>
      </div>
      <StatusCard status={status} />
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Save your reference. Check progress any time on{" "}
        <Link to={`/registration-status?ref=${status.reference}`} className="font-medium text-primary hover:underline">
          Registration status
        </Link>{" "}
        with this reference and your mobile number. Your login details arrive by SMS after approval.
      </p>
    </div>
  );
}

export function StatusCard({ status }: { status: RegistrationStatus }) {
  const rows: [string, string][] = [
    ["Reference", status.reference],
    ["Turf", status.turf_name],
    ["Plan", status.plan ?? "—"],
    ["Promo code", status.promo_code ?? "—"],
    ["Original amount", status.original ? formatBDT(status.original) : "—"],
    ["Discount", status.discount ? `−${formatBDT(status.discount)}` : "—"],
    ["Amount paid", status.amount_sent ? formatBDT(status.amount_sent) : "—"],
    ["Transaction ID", status.trx || "—"],
    ["Submitted", new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", dateStyle: "medium", timeStyle: "short" }).format(new Date(status.submitted_at))],
  ];
  return (
    <Card className="mt-6">
      <CardContent className="pt-6">
        <p className="mb-4 flex items-center justify-between gap-2">
          <span className="text-sm text-muted-foreground">Status</span>
          <span
            className={cn(
              "rounded-full px-3 py-1 text-sm font-semibold",
              status.status === "approved" ? "bg-emerald-100 text-emerald-800" : status.status.includes("rejected") ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800",
            )}
          >
            {status.status_label}
          </span>
        </p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className={cn("text-right", k === "Reference" || k === "Transaction ID" ? "font-mono" : "")}>{v}</dd>
            </div>
          ))}
        </dl>
        {status.rejection_reason && (
          <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <strong>Payment not accepted:</strong> {status.rejection_reason}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
