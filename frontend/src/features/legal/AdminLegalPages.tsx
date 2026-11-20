import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FilePlus2,
  FileText,
  GitCompare,
  Layers,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Scale,
  Send,
  Trash2,
  Undo2,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { PageHeader, StatCard } from "@/components/layout/AppShell";
import { type Lang, LangToggle, LegalHtml, legalDateTime } from "@/components/legal/Legal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RichTextEditor } from "./RichTextEditor";

// ------------------------------------------------------------------ types
interface Sector {
  id: string;
  slug: string;
  name_en: string;
  name_bn: string;
  is_active?: boolean;
  sort_order?: number;
  turfs?: number;
  documents?: number;
}
interface VersionSummary {
  id: number;
  version: number;
  status: "draft" | "published" | "archived";
  state: "draft" | "current" | "scheduled" | "superseded" | "withdrawn" | "archived";
  title_en: string;
  title_bn: string;
  change_summary: string;
  reacceptance: string;
  reaccept_sector: string | null;
  effective_at: string | null;
  published_at: string | null;
  published_by: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  has_en: boolean;
  has_bn: boolean;
}
interface DocumentRow {
  id: string;
  category: string;
  category_label: string;
  sector: Sector | null;
  scope: "platform" | "sector";
  slug: string;
  audiences: string[];
  actions: string[];
  is_mandatory: boolean;
  is_archived: boolean;
  url: string;
  current: VersionSummary | null;
  draft: VersionSummary | null;
  versions: VersionSummary[];
  acceptances: number;
  updated_at: string;
}
interface Choice {
  value: string;
  label: string;
}
interface DocumentsPayload {
  documents: DocumentRow[];
  sectors: Sector[];
  categories: Choice[];
  audiences: Choice[];
  actions: Choice[];
  reacceptance: Choice[];
}
interface VersionDetail extends VersionSummary {
  document: DocumentRow;
  body_en: string;
  body_bn: string;
  acceptances: number;
}
interface Overview {
  documents: number;
  published: number;
  drafts: number;
  scheduled: number;
  sectors: number;
  acceptances: number;
  acceptances_30d: number;
  pending_accounts: number;
  unpublished_modules: { id: string; label: string }[];
  recent: { document: string; document_id: string; version: number; published_at: string; by: string | null }[];
}
interface AcceptanceRow {
  id: number;
  accepted_at: string;
  person: string | null;
  turf: string | null;
  booking: string | null;
  document: string;
  category: string;
  sector: string | null;
  version: number;
  action_label: string;
  related_ref: string;
}

const STATE_TONE: Record<VersionSummary["state"], BadgeTone> = {
  draft: "amber",
  current: "green",
  scheduled: "blue",
  superseded: "neutral",
  withdrawn: "red",
  archived: "neutral",
};

const docsKey = ["admin", "legal", "documents"] as const;
const useDocuments = () => useQuery({ queryKey: docsKey, queryFn: () => api<DocumentsPayload>("/admin/legal/documents/") });

/** Shown wherever documents are written: the platform provides the tools, not legal advice. */
function LegalReviewNotice() {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
      <AlertTriangle className="mt-0.5 size-5 shrink-0" />
      <p>
        These tools manage, version and record agreement to your documents — they don't check whether the wording is legally
        sufficient. Have a qualified legal professional in Bangladesh review each document (especially privacy, refunds and
        payments) before publishing.
      </p>
    </div>
  );
}

function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-5 flex flex-wrap gap-2" role="tablist">
      {tabs.map(([k, label]) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={value === k}
          onClick={() => onChange(k)}
          className={cn("rounded-full border px-3 py-1.5 text-sm font-medium", value === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ main page
export function AdminLegalPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  return (
    <>
      <PageHeader
        title="Legal & Compliance"
        description="Platform-wide terms, policies and sector rules: versioned, bilingual, with a permanent record of who accepted which version."
        actions={
          <Button asChild variant="outline">
            <a href="/legal" target="_blank" rel="noreferrer">
              <Eye /> Public legal centre
            </a>
          </Button>
        }
      />
      <LegalReviewNotice />
      <Tabs
        tabs={[
          ["overview", "Overview"],
          ["documents", "Documents"],
          ["sectors", "Sectors"],
          ["acceptances", "Acceptance records"],
        ]}
        value={tab}
        onChange={(t) => setParams(t === "overview" ? {} : { tab: t })}
      />
      {tab === "overview" && <OverviewTab />}
      {tab === "documents" && <DocumentsTab />}
      {tab === "sectors" && <SectorsTab />}
      {tab === "acceptances" && <AcceptancesTab />}
    </>
  );
}

function OverviewTab() {
  const data = useQuery({ queryKey: ["admin", "legal", "overview"], queryFn: () => api<Overview>("/admin/legal/") });
  const pending = useQuery({
    queryKey: ["admin", "legal", "pending"],
    queryFn: () => api<{ results: { user_id: string; name: string; email: string; roles: string[]; turfs: string[]; pending: string[] }[] }>("/admin/legal/pending/"),
  });
  if (data.isPending) return <Skeleton className="h-64" />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  const d = data.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Published documents" value={`${d.published} / ${d.documents}`} icon={<FileText />} hint={`${d.drafts} draft${d.drafts === 1 ? "" : "s"}, ${d.scheduled} scheduled`} />
        <StatCard label="Sectors" value={d.sectors} icon={<Layers />} />
        <StatCard label="Acceptance records" value={d.acceptances.toLocaleString()} icon={<Scale />} hint={`${d.acceptances_30d.toLocaleString()} in the last 30 days`} />
        <StatCard label="Accounts yet to accept" value={d.pending_accounts} icon={<Users />} hint="Owners/managers blocked at sign-in" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recently published</CardTitle>
          </CardHeader>
          <CardContent>
            {d.recent.length === 0 ? (
              <EmptyState title="Nothing published yet" />
            ) : (
              <ul className="divide-y text-sm">
                {d.recent.map((r) => (
                  <li key={`${r.document_id}-${r.version}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <Link to={`/admin/legal/documents/${r.document_id}`} className="font-medium hover:underline">
                      {r.document} v{r.version}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {legalDateTime(r.published_at)}
                      {r.by && ` · ${r.by}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Not published yet</CardTitle>
            <CardDescription>Unpublished modules are never shown or required. Publish them once the text is ready and reviewed.</CardDescription>
          </CardHeader>
          <CardContent>
            {d.unpublished_modules.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every module has a published version.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {d.unpublished_modules.map((m) => (
                  <li key={m.id}>
                    <Link to={`/admin/legal/documents/${m.id}`} className="inline-block rounded-full border px-3 py-1 text-xs font-medium hover:bg-secondary">
                      {m.label}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Accounts that still have to accept</CardTitle>
          <CardDescription>They can't use their workspace until they accept on their next sign-in.</CardDescription>
        </CardHeader>
        <CardContent>
          {pending.data?.results.length ? (
            <Table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Business</th>
                  <th>Waiting for</th>
                </tr>
              </thead>
              <tbody>
                {pending.data.results.map((p) => (
                  <tr key={p.user_id}>
                    <td>
                      {p.name}
                      <span className="block text-xs text-muted-foreground">{p.roles.join(", ")}</span>
                    </td>
                    <td>{p.turfs.join(", ")}</td>
                    <td className="text-xs">{p.pending.join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">{pending.isPending ? "Loading…" : "Everyone is up to date."}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DocumentsTab() {
  const data = useDocuments();
  const [filter, setFilter] = useState("all");
  const [adding, setAdding] = useState(false);
  if (data.isPending) return <Skeleton className="h-96" />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  const rows = data.data.documents.filter((d) => filter === "all" || (filter === "platform" ? d.scope === "platform" : d.sector?.slug === filter));
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <Select aria-label="Filter documents" className="w-auto" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All documents</option>
          <option value="platform">Platform-wide</option>
          {data.data.sectors.map((s) => (
            <option key={s.slug} value={s.slug}>
              Sector: {s.name_en}
            </option>
          ))}
        </Select>
        <Button variant="outline" onClick={() => setAdding(true)}>
          <Plus /> Add sector document
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Applies to</th>
              <th>Current</th>
              <th>Draft</th>
              <th>Acceptances</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id} className={cn(d.is_archived && "opacity-60")}>
                <td>
                  <Link to={`/admin/legal/documents/${d.id}`} className="font-medium hover:underline">
                    {d.category_label}
                  </Link>
                  <span className="block text-xs text-muted-foreground">
                    {d.sector ? d.sector.name_en : "Platform-wide"}
                    {!d.is_mandatory && " · optional"}
                    {d.is_archived && " · retired"}
                  </span>
                </td>
                <td className="text-xs">
                  {d.audiences.join(", ") || "—"}
                  <span className="block text-muted-foreground">at: {d.actions.join(", ") || "—"}</span>
                </td>
                <td>{d.current ? <Badge tone="green">v{d.current.version}</Badge> : <span className="text-xs text-muted-foreground">Not published</span>}</td>
                <td>{d.draft ? <Badge tone="amber">v{d.draft.version} draft</Badge> : "—"}</td>
                <td className="tabular">{d.acceptances.toLocaleString()}</td>
                <td className="whitespace-nowrap">
                  {d.draft && (
                    <Button asChild size="sm" className="mr-1">
                      <Link to={`/admin/legal/versions/${d.draft.id}/edit`}>
                        <Pencil /> Edit
                      </Link>
                    </Button>
                  )}
                  <Button asChild size="sm" variant="outline">
                    <Link to={`/admin/legal/documents/${d.id}`}>Open</Link>
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </CardContent>
      {adding && <AddDocumentDialog data={data.data} onClose={() => setAdding(false)} />}
    </Card>
  );
}

function AddDocumentDialog({ data, onClose }: { data: DocumentsPayload; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [category, setCategory] = useState("booking");
  const [sector, setSector] = useState(data.sectors[0]?.slug ?? "");
  const create = useMutation({
    mutationFn: () => api<DocumentRow>("/admin/legal/documents/", { method: "POST", json: { category, sector } }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["admin", "legal"] });
      navigate(`/admin/legal/documents/${d.id}`);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Dialog open onClose={onClose} title="Add a sector document" description="A sector document adds to the platform documents for businesses in that sector — it never replaces them.">
      <div className="flex flex-col gap-4">
        <FormField label="Sector">
          {(id) => (
            <Select id={id} value={sector} onChange={(e) => setSector(e.target.value)}>
              {data.sectors.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name_en}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        <FormField label="Document type">
          {(id) => (
            <Select id={id} value={category} onChange={(e) => setCategory(e.target.value)}>
              {data.categories.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        <Button disabled={!sector || create.isPending} onClick={() => create.mutate()}>
          {create.isPending && <Loader2 className="animate-spin" />} Create
        </Button>
      </div>
    </Dialog>
  );
}

function SectorsTab() {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["admin", "legal", "sectors"], queryFn: () => api<{ sectors: Sector[] }>("/admin/legal/sectors/") });
  const [form, setForm] = useState({ name_en: "", name_bn: "", slug: "" });
  const add = useMutation({
    mutationFn: () => api("/admin/legal/sectors/", { method: "POST", json: form }),
    onSuccess: () => {
      toast.success("Sector added with empty Terms and Rules modules");
      setForm({ name_en: "", name_bn: "", slug: "" });
      qc.invalidateQueries({ queryKey: ["admin", "legal"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const toggle = useMutation({
    mutationFn: (s: Sector) => api(`/admin/legal/sectors/${s.id}/`, { method: "PATCH", json: { is_active: !s.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "legal"] }),
    onError: (e) => toast.error(errorText(e)),
  });
  if (data.isPending) return <Skeleton className="h-64" />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <Card>
        <CardHeader>
          <CardTitle>Business sectors</CardTitle>
          <CardDescription>Each business belongs to one sector; its sector's documents are added to the platform documents.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <thead>
              <tr>
                <th>Sector</th>
                <th>URL</th>
                <th>Businesses</th>
                <th>Documents</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.data.sectors.map((s) => (
                <tr key={s.id} className={cn(!s.is_active && "opacity-60")}>
                  <td>
                    {s.name_en}
                    {s.name_bn && <span className="block text-xs text-muted-foreground">{s.name_bn}</span>}
                  </td>
                  <td className="font-mono text-xs">/legal/sector/{s.slug}</td>
                  <td className="tabular">{s.turfs}</td>
                  <td className="tabular">{s.documents}</td>
                  <td>
                    <Button size="sm" variant="outline" disabled={toggle.isPending} onClick={() => toggle.mutate(s)}>
                      {s.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Add a sector</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate();
            }}
          >
            <FormField label="Name (English)">{(id) => <Input id={id} required value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} />}</FormField>
            <FormField label="Name (Bengali)">{(id) => <Input id={id} lang="bn" value={form.name_bn} onChange={(e) => setForm({ ...form, name_bn: e.target.value })} />}</FormField>
            <FormField label="URL name" hint="Letters, numbers and dashes. Leave empty to generate.">
              {(id) => <Input id={id} pattern="[a-z0-9-]*" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase() })} />}
            </FormField>
            <Button type="submit" disabled={add.isPending || !form.name_en.trim()}>
              {add.isPending && <Loader2 className="animate-spin" />} Add sector
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function AcceptancesTab() {
  const docs = useDocuments();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const query = new URLSearchParams({ page: String(page), ...(search && { q: search }), ...(action && { action }), ...(category && { category }) });
  const list = useQuery({
    queryKey: ["admin", "legal", "acceptances", query.toString()],
    queryFn: () => api<{ count: number; page: number; pages: number; results: AcceptanceRow[] }>(`/admin/legal/acceptances/?${query}`),
    placeholderData: keepPreviousData,
  });
  const exportQuery = new URLSearchParams(query);
  exportQuery.delete("page");
  exportQuery.set("export", "csv");
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3">
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setSearch(q.trim());
          }}
        >
          <Input aria-label="Search" placeholder="Name, email, business, booking ref…" className="w-64" value={q} onChange={(e) => setQ(e.target.value)} />
          <Select aria-label="Action" className="w-auto" value={action} onChange={(e) => (setPage(1), setAction(e.target.value))}>
            <option value="">Any action</option>
            {docs.data?.actions.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
          <Select aria-label="Document" className="w-auto" value={category} onChange={(e) => (setPage(1), setCategory(e.target.value))}>
            <option value="">Any document</option>
            {docs.data?.categories.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
          <Button type="submit" variant="outline">
            Search
          </Button>
          <Button asChild variant="outline" className="ml-auto">
            <a href={`/api/admin/legal/acceptances/?${exportQuery}`}>
              <Download /> Export CSV
            </a>
          </Button>
        </form>
        <p className="text-xs text-muted-foreground">
          Records are permanent and can't be edited. Customer phone numbers and IP addresses are not shown — bookings are identified by reference.
        </p>
      </CardHeader>
      <CardContent>
        {list.isPending && <Skeleton className="h-64" />}
        {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data && list.data.results.length === 0 && <EmptyState title="No acceptance records match" />}
        {list.data && list.data.results.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <th>When (BD)</th>
                  <th>Who</th>
                  <th>Business / booking</th>
                  <th>Document</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((r) => (
                  <tr key={r.id}>
                    <td className="whitespace-nowrap text-xs">{legalDateTime(r.accepted_at)}</td>
                    <td>{r.person ?? <span className="text-muted-foreground">Customer</span>}</td>
                    <td>
                      {r.turf ?? "—"}
                      {r.booking && <span className="block font-mono text-xs text-muted-foreground">{r.booking}</span>}
                    </td>
                    <td>
                      {r.document} <span className="text-muted-foreground">v{r.version}</span>
                      {r.sector && <span className="block text-xs text-muted-foreground">{r.sector}</span>}
                    </td>
                    <td className="text-xs">{r.action_label}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="mt-3 flex items-center justify-end gap-2 text-sm">
              <span className="text-muted-foreground">
                {list.data.count.toLocaleString()} records · page {list.data.page} of {list.data.pages}
              </span>
              <Button size="icon" variant="outline" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft />
              </Button>
              <Button size="icon" variant="outline" aria-label="Next page" disabled={page >= list.data.pages} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight />
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ one document
export function AdminLegalDocumentPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const docs = useDocuments();
  const doc = useQuery({ queryKey: ["admin", "legal", "document", id], queryFn: () => api<DocumentRow>(`/admin/legal/documents/${id}/`) });
  const [viewing, setViewing] = useState<number | null>(null);
  const [compare, setCompare] = useState<number[]>([]);
  const [settings, setSettings] = useState<Pick<DocumentRow, "audiences" | "actions" | "is_mandatory"> | null>(null);
  useEffect(() => {
    if (doc.data) setSettings({ audiences: doc.data.audiences, actions: doc.data.actions, is_mandatory: doc.data.is_mandatory });
  }, [doc.data]);

  const newDraft = useMutation({
    mutationFn: () => api<VersionDetail>(`/admin/legal/documents/${id}/versions/`, { method: "POST" }),
    onSuccess: (v) => navigate(`/admin/legal/versions/${v.id}/edit`),
    onError: (e) => toast.error(errorText(e)),
  });
  const saveSettings = useMutation({
    mutationFn: (body: Partial<DocumentRow>) => api<DocumentRow>(`/admin/legal/documents/${id}/`, { method: "PATCH", json: body }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "legal", "document", id], d);
      toast.success("Saved");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const withdraw = useMutation({
    mutationFn: (versionId: number) => api(`/admin/legal/versions/${versionId}/unpublish/`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Version withdrawn — the previous published version (if any) applies again");
      qc.invalidateQueries({ queryKey: ["admin", "legal"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  if (doc.isPending) return <Skeleton className="h-96" />;
  if (doc.isError) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />;
  const d = doc.data;
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const dirty = settings && JSON.stringify(settings) !== JSON.stringify({ audiences: d.audiences, actions: d.actions, is_mandatory: d.is_mandatory });

  return (
    <>
      <Link to="/admin/legal?tab=documents" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> All documents
      </Link>
      <PageHeader
        title={d.category_label}
        description={d.sector ? `Sector document for ${d.sector.name_en} — adds to the platform documents.` : "Platform-wide document."}
        actions={
          <>
            {d.current && (
              <Button asChild variant="outline">
                <a href={d.url} target="_blank" rel="noreferrer">
                  <Eye /> Public page
                </a>
              </Button>
            )}
            <Button onClick={() => (d.draft ? navigate(`/admin/legal/versions/${d.draft.id}/edit`) : newDraft.mutate())} disabled={newDraft.isPending}>
              {d.draft ? <Pencil /> : <FilePlus2 />}{" "}
              {d.draft ? `Edit draft v${d.draft.version}` : d.versions.length ? "Edit / rewrite (new version)" : "Write first version"}
            </Button>
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle>Versions</CardTitle>
            {compare.length === 2 && (
              <Button size="sm" variant="outline" onClick={() => navigate(`/admin/legal/versions/${compare[0]}/compare/${compare[1]}`)}>
                <GitCompare /> Compare selected
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {d.versions.length === 0 ? (
              <EmptyState icon={<FileText />} title="No versions yet">
                Nothing is shown or required until a version is published.
              </EmptyState>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th className="w-8">
                      <span className="sr-only">Compare</span>
                    </th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Effective</th>
                    <th>Published by</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {d.versions.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select v${v.version} to compare`}
                          className="size-4 accent-[var(--primary)]"
                          checked={compare.includes(v.id)}
                          onChange={() => setCompare((c) => (c.includes(v.id) ? c.filter((x) => x !== v.id) : [...c, v.id].slice(-2)))}
                        />
                      </td>
                      <td>
                        <span className="font-semibold">v{v.version}</span>
                        {v.change_summary && <span className="block text-xs text-muted-foreground">{v.change_summary}</span>}
                        <span className="block text-xs text-muted-foreground">
                          {v.has_en ? "EN" : ""}
                          {v.has_en && v.has_bn ? " · " : ""}
                          {v.has_bn ? "বাংলা" : ""}
                        </span>
                      </td>
                      <td>
                        <Badge tone={STATE_TONE[v.state]}>{v.state}</Badge>
                      </td>
                      <td className="text-xs">{v.status === "draft" ? "—" : legalDateTime(v.effective_at)}</td>
                      <td className="text-xs">{v.published_by ?? (v.status === "draft" ? `draft by ${v.created_by ?? "—"}` : "—")}</td>
                      <td className="whitespace-nowrap">
                        <Button size="sm" variant="ghost" onClick={() => setViewing(v.id)}>
                          <Eye /> View
                        </Button>
                        {(v.state === "current" || v.state === "scheduled") && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            disabled={withdraw.isPending}
                            onClick={() => {
                              if (window.confirm(`Withdraw v${v.version}? Its text and acceptance records are kept; the previous published version applies again.`)) withdraw.mutate(v.id);
                            }}
                          >
                            <Undo2 /> Withdraw
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Who must accept, and when</CardTitle>
            <CardDescription>Only published, mandatory versions are ever required.</CardDescription>
          </CardHeader>
          <CardContent>
            {settings && docs.data && (
              <div className="flex flex-col gap-4 text-sm">
                <fieldset className="flex flex-col gap-1.5">
                  <legend className="mb-1 font-semibold">Applies to</legend>
                  {docs.data.audiences.map((a) => (
                    <Checkbox key={a.value} label={a.label} checked={settings.audiences.includes(a.value)} onChange={() => setSettings({ ...settings, audiences: toggle(settings.audiences, a.value) })} />
                  ))}
                </fieldset>
                <fieldset className="flex flex-col gap-1.5">
                  <legend className="mb-1 font-semibold">Ask for agreement at</legend>
                  {docs.data.actions.map((a) => (
                    <Checkbox key={a.value} label={a.label} checked={settings.actions.includes(a.value)} onChange={() => setSettings({ ...settings, actions: toggle(settings.actions, a.value) })} />
                  ))}
                </fieldset>
                <Checkbox label="Mandatory" checked={settings.is_mandatory} onChange={() => setSettings({ ...settings, is_mandatory: !settings.is_mandatory })} />
                <Button disabled={!dirty || saveSettings.isPending} onClick={() => saveSettings.mutate(settings)}>
                  <Save /> Save settings
                </Button>
                <hr />
                <Button
                  variant="outline"
                  className={d.is_archived ? "" : "text-destructive"}
                  onClick={() => {
                    if (d.is_archived || window.confirm("Retire this document? It stops being shown or required. Its versions and records are kept.")) {
                      saveSettings.mutate({ is_archived: !d.is_archived });
                    }
                  }}
                >
                  {d.is_archived ? "Restore document" : "Retire document"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      {viewing !== null && <VersionPreviewDialog id={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}

function VersionPreviewDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const v = useQuery({ queryKey: ["admin", "legal", "version", id], queryFn: () => api<VersionDetail>(`/admin/legal/versions/${id}/`) });
  const [lang, setLang] = useState<Lang>("bn");
  return (
    <Dialog open onClose={onClose} wide title={v.data ? `${lang === "bn" ? v.data.title_bn || v.data.title_en : v.data.title_en} — v${v.data.version}` : "Version"}>
      {v.isPending && <Skeleton className="h-64" />}
      {v.data && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              <Badge tone={STATE_TONE[v.data.state]}>{v.data.state}</Badge> · {v.data.acceptances.toLocaleString()} acceptances
            </span>
            <LangToggle lang={lang} onChange={setLang} />
          </div>
          {(lang === "bn" ? v.data.body_bn : v.data.body_en).trim() ? (
            <LegalHtml html={lang === "bn" ? v.data.body_bn : v.data.body_en} lang={lang} className="text-sm" />
          ) : (
            <p className="text-sm text-muted-foreground">No {lang === "bn" ? "Bengali" : "English"} text in this version.</p>
          )}
        </div>
      )}
    </Dialog>
  );
}

// ------------------------------------------------------------------ editor
/** "YYYY-MM-DDTHH:mm" typed in Bangladesh time → ISO with +06:00. */
const dhakaLocalToIso = (v: string) => (v ? `${v}:00+06:00` : null);

export function AdminLegalEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const docs = useDocuments();
  const v = useQuery({ queryKey: ["admin", "legal", "version", Number(id)], queryFn: () => api<VersionDetail>(`/admin/legal/versions/${id}/`) });
  const [form, setForm] = useState<{ title_en: string; title_bn: string; body_en: string; body_bn: string; change_summary: string } | null>(null);
  const [lang, setLang] = useState<Lang>("bn");
  const [preview, setPreview] = useState(false);
  const [publishing, setPublishing] = useState(false);
  useEffect(() => {
    if (v.data && !form) {
      setForm({ title_en: v.data.title_en, title_bn: v.data.title_bn, body_en: v.data.body_en, body_bn: v.data.body_bn, change_summary: v.data.change_summary });
    }
  }, [v.data, form]);

  const save = useMutation({
    mutationFn: () => api<VersionDetail>(`/admin/legal/versions/${id}/`, { method: "PUT", json: form }),
    onSuccess: (d) => {
      qc.setQueryData(["admin", "legal", "version", Number(id)], d);
      // Show exactly what the server kept after cleaning.
      setForm({ title_en: d.title_en, title_bn: d.title_bn, body_en: d.body_en, body_bn: d.body_bn, change_summary: d.change_summary });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  // Replace the whole draft (both languages) with TurfBari's standard wording; saved only on "Save draft".
  const rewrite = useMutation({
    mutationFn: () =>
      api<{ title_en: string; title_bn: string; body_en: string; body_bn: string }>(`/admin/legal/documents/${v.data?.document.id}/standard-text/`),
    onSuccess: (t) => {
      setForm((f) => f && { ...f, ...t });
      toast.success("Standard text loaded — edit it, then Save draft");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const discard = useMutation({
    mutationFn: () => api(`/admin/legal/versions/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Draft discarded");
      qc.invalidateQueries({ queryKey: ["admin", "legal"] });
      navigate(`/admin/legal/documents/${v.data?.document.id}`);
    },
  });

  if (v.isPending || !form) return <Skeleton className="h-96" />;
  if (v.isError) return <ErrorState error={v.error} onRetry={() => v.refetch()} />;
  const d = v.data;
  if (d.status !== "draft") {
    return (
      <EmptyState title="This version is published and can't be edited">
        <Link to={`/admin/legal/documents/${d.document.id}`} className="text-primary hover:underline">
          Back to the document
        </Link>{" "}
        to start a new version.
      </EmptyState>
    );
  }
  const dirty = form.title_en !== d.title_en || form.title_bn !== d.title_bn || form.body_en !== d.body_en || form.body_bn !== d.body_bn || form.change_summary !== d.change_summary;
  const saveFirst = async () => {
    if (dirty) await save.mutateAsync();
  };

  return (
    <>
      <Link to={`/admin/legal/documents/${d.document.id}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> {d.document.category_label}
        {d.document.sector && ` · ${d.document.sector.name_en}`}
      </Link>
      <PageHeader
        title={`Draft v${d.version}`}
        description="Drafts are private: customers and businesses keep seeing the current published version until you publish."
        actions={
          <>
            <Button variant="ghost" className="text-destructive" onClick={() => window.confirm("Discard this draft?") && discard.mutate()}>
              <Trash2 /> Discard
            </Button>
            <Button
              variant="outline"
              disabled={rewrite.isPending}
              onClick={() =>
                window.confirm("Replace the text of this draft (English and Bengali) with TurfBari's standard wording? Unsaved edits are lost.") &&
                rewrite.mutate()
              }
            >
              {rewrite.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Rewrite with standard text
            </Button>
            <Button variant="outline" disabled={save.isPending} onClick={async () => (await saveFirst(), setPreview(true))}>
              <Eye /> Preview
            </Button>
            <Button variant="outline" disabled={!dirty || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => toast.success("Draft saved") })}>
              {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save draft
            </Button>
            <Button disabled={save.isPending} onClick={async () => (await saveFirst(), setPublishing(true))}>
              <Send /> Publish…
            </Button>
          </>
        }
      />
      <LegalReviewNotice />
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Title (English)">{(fid) => <Input id={fid} required value={form.title_en} onChange={(e) => setForm({ ...form, title_en: e.target.value })} />}</FormField>
            <FormField label="Title (Bengali)">{(fid) => <Input id={fid} lang="bn" value={form.title_bn} onChange={(e) => setForm({ ...form, title_bn: e.target.value })} />}</FormField>
          </div>
          <FormField label="What changed in this version" hint="Shown in the version history and to people asked to accept again.">
            {(fid) => <Input id={fid} maxLength={300} value={form.change_summary} onChange={(e) => setForm({ ...form, change_summary: e.target.value })} />}
          </FormField>
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold">Document text</p>
            <LangToggle lang={lang} onChange={setLang} />
          </div>
          {lang === "bn" ? (
            <RichTextEditor key="bn" lang="bn" label="Bengali text" value={form.body_bn} onChange={(html) => setForm((f) => f && { ...f, body_bn: html })} />
          ) : (
            <RichTextEditor key="en" lang="en" label="English text" value={form.body_en} onChange={(html) => setForm((f) => f && { ...f, body_en: html })} />
          )}
          <p className="text-xs text-muted-foreground">
            Allowed: headings, paragraphs, lists, bold/italic/underline, links (web, email, phone), quotes and tables. Anything else (scripts, styles,
            images, embeds) is removed when you save.
          </p>
        </CardContent>
      </Card>
      {preview && (
        <Dialog open onClose={() => setPreview(false)} wide title={`Preview — ${lang === "bn" ? form.title_bn || form.title_en : form.title_en}`} description="Exactly as it will appear after publishing (cleaned by the server).">
          <div className="mb-3 flex justify-end">
            <LangToggle lang={lang} onChange={setLang} />
          </div>
          {(lang === "bn" ? d.body_bn : d.body_en).trim() ? (
            <LegalHtml html={lang === "bn" ? d.body_bn : d.body_en} lang={lang} className="text-sm" />
          ) : (
            <p className="text-sm text-muted-foreground">No {lang === "bn" ? "Bengali" : "English"} text yet.</p>
          )}
        </Dialog>
      )}
      {publishing && docs.data && (
        <PublishDialog version={d} choices={docs.data.reacceptance} sectors={docs.data.sectors} onClose={() => setPublishing(false)} />
      )}
    </>
  );
}

function PublishDialog({ version, choices, sectors, onClose }: { version: VersionDetail; choices: Choice[]; sectors: Sector[]; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [when, setWhen] = useState<"now" | "later">("now");
  const [at, setAt] = useState("");
  const [scope, setScope] = useState(version.version === 1 ? "all" : "all");
  const [sector, setSector] = useState(version.document.sector?.slug ?? sectors[0]?.slug ?? "");
  const publish = useMutation({
    mutationFn: () =>
      api<VersionDetail>(`/admin/legal/versions/${version.id}/publish/`, {
        method: "POST",
        json: {
          reacceptance: scope,
          reaccept_sector: scope === "sector" ? sector : null,
          effective_at: when === "later" ? dhakaLocalToIso(at) : null,
          change_summary: version.change_summary,
        },
      }),
    onSuccess: (d) => {
      toast.success(when === "later" ? `v${d.version} scheduled` : `v${d.version} published`);
      qc.invalidateQueries({ queryKey: ["admin", "legal"] });
      navigate(`/admin/legal/documents/${d.document.id}`);
    },
  });
  const fields = publish.error instanceof ApiError ? publish.error.fields : null;
  const missing = [!version.has_en && "English", !version.has_bn && "Bengali"].filter(Boolean);
  return (
    <Dialog open onClose={onClose} title={`Publish v${version.version}`} description="Published versions are permanent: they can be withdrawn but never edited.">
      <div className="flex flex-col gap-4 text-sm">
        {missing.length === 1 && (
          <p className="rounded-md bg-amber-100 px-3 py-2 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200">
            There is no {missing[0]} text. Readers choosing {missing[0]} will see the other language with a note.
          </p>
        )}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 font-semibold">Takes effect</legend>
          <label className="flex items-center gap-2">
            <input type="radio" name="when" checked={when === "now"} onChange={() => setWhen("now")} className="accent-[var(--primary)]" /> Immediately
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="when" checked={when === "later"} onChange={() => setWhen("later")} className="accent-[var(--primary)]" /> On a date (Bangladesh time)
          </label>
          {when === "later" && (
            <Input type="datetime-local" aria-label="Effective date and time (Bangladesh time)" required value={at} onChange={(e) => setAt(e.target.value)} />
          )}
          {fields?.effective_at && <p className="text-destructive">{fields.effective_at[0]}</p>}
        </fieldset>
        <FormField label="Who must accept this version again">
          {(id) => (
            <Select id={id} value={scope} onChange={(e) => setScope(e.target.value)}>
              {choices.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        {scope === "sector" && (
          <FormField label="Sector that must accept again">
            {(id) => (
              <Select id={id} value={sector} onChange={(e) => setSector(e.target.value)}>
                {sectors.map((s) => (
                  <option key={s.slug} value={s.slug}>
                    {s.name_en}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
        )}
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <CalendarClock className="mt-0.5 size-4 shrink-0" />
          Customers always tick the current versions at every booking. Re-acceptance decides who is stopped at sign-in or at their next plan order / SMS recharge.
          People who never accepted this document always have to accept it.
        </p>
        {publish.error && <p className="text-destructive">{fields?.body?.[0] ?? fields?.status?.[0] ?? fields?.title_en?.[0] ?? errorText(publish.error)}</p>}
        <Button disabled={publish.isPending || (when === "later" && !at)} onClick={() => publish.mutate()}>
          {publish.isPending ? <Loader2 className="animate-spin" /> : <Send />} {when === "later" ? "Schedule" : "Publish now"}
        </Button>
      </div>
    </Dialog>
  );
}

// ------------------------------------------------------------------ compare
export function AdminLegalComparePage() {
  const { a = "", b = "" } = useParams();
  const [lang, setLang] = useState<Lang>("bn");
  const diff = useQuery({
    queryKey: ["admin", "legal", "compare", a, b, lang],
    queryFn: () =>
      api<{ from: { version: number; title: string }; to: { version: number; title: string }; rows: { type: "same" | "added" | "removed"; text: string }[]; changes: number }>(
        `/admin/legal/versions/${a}/compare/${b}/?lang=${lang}`,
      ),
  });
  return (
    <>
      <button type="button" onClick={() => window.history.back()} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back
      </button>
      <PageHeader
        title={diff.data ? `v${diff.data.from.version} → v${diff.data.to.version}` : "Compare versions"}
        description={diff.data ? `${diff.data.to.title} · ${diff.data.changes} changed line${diff.data.changes === 1 ? "" : "s"}` : undefined}
        actions={<LangToggle lang={lang} onChange={setLang} />}
      />
      {diff.isPending && <Skeleton className="h-96" />}
      {diff.isError && <ErrorState error={diff.error} onRetry={() => diff.refetch()} />}
      {diff.data && (
        <Card>
          <CardContent className="pt-6">
            <ol className="flex flex-col gap-0.5 text-sm" lang={lang}>
              {diff.data.rows.map((r, i) => (
                <li
                  // biome-ignore lint/suspicious/noArrayIndexKey: diff rows have no identity
                  key={i}
                  className={cn(
                    "rounded px-2 py-1",
                    r.type === "added" && "bg-emerald-100 text-emerald-900 dark:bg-emerald-500/15 dark:text-emerald-100",
                    r.type === "removed" && "bg-red-100 text-red-900 line-through dark:bg-red-500/15 dark:text-red-100",
                  )}
                >
                  <span className="mr-2 inline-block w-3 font-mono text-xs text-muted-foreground">{r.type === "added" ? "+" : r.type === "removed" ? "−" : ""}</span>
                  {r.text}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </>
  );
}
