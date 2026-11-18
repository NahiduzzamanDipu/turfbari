import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, Search, Trash2, Users, Wrench } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, EmptyState, ErrorState, FormField, Input, Select, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { PAYMENT_METHODS, addDays, dhakaISO, fmtDate, fmtDay, fmtRange, todayISO } from "@/lib/format";
import type { Customer, Expense, Maintenance, Paginated } from "@/lib/types";
import { cn, formatBDT } from "@/lib/utils";
import { errorText, useFields } from "./hooks";

// ------------------------------------------------------------------ customers
export function CustomersPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Partial<Customer> | null>(null);
  const list = useQuery({
    queryKey: ["ws", "customers", q, page],
    queryFn: () => api<Paginated<Customer>>(`/workspace/customers/?${new URLSearchParams({ q, page: String(page), sort: "recent" })}`),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: (c: Partial<Customer>) =>
      c.id
        ? api<Customer>(`/workspace/customers/${c.id}/`, { method: "PATCH", json: c })
        : api<Customer>("/workspace/customers/", { method: "POST", json: c }),
    onSuccess: () => {
      toast.success("Customer saved");
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["ws", "customers"] });
    },
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 20)) : 1;

  return (
    <>
      <PageHeader
        title="Customers"
        description="Everyone who has booked, identified by mobile number."
        actions={<Button onClick={() => setEditing({ name: "", phone: "", email: "", notes: "" })}><Plus /> Add customer</Button>}
      />
      <div className="relative mb-4 max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input aria-label="Search customers" placeholder="Search name, phone or email" className="pl-9" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-40" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.count === 0 && <EmptyState icon={<Users />} title="No customers yet" />}
          {list.data && list.data.count > 0 && (
            <Table className={cn(list.isFetching && "opacity-70")}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th className="text-right">Bookings</th>
                  <th className="text-right">Total paid</th>
                  <th>Last booking</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((c) => (
                  <tr key={c.id}>
                    <td className="font-medium">
                      {c.name}
                      {c.email && <span className="block text-xs text-muted-foreground">{c.email}</span>}
                    </td>
                    <td>
                      <a href={`tel:${c.phone}`} className="hover:text-primary">
                        {c.phone}
                      </a>
                    </td>
                    <td className="tabular text-right">
                      <Link className="hover:text-primary" to={`/workspace/bookings?view=list&q=${encodeURIComponent(c.phone)}`}>
                        {c.bookings_count}
                      </Link>
                    </td>
                    <td className="tabular text-right">{formatBDT(c.total_paid)}</td>
                    <td className="whitespace-nowrap">{c.last_booking ? fmtDate(c.last_booking) : "—"}</td>
                    <td className="text-right">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="text-sm">Page {page} of {pages}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          )}
        </CardContent>
      </Card>
      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing?.id ? "Edit customer" : "Add customer"}>
        {editing && (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(editing); }}>
            <FormField label="Name">{(id) => <Input id={id} required value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />}</FormField>
            <FormField label="Mobile number">{(id) => <Input id={id} required type="tel" value={editing.phone ?? ""} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} />}</FormField>
            <FormField label="Email">{(id) => <Input id={id} type="email" value={editing.email ?? ""} onChange={(e) => setEditing({ ...editing, email: e.target.value })} />}</FormField>
            <FormField label="Notes">{(id) => <Textarea id={id} rows={3} value={editing.notes ?? ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} />}</FormField>
            {save.error && <p className="text-sm text-destructive">{errorText(save.error)}</p>}
            <Button type="submit" disabled={save.isPending}>Save</Button>
          </form>
        )}
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------ maintenance
export function MaintenancePage() {
  const qc = useQueryClient();
  const fields = useFields();
  const blocks = useQuery({
    queryKey: ["ws", "maintenance"],
    queryFn: () => api<Paginated<Maintenance>>("/workspace/maintenance/?upcoming=1&page_size=100"),
  });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ field: "", day: addDays(todayISO(), 1), from: "06:00", to: "09:00", reason: "" });
  const add = useMutation({
    mutationFn: () =>
      api("/workspace/maintenance/", {
        method: "POST",
        json: { field: form.field || fields.data?.[0]?.id, start: dhakaISO(form.day, form.from), end: dhakaISO(form.day, form.to), reason: form.reason },
      }),
    onSuccess: () => {
      toast.success("Field blocked");
      setOpen(false);
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/maintenance/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws"] }),
  });

  return (
    <>
      <PageHeader
        title="Maintenance"
        description="Block a field for repairs or events. Blocked times can't be booked."
        actions={<Button onClick={() => setOpen(true)}><Wrench /> Block time</Button>}
      />
      {blocks.isPending && <Skeleton className="h-32" />}
      {blocks.isError && <ErrorState error={blocks.error} onRetry={() => blocks.refetch()} />}
      {blocks.data?.count === 0 && <EmptyState icon={<Wrench />} title="No upcoming maintenance" />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {blocks.data?.results.map((m) => (
          <Card key={m.id}>
            <CardContent className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold">{m.field_name}</p>
                <p className="text-sm">{fmtDay(m.start)}, {fmtRange(m.start, m.end)}</p>
                {m.reason && <p className="text-sm text-muted-foreground">{m.reason}</p>}
              </div>
              <Button size="icon" variant="ghost" aria-label="Remove block" onClick={() => remove.mutate(m.id)}>
                <Trash2 />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <Dialog open={open} onClose={() => setOpen(false)} title="Block a field">
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <FormField label="Field" className="sm:col-span-2">
            {(id) => (
              <Select id={id} value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })}>
                {fields.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </Select>
            )}
          </FormField>
          <FormField label="Date" className="sm:col-span-2">{(id) => <Input id={id} type="date" required value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} />}</FormField>
          <FormField label="From">{(id) => <Input id={id} type="time" step={900} required value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} />}</FormField>
          <FormField label="Until">{(id) => <Input id={id} type="time" step={900} required value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} />}</FormField>
          <FormField label="Reason" className="sm:col-span-2">{(id) => <Input id={id} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />}</FormField>
          {add.error && <p className="text-sm text-destructive sm:col-span-2">{errorText(add.error)}</p>}
          <Button type="submit" className="sm:col-span-2" disabled={add.isPending}>Block field</Button>
        </form>
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------ expenses
const CATEGORIES: Record<string, string> = {
  salary: "Salary",
  electricity: "Electricity",
  maintenance: "Maintenance",
  rent: "Rent",
  equipment: "Equipment",
  marketing: "Marketing",
  other: "Other",
};

export function ExpensesPage() {
  const qc = useQueryClient();
  const [range, setRange] = useState({ from: addDays(todayISO(), -29), to: todayISO() });
  const [form, setForm] = useState({ category: "electricity", amount: "", spent_on: todayISO(), note: "" });
  const list = useQuery({
    queryKey: ["ws", "expenses", range],
    queryFn: () => api<Paginated<Expense>>(`/workspace/expenses/?${new URLSearchParams({ ...range, page_size: "100" })}`),
    placeholderData: keepPreviousData,
  });
  const add = useMutation({
    mutationFn: () => api<Expense>("/workspace/expenses/", { method: "POST", json: form }),
    onSuccess: () => {
      toast.success("Expense added");
      setForm({ ...form, amount: "", note: "" });
      qc.invalidateQueries({ queryKey: ["ws"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/workspace/expenses/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws"] }),
  });
  const total = (list.data?.results ?? []).reduce((s, e) => s + Number(e.amount), 0);

  return (
    <>
      <PageHeader title="Expenses" description="Running costs, used for net profit in reports." />
      <div className="grid gap-6 xl:grid-cols-[22rem_1fr]">
        <Card className="h-fit">
          <CardHeader><CardTitle>Add expense</CardTitle></CardHeader>
          <CardContent>
            <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
              <FormField label="Category">
                {(id) => (
                  <Select id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                    {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </Select>
                )}
              </FormField>
              <FormField label="Amount (৳)">{(id) => <Input id={id} type="number" min={1} step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />}</FormField>
              <FormField label="Date">{(id) => <Input id={id} type="date" required value={form.spent_on} onChange={(e) => setForm({ ...form, spent_on: e.target.value })} />}</FormField>
              <FormField label="Note">{(id) => <Input id={id} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />}</FormField>
              {add.error && <p className="text-sm text-destructive">{errorText(add.error)}</p>}
              <Button type="submit" disabled={add.isPending}><Plus /> Add</Button>
            </form>
          </CardContent>
        </Card>
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Input type="date" aria-label="From" className="w-44" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} />
            <span className="text-muted-foreground">to</span>
            <Input type="date" aria-label="To" className="w-44" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} />
            <span className="ml-auto text-sm">Total <strong className="tabular">{formatBDT(total)}</strong></span>
          </div>
          <Card>
            <CardContent className="p-2 sm:p-4">
              {list.isPending && <Skeleton className="h-40" />}
              {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
              {list.data?.count === 0 && <EmptyState title="No expenses in this period" />}
              {list.data && list.data.count > 0 && (
                <Table>
                  <thead><tr><th>Date</th><th>Category</th><th>Note</th><th className="text-right">Amount</th><th /></tr></thead>
                  <tbody>
                    {list.data.results.map((e) => (
                      <tr key={e.id}>
                        <td className="whitespace-nowrap">{fmtDate(`${e.spent_on}T12:00:00+06:00`)}</td>
                        <td>{e.category_label}</td>
                        <td className="text-muted-foreground">{e.note}</td>
                        <td className="tabular text-right font-medium">{formatBDT(e.amount)}</td>
                        <td className="text-right">
                          <Button size="icon" variant="ghost" aria-label="Delete expense" onClick={() => window.confirm("Delete this expense?") && remove.mutate(e.id)}><Trash2 /></Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ reports
interface Report {
  from: string;
  to: string;
  revenue: string;
  billed: string;
  expenses: string;
  net: string;
  bookings: number;
  by_status: Record<string, number>;
  by_field: { field: string; bookings: number; billed: string; hours: number }[];
  by_method: { method: string; total: string }[];
  expenses_by_category: { category: string; total: string }[];
  daily: { date: string; revenue: string }[];
}

export function ReportsPage() {
  const [range, setRange] = useState({ from: addDays(todayISO(), -29), to: todayISO() });
  const report = useQuery({
    queryKey: ["ws", "report", range],
    queryFn: () => api<Report>(`/workspace/reports/summary/?${new URLSearchParams(range)}`),
    placeholderData: keepPreviousData,
  });
  const presets: [string, number][] = [["7 days", 6], ["30 days", 29], ["90 days", 89]];
  const r = report.data;

  return (
    <>
      <PageHeader
        title="Reports"
        description="Collections are payments actually received; billed is the value of bookings."
        actions={
          <Button asChild variant="outline">
            <a href={`/api/workspace/reports/bookings.xlsx?${new URLSearchParams(range)}`}>
              <Download /> Export bookings (Excel)
            </a>
          </Button>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-2">
        {presets.map(([label, days]) => (
          <Button key={label} size="sm" variant={range.from === addDays(range.to, -days) ? "default" : "outline"} onClick={() => setRange({ from: addDays(todayISO(), -days), to: todayISO() })}>
            {label}
          </Button>
        ))}
        <Input type="date" aria-label="From" className="w-44" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} />
        <span className="text-muted-foreground">to</span>
        <Input type="date" aria-label="To" className="w-44" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} />
      </div>
      {report.isPending && <Skeleton className="h-64" />}
      {report.isError && <ErrorState error={report.error} onRetry={() => report.refetch()} />}
      {r && (
        <div className={cn("flex flex-col gap-6", report.isFetching && "opacity-70")}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Collected" value={formatBDT(r.revenue)} hint={`Billed ${formatBDT(r.billed)}`} />
            <StatCard label="Expenses" value={formatBDT(r.expenses)} />
            <StatCard label="Net" value={<span className={Number(r.net) < 0 ? "text-destructive" : ""}>{formatBDT(r.net)}</span>} />
            <StatCard label="Bookings" value={r.bookings} hint={`${r.by_status.cancelled ?? 0} cancelled · ${r.by_status.no_show ?? 0} no-show`} />
          </div>
          <Card>
            <CardHeader><CardTitle>Daily collections</CardTitle></CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={r.daily.map((d) => ({ day: d.date.slice(5), revenue: Number(d.revenue) }))}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} />
                  <YAxis tickLine={false} axisLine={false} fontSize={12} width={56} tickFormatter={(v: number) => `৳${v >= 1000 ? `${v / 1000}k` : v}`} />
                  <Tooltip formatter={(v) => formatBDT(Number(v))} contentStyle={{ borderRadius: 8, border: "1px solid var(--border)" }} />
                  <Bar dataKey="revenue" name="Collected" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <div className="grid gap-6 xl:grid-cols-3">
            <Card>
              <CardHeader><CardTitle>By field</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <thead><tr><th>Field</th><th className="text-right">Bookings</th><th className="text-right">Hours</th><th className="text-right">Billed</th></tr></thead>
                  <tbody>
                    {r.by_field.map((f) => (
                      <tr key={f.field}><td>{f.field}</td><td className="tabular text-right">{f.bookings}</td><td className="tabular text-right">{f.hours}</td><td className="tabular text-right">{formatBDT(f.billed)}</td></tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>By payment method</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {r.by_method.length === 0 && <p className="text-muted-foreground">No payments.</p>}
                {r.by_method.map((m) => (
                  <div key={m.method} className="flex justify-between"><span>{PAYMENT_METHODS[m.method] ?? m.method}</span><span className="tabular font-medium">{formatBDT(m.total)}</span></div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Expenses by category</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {r.expenses_by_category.length === 0 && <p className="text-muted-foreground">No expenses.</p>}
                {r.expenses_by_category.map((c) => (
                  <div key={c.category} className="flex justify-between"><span>{CATEGORIES[c.category] ?? c.category}</span><span className="tabular font-medium">{formatBDT(c.total)}</span></div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
