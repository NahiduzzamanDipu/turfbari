import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { History, Search } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, type BadgeTone, EmptyState, ErrorState, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { Paginated } from "@/lib/types";

interface AuditRow {
  id: string;
  created_at: string;
  actor_label: string;
  category: string;
  category_label: string;
  action: string;
  summary: string;
  turf_name?: string;
  ip?: string | null;
}

const CATEGORIES: [string, string, BadgeTone][] = [
  ["booking", "Bookings", "blue"],
  ["payment", "Payments", "green"],
  ["customer", "Customers", "neutral"],
  ["setup", "Fields, hours & pricing", "neutral"],
  ["settings", "Settings & pictures", "neutral"],
  ["team", "Team", "lime"],
  ["expense", "Expenses", "amber"],
  ["subscription", "Subscription", "amber"],
  ["account", "Sign-in & account", "neutral"],
  ["platform", "Platform admin", "red"],
];
const TONE = Object.fromEntries(CATEGORIES.map(([k, , t]) => [k, t])) as Record<string, BadgeTone>;
const PAGE_SIZE = 25;

/** Activity log for the owner workspace (`scope="workspace"`) or the Super Admin (`scope="admin"`). */
export function ActivityLog({ scope }: { scope: "workspace" | "admin" }) {
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (category) params.set("category", category);
  if (search) params.set("q", search);
  const url = scope === "admin" ? "/admin/audit/" : "/workspace/activity/";
  const log = useQuery({
    queryKey: [scope === "admin" ? "admin" : "ws", "audit", params.toString()],
    queryFn: () => api<Paginated<AuditRow>>(`${url}?${params}`),
    placeholderData: keepPreviousData,
  });
  const pages = log.data ? Math.max(1, Math.ceil(log.data.count / PAGE_SIZE)) : 1;
  const categories = scope === "admin" ? CATEGORIES : CATEGORIES.filter(([k]) => k !== "platform");

  return (
    <>
      <PageHeader
        title={scope === "admin" ? "Audit log" : "Activity"}
        description={
          scope === "admin"
            ? "Every important action across the platform: who did it, when and from where."
            : "Who did what on your turf: bookings, payments, settings, team and sign-ins."
        }
      />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <form
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q.trim());
            setPage(1);
          }}
        >
          <Input aria-label="Search activity" placeholder="Search by person, booking, team…" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button type="submit" variant="outline">
            <Search /> Search
          </Button>
        </form>
        <Select
          aria-label="Category"
          className="sm:max-w-56"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Everything</option>
          {categories.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {log.isPending && <Skeleton className="h-60" />}
          {log.isError && <ErrorState error={log.error} onRetry={() => log.refetch()} />}
          {log.data?.results.length === 0 && (
            <EmptyState icon={<History />} title="Nothing recorded yet">
              Actions appear here as soon as they happen.
            </EmptyState>
          )}
          {log.data && log.data.results.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  {scope === "admin" && <th>Turf</th>}
                  <th>What happened</th>
                </tr>
              </thead>
              <tbody>
                {log.data.results.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap text-sm text-muted-foreground">{fmtDateTime(row.created_at)}</td>
                    <td className="text-sm">
                      {row.actor_label || <span className="text-muted-foreground">{row.action === "booking.requested" ? "Player (online)" : "System"}</span>}
                      {scope === "admin" && row.ip && <span className="block font-mono text-[11px] text-muted-foreground">{row.ip}</span>}
                    </td>
                    {scope === "admin" && <td className="text-sm">{row.turf_name || "—"}</td>}
                    <td>
                      <Badge tone={TONE[row.category] ?? "neutral"} className="mb-1">
                        {row.category_label}
                      </Badge>
                      <p className="text-sm">{row.summary}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {pages > 1 && (
            <nav className="mt-4 flex items-center justify-center gap-3" aria-label="Pagination">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Newer
              </Button>
              <span className="text-sm">
                Page {page} of {pages}
              </span>
              <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Older
              </Button>
            </nav>
          )}
        </CardContent>
      </Card>
    </>
  );
}

export const WorkspaceActivityPage = () => <ActivityLog scope="workspace" />;
export const AdminAuditPage = () => <ActivityLog scope="admin" />;
