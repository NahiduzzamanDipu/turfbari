import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Loader2, Search, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { type CredentialInfo, CredentialStatus } from "@/components/account/CredentialStatus";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { api } from "@/lib/api";
import { cn, formatBDT } from "@/lib/utils";

interface Row {
  id: string;
  reference: string;
  turf_name: string;
  owner_name: string;
  phone: string;
  email: string;
  plan: string;
  promo_code: string | null;
  promo_label: string | null;
  original: string;
  discount: string;
  payable: string;
  amount_sent: string;
  sender_number: string;
  trx_id: string | null;
  note: string;
  receiving_number: string;
  submitted_at: string;
  status: "pending_verification" | "approved" | "rejected";
  status_label: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string;
  rejection_reason: string;
  can_resubmit: boolean;
  credential?: CredentialInfo | null;
  temporary_password?: string | null;
}
interface Report {
  requests: number;
  pending: number;
  approved: number;
  rejected: number;
  original_value: string;
  discounts: string;
  revenue: string;
  registrations: number;
  registrations_approved: number;
  by_promo: { code: string; uses: number; discount: string; revenue: string }[];
}

const TONE: Record<Row["status"], BadgeTone> = { pending_verification: "amber", approved: "green", rejected: "red" };
const when = (iso: string | null) =>
  iso ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso)) : "—";

export function AdminRegistrationPaymentsPage() {
  const [status, setStatus] = useState("pending_verification");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Row | null>(null);
  const query = new URLSearchParams({ page: String(page), ...(status && { status }), ...(search && { q: search }) });
  const list = useQuery({
    queryKey: ["admin", "registration-payments", query.toString()],
    queryFn: () => api<{ count: number; results: Row[]; report: Report }>(`/admin/registration-payments/?${query}`),
    placeholderData: keepPreviousData,
  });
  const r = list.data?.report;
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 20)) : 1;
  return (
    <>
      <PageHeader
        title="Registration payments"
        description="New turf registrations paid by bKash. Check each Transaction ID in TurfBari's bKash account before approving — approval creates the account and activates the plan."
      />
      {r && (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Awaiting verification" value={r.pending} hint={`${r.requests} submissions in total`} />
          <StatCard label="Approved / rejected" value={`${r.approved} / ${r.rejected}`} hint={`${r.registrations_approved} of ${r.registrations} registrations approved`} />
          <StatCard label="Received (approved only)" value={formatBDT(r.revenue)} hint={`List value ${formatBDT(r.original_value)}`} />
          <StatCard label="Discounts given" value={formatBDT(r.discounts)} hint={r.by_promo[0] ? `Top code: ${r.by_promo[0].code} (${r.by_promo[0].uses})` : "No promo codes used yet"} />
        </div>
      )}
      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <form
            className="flex flex-1 gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setSearch(q.trim());
            }}
          >
            <Input aria-label="Search" placeholder="Reference, turf, owner, phone, email or TrxID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Button type="submit" size="icon" variant="outline" aria-label="Search">
              <Search />
            </Button>
          </form>
          <Select aria-label="Status" className="sm:w-56" value={status} onChange={(e) => (setPage(1), setStatus(e.target.value))}>
            <option value="pending_verification">Awaiting verification</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="">All</option>
          </Select>
        </CardHeader>
        <CardContent>
          {list.isPending && <Skeleton className="h-48" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.count === 0 && <EmptyState title="Nothing here" />}
          {!!list.data?.results.length && (
            <Table className={cn(list.isFetching && "opacity-70")}>
              <thead>
                <tr>
                  <th>Registration</th>
                  <th>Owner</th>
                  <th>Plan &amp; promo</th>
                  <th className="text-right">Payable</th>
                  <th>bKash</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((p) => (
                  <tr key={p.id} className="cursor-pointer hover:bg-secondary/60" onClick={() => setOpen(p)}>
                    <td>
                      <span className="font-mono text-xs font-semibold">{p.reference}</span>
                      <span className="block">{p.turf_name}</span>
                      <span className="block text-xs text-muted-foreground">{when(p.submitted_at)}</span>
                    </td>
                    <td>
                      {p.owner_name}
                      <span className="block text-xs text-muted-foreground">
                        {p.phone} · {p.email}
                      </span>
                    </td>
                    <td className="text-xs">
                      {p.plan}
                      {p.promo_code && (
                        <span className="block text-primary">
                          {p.promo_code} · −{formatBDT(p.discount)}
                        </span>
                      )}
                    </td>
                    <td className="tabular text-right">
                      {formatBDT(p.payable)}
                      {p.amount_sent !== p.payable && <span className="block text-xs text-destructive">sent {formatBDT(p.amount_sent)}</span>}
                    </td>
                    <td className="text-xs">
                      <span className="font-mono">{p.trx_id ?? "— (100% promo)"}</span>
                      <span className="block text-muted-foreground">from {p.sender_number || "—"}</span>
                    </td>
                    <td>
                      <Badge tone={TONE[p.status]}>{p.status_label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {pages > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-sm">
              <Button size="icon" variant="outline" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((x) => x - 1)}>
                <ChevronLeft />
              </Button>
              {page} / {pages}
              <Button size="icon" variant="outline" aria-label="Next page" disabled={page >= pages} onClick={() => setPage((x) => x + 1)}>
                <ChevronRight />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      {r && r.by_promo.length > 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Promo codes in approved registrations</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th className="text-right">Registrations</th>
                  <th className="text-right">Discount</th>
                  <th className="text-right">Received</th>
                </tr>
              </thead>
              <tbody>
                {r.by_promo.map((x) => (
                  <tr key={x.code}>
                    <td className="font-mono">{x.code}</td>
                    <td className="tabular text-right">{x.uses}</td>
                    <td className="tabular text-right">{formatBDT(x.discount)}</td>
                    <td className="tabular text-right">{formatBDT(x.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
      {open && <ReviewDialog row={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function ReviewDialog({ row, onClose }: { row: Row; onClose: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [allowResubmit, setAllowResubmit] = useState(true);
  const [result, setResult] = useState<Row | null>(null);
  const after = (r: Row, msg: string) => {
    setResult(r);
    qc.invalidateQueries({ queryKey: ["admin"] });
    toast.success(msg);
  };
  const approve = useMutation({
    mutationFn: () => api<Row>(`/admin/registration-payments/${row.id}/approve/`, { method: "POST", json: { note } }),
    onSuccess: (r) => after(r, `${r.reference} approved — account and plan are active`),
    onError: (e) => toast.error(errorText(e)),
  });
  const reject = useMutation({
    mutationFn: () => api<Row>(`/admin/registration-payments/${row.id}/reject/`, { method: "POST", json: { reason, allow_resubmit: allowResubmit } }),
    onSuccess: (r) => after(r, `${r.reference} rejected`),
    onError: (e) => toast.error(errorText(e)),
  });
  const p = result ?? row;
  const pending = p.status === "pending_verification";
  const items: [string, string][] = [
    ["Turf", p.turf_name],
    ["Owner", `${p.owner_name} · ${p.phone} · ${p.email}`],
    ["Plan", p.plan],
    ["Promo", p.promo_code ? `${p.promo_code} (${p.promo_label})` : "—"],
    ["Original price", formatBDT(p.original)],
    ["Discount", `−${formatBDT(p.discount)}`],
    ["Payable", formatBDT(p.payable)],
    ["Amount sent", formatBDT(p.amount_sent)],
    ["Sender bKash", p.sender_number || "—"],
    ["Transaction ID", p.trx_id ?? "— (100% promo, nothing paid)"],
    ["Paid to", p.receiving_number || "—"],
    ["Note", p.note || "—"],
    ["Submitted", when(p.submitted_at)],
  ];
  return (
    <Dialog open onClose={onClose} wide title={`Registration ${p.reference}`} description="Check this TrxID and amount in TurfBari's bKash account first.">
      <div className="flex flex-col gap-4 text-sm">
        <div className="flex items-center gap-2">
          <Badge tone={TONE[p.status]}>{p.status_label}</Badge>
          {p.reviewed_by && (
            <span className="text-xs text-muted-foreground">
              by {p.reviewed_by}, {when(p.reviewed_at)}
            </span>
          )}
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          {items.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className={cn(k === "Transaction ID" && "font-mono font-semibold")}>{v}</dd>
            </div>
          ))}
        </dl>
        {p.rejection_reason && <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive">Rejected: {p.rejection_reason}</p>}
        {result?.credential && <CredentialStatus credential={result.credential} />}
        {result?.temporary_password && (
          <p className="rounded-md bg-secondary px-3 py-2">
            SMS isn't available — share this temporary password with the owner securely (shown once): <code className="font-mono font-semibold">{result.temporary_password}</code>
          </p>
        )}
        {pending && (
          <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <FormField label="Verification note (optional)">{(id) => <Input id={id} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Checked in bKash app" />}</FormField>
              <Button disabled={approve.isPending || reject.isPending} onClick={() => window.confirm(`Approve ${p.reference}? This creates the owner account, activates the ${p.plan} plan and sends the login details by SMS.`) && approve.mutate()}>
                {approve.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Approve payment
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              <FormField label="Rejection reason (shown to the applicant)">{(id) => <Textarea id={id} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}</FormField>
              <Checkbox label="Let them correct and resubmit" checked={allowResubmit} onChange={(e) => setAllowResubmit(e.target.checked)} />
              <Button variant="destructive" disabled={!reason.trim() || approve.isPending || reject.isPending} onClick={() => reject.mutate()}>
                {reject.isPending ? <Loader2 className="animate-spin" /> : <XCircle />} Reject payment
              </Button>
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}
