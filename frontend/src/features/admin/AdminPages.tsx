import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Building2, ClipboardList, Copy, Inbox, Plus, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Badge,
  Checkbox,
  Dialog,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  STATUS_TONE,
  Select,
  Table,
  Textarea,
} from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useLocations } from "@/features/public/shared";
import { ApiError, api } from "@/lib/api";
import { TURF_TYPE_LABEL, fmtDate } from "@/lib/format";
import type { AdminTurf, Application, Paginated } from "@/lib/types";
import { formatBDT } from "@/lib/utils";
import { AssignPlanDialog, PERIOD_TONE, PlanPicker, TurfPlanCell } from "./BillingPages";

interface AdminDashboard {
  turfs: { total: number; active: number; suspended: number; listed: number };
  applications_pending: number;
  bookings_this_month: number;
  payments_this_month: string;
  users: number;
  recent_applications: Application[];
  new_turfs_30d: number;
  plans: { period: string; name: string; turfs: number }[];
  payments_to_verify: number;
}

export function AdminDashboardPage() {
  const data = useQuery({ queryKey: ["admin", "dashboard"], queryFn: () => api<AdminDashboard>("/admin/dashboard/") });
  return (
    <>
      <PageHeader title="Platform overview" description="Every turf on TurfBari at a glance." />
      {data.isError && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
      {data.isPending && <Skeleton className="h-28" />}
      {data.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Active turfs"
              icon={<Building2 />}
              value={data.data.turfs.active}
              hint={`${data.data.turfs.listed} listed · ${data.data.turfs.suspended} suspended`}
            />
            <StatCard
              label="Applications to review"
              icon={<Inbox />}
              value={data.data.applications_pending}
              hint={<Link to="/admin/applications" className="text-primary hover:underline">Open pipeline</Link>}
            />
            <StatCard label="Bookings this month" icon={<ClipboardList />} value={data.data.bookings_this_month} />
            <StatCard
              label="Payments recorded this month"
              icon={<Wallet />}
              value={formatBDT(data.data.payments_this_month)}
              hint={`${data.data.users} active users`}
            />
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {data.data.plans.map((p) => (
              <Link key={p.period} to={`/admin/turfs?plan=${p.period}`} className="glass rounded-xl p-4 transition hover:shadow-md">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>Turfs on</span>
                  <Badge tone={PERIOD_TONE[p.period] ?? "neutral"}>{p.name}</Badge>
                </div>
                <p className="tabular mt-2 text-2xl font-bold">{p.turfs}</p>
              </Link>
            ))}
            <StatCard
              label="Payments to verify"
              icon={<BadgeCheck />}
              value={data.data.payments_to_verify}
              hint={<Link to="/admin/billing" className="text-primary hover:underline">Plans & payments</Link>}
            />
          </div>
          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Latest applications</CardTitle>
            </CardHeader>
            <CardContent>
              <ApplicationsTable rows={data.data.recent_applications} onOpen={() => undefined} compact />
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}

function ApplicationsTable({
  rows,
  onOpen,
  compact,
}: {
  rows: Application[];
  onOpen: (a: Application) => void;
  compact?: boolean;
}) {
  if (rows.length === 0) return <EmptyState icon={<Inbox />} title="No applications yet" />;
  return (
    <Table>
      <thead>
        <tr>
          <th>Turf</th>
          <th>Owner</th>
          <th>Location</th>
          <th>Received</th>
          <th>Status</th>
          {!compact && <th />}
        </tr>
      </thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id}>
            <td className="font-medium">{a.turf_name}</td>
            <td>
              {a.owner_name}
              <span className="block text-xs text-muted-foreground">{a.phone}</span>
            </td>
            <td>{[a.area_name, a.district_name].filter(Boolean).join(", ")}</td>
            <td className="whitespace-nowrap">{fmtDate(a.created_at)}</td>
            <td>
              <Badge tone={STATUS_TONE[a.status]} className="capitalize">
                {a.status}
              </Badge>
            </td>
            {!compact && (
              <td className="text-right">
                <Button size="sm" variant="outline" onClick={() => onOpen(a)}>
                  Review
                </Button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function AdminApplicationsPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("pending");
  const [open, setOpen] = useState<Application | null>(null);
  const [note, setNote] = useState("");
  const [rate, setRate] = useState("1500");
  const [plan, setPlan] = useState({ plan: "monthly", payment_received: true });
  const [credentials, setCredentials] = useState<{ email: string; password: string | null; slug: string } | null>(null);

  const list = useQuery({
    queryKey: ["admin", "applications", status],
    queryFn: () => api<Paginated<Application>>(`/admin/applications/?status=${status}`),
    placeholderData: keepPreviousData,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin"] });

  const update = useMutation({
    mutationFn: (body: Partial<Application>) =>
      api<Application>(`/admin/applications/${open?.id}/`, { method: "PATCH", json: body }),
    onSuccess: () => {
      toast.success("Application updated");
      setOpen(null);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });
  const approve = useMutation({
    mutationFn: () =>
      api<{ owner_email: string; temporary_password: string | null; turf: { slug: string } }>(
        `/admin/applications/${open?.id}/approve/`,
        { method: "POST", json: { hourly_rate: rate, ...plan } },
      ),
    onSuccess: (r) => {
      setOpen(null);
      setCredentials({ email: r.owner_email, password: r.temporary_password, slug: r.turf.slug });
      refresh();
    },
    onError: (e) => toast.error(e instanceof ApiError && e.fields ? Object.values(e.fields).flat()[0] ?? e.message : e.message),
  });

  return (
    <>
      <PageHeader title="Applications" description="Turf owners who asked to join TurfBari." />
      <div className="mb-4 flex flex-wrap gap-2">
        {["pending", "contacted", "approved", "rejected", ""].map((s) => (
          <Button key={s || "all"} size="sm" variant={status === s ? "default" : "outline"} onClick={() => setStatus(s)} className="capitalize">
            {s || "All"}
          </Button>
        ))}
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-40" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data && (
            <ApplicationsTable
              rows={list.data.results}
              onOpen={(a) => {
                setOpen(a);
                setNote(a.admin_note);
              }}
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={open !== null} onClose={() => setOpen(null)} title={open?.turf_name ?? ""} description="Review and decide." wide>
        {open && (
          <div className="flex flex-col gap-4">
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {[
                ["Owner", open.owner_name],
                ["Phone", open.phone],
                ["Email", open.email],
                ["Type", TURF_TYPE_LABEL[open.turf_type] ?? open.turf_type],
                ["Fields", String(open.number_of_fields)],
                ["Location", [open.area_name, open.district_name].filter(Boolean).join(", ")],
                ["Address", open.address],
                ["Received", fmtDate(open.created_at)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="break-words font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            {open.message && <p className="rounded-md bg-secondary p-3 text-sm">{open.message}</p>}
            {open.status === "approved" ? (
              <p className="text-sm">
                Approved{open.reviewed_by_email && ` by ${open.reviewed_by_email}`}.{" "}
                {open.turf_slug && (
                  <a className="text-primary hover:underline" href={`/turfs/${open.turf_slug}`} target="_blank" rel="noreferrer">
                    View turf
                  </a>
                )}
              </p>
            ) : (
              <>
                <FormField label="Internal note">
                  {(id) => <Textarea id={id} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
                </FormField>
                <FormField label="Starting hourly rate (৳)" hint="Applied to every field; the owner can change it later.">
                  {(id) => <Input id={id} type="number" min={0} step={50} value={rate} onChange={(e) => setRate(e.target.value)} />}
                </FormField>
                <PlanPicker value={plan} onChange={setPlan} />
                <div className="flex flex-wrap justify-end gap-2">
                  <Button variant="outline" onClick={() => update.mutate({ status: "contacted", admin_note: note })} disabled={update.isPending}>
                    Mark contacted
                  </Button>
                  <Button variant="destructive" onClick={() => update.mutate({ status: "rejected", admin_note: note })} disabled={update.isPending || open.status === "rejected"}>
                    Reject
                  </Button>
                  {open.status === "rejected" ? (
                    <Button onClick={() => update.mutate({ status: "pending", admin_note: note })}>Reopen</Button>
                  ) : (
                    <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
                      Approve & create turf
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </Dialog>
      <CredentialsDialog value={credentials} onClose={() => setCredentials(null)} />
    </>
  );
}

function CredentialsDialog({
  value,
  onClose,
}: {
  value: { email: string; password: string | null; slug: string } | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={value !== null} onClose={onClose} title="Turf created" description="Share the owner login securely. The password is shown only once.">
      {value && (
        <div className="flex flex-col gap-3 text-sm">
          <p>
            Owner email: <span className="font-semibold">{value.email}</span>
          </p>
          {value.password ? (
            <div className="flex items-center gap-2 rounded-md bg-secondary p-3">
              <code className="flex-1 font-mono text-base">{value.password}</code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigator.clipboard.writeText(value.password ?? "").then(() => toast.success("Copied"))}
              >
                <Copy /> Copy
              </Button>
            </div>
          ) : (
            <p className="text-muted-foreground">This owner already had an account, so their existing password still works.</p>
          )}
          <p className="text-muted-foreground">
            The turf is not public yet. The owner can list it from Workspace → Settings, or you can list it from Turfs.
          </p>
          <Button onClick={onClose}>Done</Button>
        </div>
      )}
    </Dialog>
  );
}

const NEW_TURF = {
  name: "",
  district: "",
  area: "",
  address: "",
  turf_type: "outdoor",
  owner_name: "",
  owner_email: "",
  owner_phone: "",
  number_of_fields: "1",
  hourly_rate: "1500",
  plan: "monthly",
  payment_received: true,
};

export function AdminTurfsPage() {
  const qc = useQueryClient();
  const locations = useLocations();
  const [params, setParams] = useSearchParams();
  const plan = params.get("plan") ?? "";
  const setPlan = (value: string) => setParams(value ? { plan: value } : {}, { replace: true });
  const [planFor, setPlanFor] = useState<AdminTurf | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(NEW_TURF);
  const [credentials, setCredentials] = useState<{ email: string; password: string | null; slug: string } | null>(null);

  const list = useQuery({
    queryKey: ["admin", "turfs", q, status, plan],
    queryFn: () => api<Paginated<AdminTurf>>(`/admin/turfs/?${new URLSearchParams({ q, status, plan })}`),
    placeholderData: keepPreviousData,
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<AdminTurf> }) =>
      api<AdminTurf>(`/admin/turfs/${id}/`, { method: "PATCH", json: body }),
    onSuccess: () => {
      toast.success("Turf updated");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast.error(e.message),
  });
  const create = useMutation({
    mutationFn: () =>
      api<{ owner_email: string; temporary_password: string | null; turf: AdminTurf }>("/admin/turfs/", {
        method: "POST",
        json: { ...form, area: form.area || null, number_of_fields: Number(form.number_of_fields) },
      }),
    onSuccess: (r) => {
      setCreating(false);
      setForm(NEW_TURF);
      setCredentials({ email: r.owner_email, password: r.temporary_password, slug: r.turf.slug });
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const errors = create.error instanceof ApiError ? create.error.fields : null;
  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));
  const areas = districts.find((d) => d.slug === form.district)?.areas ?? [];
  const set = (key: Exclude<keyof typeof NEW_TURF, "payment_received">) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      <PageHeader
        title="Turfs"
        description="Suspend, list or feature turfs across the platform."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> Add turf
          </Button>
        }
      />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Search turfs or owners" aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="sm:max-w-48">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="archived">Archived</option>
        </Select>
        <Select aria-label="Plan" value={plan} onChange={(e) => setPlan(e.target.value)} className="sm:max-w-48">
          <option value="">All plans</option>
          <option value="monthly">Monthly</option>
          <option value="half_yearly">Half-yearly</option>
          <option value="yearly">Yearly</option>
          <option value="none">No active plan</option>
        </Select>
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-40" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.results.length === 0 && <EmptyState icon={<Building2 />} title="No turfs found" />}
          {list.data && list.data.results.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Turf</th>
                  <th>Owner</th>
                  <th>Plan</th>
                  <th>Fields</th>
                  <th>Bookings</th>
                  <th>Status</th>
                  <th>Public</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <a href={`/turfs/${t.slug}`} target="_blank" rel="noreferrer" className="font-medium hover:text-primary">
                        {t.name}
                      </a>
                      <span className="block text-xs text-muted-foreground">
                        {[t.area_name, t.district_name].filter(Boolean).join(", ")}
                        {t.min_public_price && ` · from ${formatBDT(t.min_public_price)}`}
                      </span>
                    </td>
                    <td>
                      {t.owner_name}
                      <span className="block text-xs text-muted-foreground">{t.owner_email}</span>
                    </td>
                    <td>
                      <TurfPlanCell turf={t} onChange={() => setPlanFor(t)} />
                    </td>
                    <td className="tabular">{t.fields_count}</td>
                    <td className="tabular">{t.bookings_count}</td>
                    <td>
                      <Select
                        aria-label={`Status of ${t.name}`}
                        value={t.status}
                        className="h-8 w-32 text-xs"
                        onChange={(e) => patch.mutate({ id: t.id, body: { status: e.target.value as AdminTurf["status"] } })}
                      >
                        <option value="active">Active</option>
                        <option value="suspended">Suspended</option>
                        <option value="archived">Archived</option>
                      </Select>
                    </td>
                    <td>
                      <div className="flex flex-col gap-1">
                        <Checkbox label="Listed" checked={t.is_listed} onChange={(e) => patch.mutate({ id: t.id, body: { is_listed: e.target.checked } })} />
                        <Checkbox label="Featured" checked={t.is_featured} onChange={(e) => patch.mutate({ id: t.id, body: { is_featured: e.target.checked } })} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={creating} onClose={() => setCreating(false)} title="Add a turf" description="Creates the turf, default hours and fields, and the owner's login." wide>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <FormField label="Turf name" error={errors?.name} className="sm:col-span-2">
            {(id) => <Input id={id} required value={form.name} onChange={set("name")} />}
          </FormField>
          <FormField label="District" error={errors?.district}>
            {(id) => (
              <Select id={id} required value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value, area: "" })}>
                <option value="">Choose…</option>
                {districts.map((d) => (
                  <option key={d.slug} value={d.slug}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <FormField label="Area" error={errors?.area}>
            {(id) => (
              <Select id={id} value={form.area} onChange={set("area")} disabled={!areas.length}>
                <option value="">—</option>
                {areas.map((a) => (
                  <option key={a.slug} value={a.slug}>
                    {a.name}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <FormField label="Address" error={errors?.address} className="sm:col-span-2">
            {(id) => <Input id={id} required value={form.address} onChange={set("address")} />}
          </FormField>
          <FormField label="Owner name" error={errors?.owner_name}>
            {(id) => <Input id={id} required value={form.owner_name} onChange={set("owner_name")} />}
          </FormField>
          <FormField label="Owner mobile" error={errors?.owner_phone}>
            {(id) => <Input id={id} required type="tel" value={form.owner_phone} onChange={set("owner_phone")} />}
          </FormField>
          <FormField label="Owner email" error={errors?.owner_email ?? errors?.email} className="sm:col-span-2">
            {(id) => <Input id={id} required type="email" value={form.owner_email} onChange={set("owner_email")} />}
          </FormField>
          <FormField label="Type">
            {(id) => (
              <Select id={id} value={form.turf_type} onChange={set("turf_type")}>
                <option value="outdoor">Outdoor</option>
                <option value="indoor">Indoor</option>
                <option value="rooftop">Rooftop</option>
              </Select>
            )}
          </FormField>
          <FormField label="Fields" error={errors?.number_of_fields}>
            {(id) => <Input id={id} type="number" min={1} max={20} value={form.number_of_fields} onChange={set("number_of_fields")} />}
          </FormField>
          <FormField label="Hourly rate (৳)" error={errors?.hourly_rate}>
            {(id) => <Input id={id} type="number" min={0} step={50} value={form.hourly_rate} onChange={set("hourly_rate")} />}
          </FormField>
          <PlanPicker
            value={{ plan: form.plan, payment_received: form.payment_received }}
            onChange={(v) => setForm({ ...form, ...v })}
          />
          {create.error && !errors && <p className="text-sm text-destructive sm:col-span-2">{create.error.message}</p>}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="outline" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Create turf
            </Button>
          </div>
        </form>
      </Dialog>
      <CredentialsDialog value={credentials} onClose={() => setCredentials(null)} />
      <AssignPlanDialog key={planFor?.id ?? "none"} turf={planFor} onClose={() => setPlanFor(null)} />
    </>
  );
}

