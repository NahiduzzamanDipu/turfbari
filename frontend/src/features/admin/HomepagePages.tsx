import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Save, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { fmtDateTime } from "@/lib/format";
import { api } from "@/lib/api";

interface FAQ { id: string; question_en: string; question_bn: string; answer_en: string; answer_bn: string; display_order: number; is_published: boolean }
const EMPTY_FAQ: Omit<FAQ, "id"> = { question_en: "", question_bn: "", answer_en: "", answer_bn: "", display_order: 0, is_published: false };

export function AdminHomepageFaqPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<FAQ | null>(null);
  const [creating, setCreating] = useState(false);
  const query = useQuery({ queryKey: ["admin", "homepage-faqs"], queryFn: () => api<FAQ[]>("/admin/homepage/faqs/") });
  const remove = useMutation({ mutationFn: (id: string) => api(`/admin/homepage/faqs/${id}/`, { method: "DELETE" }),
    onSuccess: () => { toast.success("FAQ deleted"); void qc.invalidateQueries({ queryKey: ["admin", "homepage-faqs"] }); },
    onError: (e) => toast.error(errorText(e)) });
  return <>
    <PageHeader title="Homepage FAQs" description="Manage bilingual answers displayed in the public homepage FAQ section." />
    <Card><CardHeader className="flex flex-row items-center justify-between gap-3"><CardTitle>Questions &amp; answers</CardTitle><Button onClick={() => setCreating(true)}><Plus /> Add question</Button></CardHeader>
      <CardContent className="p-2 sm:p-4">{query.isPending ? <Skeleton className="h-32" /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data?.length ? <EmptyState title="No homepage FAQs yet">Add and publish questions to show them on the homepage.</EmptyState> : <Table><thead><tr><th>Question</th><th>Order</th><th>Visibility</th><th /></tr></thead><tbody>{query.data.map((faq) => <tr key={faq.id}><td className="max-w-xl"><p className="font-semibold">{faq.question_en}</p><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{faq.answer_en}</p></td><td>{faq.display_order}</td><td><Badge tone={faq.is_published ? "green" : "neutral"}>{faq.is_published ? "Published" : "Draft"}</Badge></td><td className="text-right"><Button size="icon" variant="ghost" aria-label="Edit FAQ" onClick={() => setEditing(faq)}><Pencil /></Button><Button size="icon" variant="ghost" aria-label="Delete FAQ" onClick={() => remove.mutate(faq.id)}><Trash2 /></Button></td></tr>)}</tbody></Table>}</CardContent>
    </Card>
    <FaqDialog faq={editing} initial={creating ? EMPTY_FAQ : undefined} onClose={() => { setEditing(null); setCreating(false); }} />
  </>;
}

function FaqDialog({ faq, initial, onClose }: { faq: FAQ | null; initial?: Omit<FAQ, "id">; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Omit<FAQ, "id"> | null>(null);
  const current = form ?? (faq ? { question_en: faq.question_en, question_bn: faq.question_bn, answer_en: faq.answer_en,
    answer_bn: faq.answer_bn, display_order: faq.display_order, is_published: faq.is_published } : initial ?? null);
  const save = useMutation({ mutationFn: () => api(`/admin/homepage/faqs/${faq?.id ? `${faq.id}/` : ""}`, { method: faq ? "PUT" : "POST", json: current }),
    onSuccess: () => { toast.success("FAQ saved"); void qc.invalidateQueries({ queryKey: ["admin", "homepage-faqs"] }); setForm(null); onClose(); },
    onError: (e) => toast.error(errorText(e)) });
  return <Dialog open={Boolean(faq || initial)} onClose={() => { setForm(null); onClose(); }} title={faq ? "Edit FAQ" : "Add homepage FAQ"} description="Only published questions appear publicly.">
    {current && <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <FormField label="Question (English)">{(id) => <Input id={id} required maxLength={240} value={current.question_en} onChange={(e) => setForm({ ...current, question_en: e.target.value })} />}</FormField>
      <FormField label="Question (Bengali)">{(id) => <Input id={id} maxLength={240} value={current.question_bn} onChange={(e) => setForm({ ...current, question_bn: e.target.value })} />}</FormField>
      <FormField label="Answer (English)">{(id) => <Textarea id={id} required rows={4} value={current.answer_en} onChange={(e) => setForm({ ...current, answer_en: e.target.value })} />}</FormField>
      <FormField label="Answer (Bengali)">{(id) => <Textarea id={id} rows={4} value={current.answer_bn} onChange={(e) => setForm({ ...current, answer_bn: e.target.value })} />}</FormField>
      <FormField label="Display order">{(id) => <Input id={id} type="number" min={0} max={65535} value={current.display_order} onChange={(e) => setForm({ ...current, display_order: Number(e.target.value) })} />}</FormField>
      <Checkbox label="Publish on homepage" checked={current.is_published} onChange={(e) => setForm({ ...current, is_published: e.target.checked })} />
      <Button type="submit" disabled={save.isPending} className="self-end"><Save /> Save FAQ</Button>
    </form>}
  </Dialog>;
}

type OnboardingStatus = "pending" | "contacted" | "scheduled" | "in_progress" | "completed";
interface Onboarding { id: string; turf: string; turf_name: string; owner_name: string; owner_phone: string; plan_name: string | null; activation_date: string | null; status: OnboardingStatus; assigned_to: string | null; assigned_to_name: string | null; training_at: string | null; notes: string; topics: string[]; updated_at: string; events: { action: string; summary: string; created_at: string; actor: string }[] }
interface OnboardingResponse { results: Onboarding[]; support_users: { id: string; name: string }[]; plans: { period: string; name: string }[] }
const TOPICS = ["Account setup", "Turf profile", "Slots and pricing", "Booking management", "Payment verification", "Booking page and QR", "SMS wallet and messaging", "Staff management", "Reports and dashboard"];
const STATUSES: { value: OnboardingStatus; label: string }[] = [{ value: "pending", label: "Pending onboarding" }, { value: "contacted", label: "Contacted" }, { value: "scheduled", label: "Training scheduled" }, { value: "in_progress", label: "Training in progress" }, { value: "completed", label: "Completed" }];

export function AdminOnboardingPage() {
  const [status, setStatus] = useState(""); const [plan, setPlan] = useState(""); const [q, setQ] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [selected, setSelected] = useState<Onboarding | null>(null);
  const params = new URLSearchParams(); if (status) params.set("status", status); if (plan) params.set("plan", plan); if (q.trim()) params.set("q", q.trim()); if (from) params.set("from", from); if (to) params.set("to", to);
  const query = useQuery({ queryKey: ["admin", "onboarding", status, plan, q, from, to], queryFn: () => api<OnboardingResponse>(`/admin/onboarding/?${params}`) });
  return <>
    <PageHeader title="Onboarding & training" description="Track newly active turf accounts and coordinate practical product guidance. Availability and response times vary." />
    <Card><CardContent className="grid gap-3 pt-5 sm:grid-cols-3">
      <Input aria-label="Search turf or owner" placeholder="Search turf, owner or phone" value={q} onChange={(e) => setQ(e.target.value)} />
      <Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</Select>
      <Select aria-label="Filter by plan" value={plan} onChange={(e) => setPlan(e.target.value)}><option value="">All plans</option>{query.data?.plans.map((p) => <option key={p.period} value={p.period}>{p.name}</option>)}</Select>
      <Input aria-label="Activation from date" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      <Input aria-label="Activation through date" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
    </CardContent></Card>
    <Card className="mt-4"><CardContent className="p-2 sm:p-4">{query.isPending ? <Skeleton className="h-32" /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data?.results.length ? <EmptyState title="No active turf accounts found">Onboarding records appear here for currently subscribed active turfs.</EmptyState> : <Table><thead><tr><th>Turf &amp; owner</th><th>Plan</th><th>Activated</th><th>Onboarding</th><th>Training</th><th /></tr></thead><tbody>{query.data.results.map((item) => <tr key={item.id}><td className="font-semibold">{item.turf_name}<span className="block text-xs font-normal text-muted-foreground">{item.owner_name} · {item.owner_phone}</span></td><td>{item.plan_name || "—"}</td><td>{item.activation_date || "—"}</td><td><Badge tone={item.status === "completed" ? "green" : item.status === "pending" ? "amber" : "blue"}>{STATUSES.find((s) => s.value === item.status)?.label ?? item.status}</Badge></td><td>{item.training_at ? fmtDateTime(item.training_at) : "—"}</td><td className="text-right"><Button size="sm" variant="outline" onClick={() => setSelected(item)}>Manage</Button></td></tr>)}</tbody></Table>}</CardContent></Card>
    {selected && query.data && <OnboardingDialog item={selected} users={query.data.support_users} onClose={() => setSelected(null)} />}
  </>;
}

function OnboardingDialog({ item, users, onClose }: { item: Onboarding; users: OnboardingResponse["support_users"]; onClose: () => void }) {
  const qc = useQueryClient();
  const initial = useMemo(() => ({ status: item.status, assigned_to: item.assigned_to || "", training_at: item.training_at ? new Date(item.training_at).toISOString().slice(0, 16) : "", notes: item.notes, topics: item.topics }), [item]);
  const [form, setForm] = useState(initial);
  const save = useMutation({ mutationFn: () => api(`/admin/onboarding/${item.id}/`, { method: "PATCH", json: { ...form, assigned_to: form.assigned_to || null, training_at: form.training_at ? new Date(form.training_at).toISOString() : null } }),
    onSuccess: () => { toast.success("Onboarding updated"); void qc.invalidateQueries({ queryKey: ["admin", "onboarding"] }); onClose(); }, onError: (e) => toast.error(errorText(e)) });
  return <Dialog open onClose={onClose} title={`Onboarding · ${item.turf_name}`} description={`${item.plan_name ?? "No plan"}${item.activation_date ? ` · active since ${item.activation_date}` : ""}`} wide>
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2"><FormField label="Status">{(id) => <Select id={id} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as OnboardingStatus })}>{STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</Select>}</FormField>
        <FormField label="Assigned support staff">{(id) => <Select id={id} value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}><option value="">Unassigned</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select>}</FormField>
        <FormField label="Training date and time">{(id) => <Input id={id} type="datetime-local" value={form.training_at} onChange={(e) => setForm({ ...form, training_at: e.target.value })} />}</FormField>
      </div>
      <fieldset><legend className="mb-2 text-sm font-medium">Topics covered</legend><div className="grid gap-2 sm:grid-cols-2">{TOPICS.map((topic) => <Checkbox key={topic} label={topic} checked={form.topics.includes(topic)} onChange={(e) => setForm({ ...form, topics: e.target.checked ? [...form.topics, topic] : form.topics.filter((t) => t !== topic) })} />)}</div></fieldset>
      <FormField label="Internal notes">{(id) => <Textarea id={id} rows={4} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}</FormField>
      {!!item.events.length && <div><h3 className="mb-2 text-sm font-semibold">Recent history</h3><ol className="space-y-2">{item.events.map((event, i) => <li key={`${event.created_at}-${i}`} className="rounded-lg border px-3 py-2 text-sm"><span className="font-medium">{event.summary}</span><span className="block text-xs text-muted-foreground">{event.actor} · {fmtDateTime(event.created_at)}</span></li>)}</ol></div>}
      <Button type="submit" disabled={save.isPending} className="self-end"><Save /> Save changes</Button>
    </form>
  </Dialog>;
}
