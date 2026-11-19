import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Clock, Copy, Loader2, Phone, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, type BadgeTone, Dialog, EmptyState, ErrorState, FormField, Input, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtDay, fmtRange } from "@/lib/format";
import type { Paginated } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText } from "./hooks";

type VerificationStatus = "pending" | "approved" | "rejected" | "expired";

interface Verification {
  id: string;
  status: VerificationStatus;
  status_label: string;
  submitted_at: string;
  amount: string;
  sender_number: string;
  trx_id: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  slot_conflict: boolean;
  booking: {
    id: string;
    reference: string;
    status: string;
    customer_name: string;
    customer_phone: string;
    team_name: string;
    field: string;
    start: string;
    end: string;
    total: string;
    amount_paid: string;
    hold_expires_at: string | null;
    notes: string;
  };
}

type ListResponse = Paginated<Verification> & {
  counts: Record<VerificationStatus, number>;
  can_review: boolean;
};

const TABS: { key: VerificationStatus; label: string; tone: BadgeTone }[] = [
  { key: "pending", label: "Awaiting verification", tone: "amber" },
  { key: "approved", label: "Confirmed", tone: "green" },
  { key: "rejected", label: "Rejected", tone: "red" },
  { key: "expired", label: "Expired", tone: "neutral" },
];
const TONE: Record<VerificationStatus, BadgeTone> = { pending: "amber", approved: "green", rejected: "red", expired: "neutral" };

const ago = (iso: string) => {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};
const left = (iso: string | null) => {
  if (!iso) return null;
  const mins = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (mins <= 0) return "hold ended";
  return mins < 60 ? `${mins} min left` : `${Math.floor(mins / 60)} h ${mins % 60} min left`;
};

function copy(text: string) {
  navigator.clipboard.writeText(text).then(() => toast.success("Copied"), () => undefined);
}

export function PaymentVerificationPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<VerificationStatus>("pending");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [approving, setApproving] = useState<Verification | null>(null);
  const [rejecting, setRejecting] = useState<Verification | null>(null);
  const list = useQuery({
    queryKey: ["ws", "verifications", tab, q, page],
    queryFn: () => api<ListResponse>(`/workspace/payment-verifications/?${new URLSearchParams({ status: tab, q, page: String(page) })}`),
    placeholderData: keepPreviousData,
    refetchInterval: tab === "pending" ? 10_000 : false,
  });
  const after = (message: string) => {
    toast.success(message);
    setApproving(null);
    setRejecting(null);
    qc.invalidateQueries({ queryKey: ["ws"] });
  };
  const approve = useMutation({
    mutationFn: (v: Verification) => api<Verification>(`/workspace/payment-verifications/${v.id}/approve/`, { method: "POST" }),
    onSuccess: (v) => after(`Confirmed ${v.booking.reference} — the customer gets an SMS`),
    onError: (e) => toast.error(errorText(e)),
  });
  const reject = useMutation({
    mutationFn: ({ v, reason }: { v: Verification; reason: string }) =>
      api<Verification>(`/workspace/payment-verifications/${v.id}/reject/`, { method: "POST", json: { reason } }),
    onSuccess: (v) => after(`Rejected ${v.booking.reference} — the slot is free again`),
    onError: (e) => toast.error(errorText(e)),
  });
  const canReview = list.data?.can_review ?? false;

  return (
    <>
      <PageHeader
        title="Payment verification"
        description="পেমেন্ট যাচাই — check each bKash payment in your bKash app (amount, sender number and TrxID), then approve or reject. Nothing is confirmed until you approve."
      />
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Payment status">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => {
                setTab(t.key);
                setPage(1);
              }}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition",
                tab === t.key ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary",
              )}
            >
              {t.label}
              {list.data && (
                <span className={cn("tabular rounded-full px-1.5 text-xs", tab === t.key ? "bg-white/20" : "bg-secondary")}>
                  {list.data.counts[t.key]}
                </span>
              )}
            </button>
          ))}
        </div>
        <Input
          className="lg:max-w-72"
          placeholder="Search name, phone, TrxID, booking ID"
          aria-label="Search payments"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
      </div>
      {list.data && !canReview && tab === "pending" && (
        <p className="mb-4 rounded-xl border p-3 text-sm text-muted-foreground">
          You can see payments, but your turf owner hasn't allowed you to approve or reject them.
        </p>
      )}
      {list.isPending && <Skeleton className="h-48" />}
      {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.results.length === 0 && (
        <Card>
          <CardContent>
            <EmptyState icon={<ShieldCheck />} title={tab === "pending" ? "No payments waiting" : "Nothing here yet"}>
              {tab === "pending" ? "New bKash payments from your booking page appear here within seconds." : undefined}
            </EmptyState>
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 xl:grid-cols-2">
        {list.data?.results.map((v) => {
          const b = v.booking;
          const remaining = Number(b.total) - Number(v.amount);
          return (
            <Card key={v.id} className={cn(v.status === "pending" && "border-l-4 border-l-amber-500")}>
              <CardContent className="flex flex-col gap-4 p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">
                      {b.customer_name}
                      {b.team_name && <span className="font-normal text-muted-foreground"> · {b.team_name}</span>}
                    </p>
                    <a href={`tel:${b.customer_phone}`} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                      <Phone className="size-3.5" /> {b.customer_phone}
                    </a>
                  </div>
                  <div className="text-right">
                    <Badge tone={TONE[v.status]}>{v.status_label}</Badge>
                    <p className="mt-1 text-xs text-muted-foreground">Sent {ago(v.submitted_at)}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 rounded-lg bg-secondary/60 p-3 text-sm sm:grid-cols-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Slot</p>
                    <p className="font-medium">{fmtDay(b.start)}</p>
                    <p>{fmtRange(b.start, b.end)}</p>
                    <p className="text-xs text-muted-foreground">{b.field}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Slot price</p>
                    <p className="tabular font-medium">{formatBDT(b.total)}</p>
                    <p className="text-xs text-muted-foreground">Due at turf {formatBDT(Math.max(remaining, 0))}</p>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <p className="text-xs text-muted-foreground">Booking ID</p>
                    <p className="font-mono text-xs font-semibold">{b.reference}</p>
                    {v.status === "pending" && (
                      <p className="mt-1 inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
                        <Clock className="size-3" /> {left(b.hold_expires_at)}
                      </p>
                    )}
                  </div>
                </div>

                <div className="rounded-lg border-2 border-[#e2136e]/25 p-3">
                  <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span className="rounded bg-[#e2136e] px-1.5 py-0.5 text-[10px] font-bold text-white">bKash</span> Check these in your bKash app
                  </p>
                  <dl className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <dt className="text-xs text-muted-foreground">Amount</dt>
                      <dd className="tabular text-lg font-bold">{formatBDT(v.amount)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">From</dt>
                      <dd className="font-mono">{v.sender_number}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">TrxID</dt>
                      <dd className="flex items-center gap-1 font-mono font-semibold">
                        {v.trx_id}
                        <button type="button" aria-label="Copy TrxID" className="text-muted-foreground hover:text-foreground" onClick={() => copy(v.trx_id)}>
                          <Copy className="size-3.5" />
                        </button>
                      </dd>
                    </div>
                  </dl>
                </div>

                {b.notes && <p className="text-sm text-muted-foreground">Note: {b.notes}</p>}
                {v.slot_conflict && (
                  <p className="flex items-start gap-2 rounded-md bg-destructive/10 p-2 text-sm text-destructive">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    Another booking now holds this slot. Reject this payment and refund the customer.
                  </p>
                )}
                {v.reviewed_by && (
                  <p className="text-xs text-muted-foreground">
                    {v.status === "approved" ? "Approved" : "Rejected"} by {v.reviewed_by}
                    {v.reviewed_at && ` · ${ago(v.reviewed_at)}`}
                    {v.rejection_reason && ` — “${v.rejection_reason}”`}
                  </p>
                )}

                {(v.status === "pending" || v.status === "expired") && canReview && (
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button className="flex-1" disabled={v.slot_conflict || approve.isPending} onClick={() => setApproving(v)}>
                      <Check /> Approve payment
                    </Button>
                    <Button className="flex-1" variant="outline" onClick={() => setRejecting(v)}>
                      <X /> Reject payment
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      {list.data && list.data.count > 20 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft />
          </Button>
          <span className="tabular">Page {page}</span>
          <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
            <ChevronRight />
          </Button>
        </div>
      )}

      {approving && (
        <Dialog open onClose={() => setApproving(null)} title="Approve this payment?" description="Only approve after you see this money in your bKash account.">
          <div className="flex flex-col gap-4 text-sm">
            <ul className="space-y-1 rounded-lg bg-secondary/60 p-3">
              <li>
                <span className="text-muted-foreground">Amount:</span> <strong>{formatBDT(approving.amount)}</strong> from{" "}
                <span className="font-mono">{approving.sender_number}</span>
              </li>
              <li>
                <span className="text-muted-foreground">TrxID:</span> <span className="font-mono font-semibold">{approving.trx_id}</span>
              </li>
              <li>
                <span className="text-muted-foreground">Booking:</span> {fmtDay(approving.booking.start)}, {fmtRange(approving.booking.start, approving.booking.end)} ·{" "}
                {approving.booking.field}
              </li>
            </ul>
            <p className="text-muted-foreground">
              The booking is confirmed, {formatBDT(approving.amount)} is recorded as paid by bKash, and {approving.booking.customer_name} gets a confirmation SMS.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setApproving(null)}>
                Cancel
              </Button>
              <Button disabled={approve.isPending} onClick={() => approve.mutate(approving)}>
                {approve.isPending ? <Loader2 className="animate-spin" /> : <Check />} Yes, approve
              </Button>
            </div>
          </div>
        </Dialog>
      )}
      {rejecting && <RejectDialog v={rejecting} busy={reject.isPending} onClose={() => setRejecting(null)} onReject={(reason) => reject.mutate({ v: rejecting, reason })} />}
    </>
  );
}

const REASONS = ["TrxID not found in bKash", "Amount is less than the advance", "Sent with Cash Out / Payment instead of Send Money", "Slot no longer available"];

function RejectDialog({ v, busy, onClose, onReject }: { v: Verification; busy: boolean; onClose: () => void; onReject: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open onClose={onClose} title="Reject this payment?" description="The booking is cancelled and the slot opens for others.">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onReject(reason);
        }}
      >
        <p className="text-sm">
          {v.booking.customer_name} · {formatBDT(v.amount)} · TrxID <span className="font-mono">{v.trx_id}</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {REASONS.map((r) => (
            <button key={r} type="button" onClick={() => setReason(r)} className={cn("rounded-full border px-2.5 py-1 text-xs", reason === r ? "border-primary bg-primary/10" : "hover:bg-secondary")}>
              {r}
            </button>
          ))}
        </div>
        <FormField label="Reason (optional, sent to the customer by SMS)">
          {(id) => <Textarea id={id} rows={2} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </FormField>
        <p className="text-xs text-muted-foreground">If money did arrive, refund it from your bKash app — TurfBari doesn't move money.</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Keep it
          </Button>
          <Button type="submit" variant="destructive" disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <X />} Reject payment
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
