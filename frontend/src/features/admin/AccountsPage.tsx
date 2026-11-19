import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Copy, KeyRound, Lock, Plus, ShieldOff, UserCheck, UserX, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, Dialog, EmptyState, ErrorState, FormField, Input, Select, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";
import type { AdminTurf, Paginated } from "@/lib/types";

interface AccountMembership {
  id: string;
  turf_id: string;
  turf_name: string;
  turf_status: string;
  role: "owner" | "manager";
  is_active: boolean;
}

interface Account {
  id: string;
  email: string;
  username: string;
  full_name: string;
  phone: string;
  is_active: boolean;
  is_platform_admin: boolean;
  must_change_password: boolean;
  temp_password_expires_at: string | null;
  last_login: string | null;
  date_joined: string;
  two_factor: boolean;
  locked: boolean;
  memberships: AccountMembership[];
  security_events?: { at: string; action: string; summary: string; ip: string | null; by: string }[];
  temporary_password?: string;
  sessions_ended?: number;
}

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "Never";

function StatusBadges({ a }: { a: Account }) {
  return (
    <div className="flex flex-wrap gap-1">
      {a.is_platform_admin && <Badge tone="lime">Platform admin</Badge>}
      {!a.is_active && <Badge tone="red">Deactivated</Badge>}
      {a.locked && <Badge tone="amber">Locked out</Badge>}
      {a.must_change_password && <Badge tone="blue">Temporary password</Badge>}
      {a.two_factor && <Badge tone="green">2-step</Badge>}
      {a.is_active && !a.locked && !a.must_change_password && !a.is_platform_admin && <Badge tone="neutral">Active</Badge>}
    </div>
  );
}

function TempPassword({ value, email }: { value: string; email: string }) {
  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
      <p className="font-medium">Temporary password for {email}</p>
      <p className="text-muted-foreground">Shown only now. They must replace it at their next sign-in.</p>
      <div className="mt-2 flex items-center gap-2 rounded-md bg-background p-2">
        <code className="flex-1 font-mono text-base">{value}</code>
        <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(value).then(() => toast.success("Copied"))}>
          <Copy /> Copy
        </Button>
      </div>
    </div>
  );
}

export function AdminAccountsPage() {
  const [q, setQ] = useState("");
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: ["admin", "users", q, state, page],
    queryFn: () => api<Paginated<Account>>(`/admin/users/?${new URLSearchParams({ q, state, page: String(page) })}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Accounts"
        description="Find any owner or manager, fix sign-in problems and correct which turfs they belong to. Every action is audited."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> New account
          </Button>
        }
      />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input
          placeholder="Search email, phone, username, name or turf"
          aria-label="Search accounts"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <Select
          aria-label="Filter"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
          className="sm:max-w-56"
        >
          <option value="">All accounts</option>
          <option value="temporary">On a temporary password</option>
          <option value="inactive">Deactivated</option>
          <option value="admins">Platform admins</option>
        </Select>
      </div>
      <Card>
        <CardContent className="p-2 sm:p-4">
          {list.isPending && <Skeleton className="h-40" />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.results.length === 0 && <EmptyState icon={<Users />} title="No accounts match" />}
          {list.data && list.data.results.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Turfs</th>
                  <th>Status</th>
                  <th>Last sign-in</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((a) => (
                  <tr key={a.id} className="cursor-pointer hover:bg-secondary/60" onClick={() => setOpenId(a.id)}>
                    <td>
                      <button type="button" className="text-left font-medium hover:underline">
                        {a.full_name || a.email}
                      </button>
                      <span className="block text-xs text-muted-foreground">
                        {a.email}
                        {a.phone && ` · ${a.phone}`}
                      </span>
                    </td>
                    <td className="text-sm">
                      {a.memberships.filter((m) => m.is_active).map((m) => (
                        <span key={m.id} className="block">
                          {m.turf_name} <span className="text-muted-foreground">({m.role})</span>
                        </span>
                      ))}
                      {a.memberships.every((m) => !m.is_active) && <span className="text-muted-foreground">—</span>}
                    </td>
                    <td>
                      <StatusBadges a={a} />
                    </td>
                    <td className="text-sm text-muted-foreground">{when(a.last_login)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {list.data && list.data.count > 20 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-sm">
              <span className="text-muted-foreground">{list.data.count} accounts</span>
              <Button size="icon" variant="outline" aria-label="Previous page" disabled={!list.data.previous} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft />
              </Button>
              <span className="tabular">Page {page}</span>
              <Button size="icon" variant="outline" aria-label="Next page" disabled={!list.data.next} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      {openId && <AccountDialog id={openId} onClose={() => setOpenId(null)} />}
      {creating && <CreateAccountDialog onClose={() => setCreating(false)} onCreated={(id) => setOpenId(id)} />}
    </>
  );
}

function useTurfOptions() {
  return useQuery({
    queryKey: ["admin", "turfs", "options"],
    queryFn: () => api<Paginated<AdminTurf>>("/admin/turfs/?page_size=100"),
    staleTime: 60_000,
  });
}

const ACTIONS: { key: string; label: string; icon: React.ReactNode; confirm: string; show: (a: Account) => boolean }[] = [
  { key: "unlock", label: "Unlock sign-in", icon: <Lock />, confirm: "Clear the failed sign-in lockout?", show: (a) => a.locked },
  {
    key: "reset-password",
    label: "Issue temporary password",
    icon: <KeyRound />,
    confirm: "Issue a new temporary password? Their current password stops working and they're signed out everywhere.",
    show: () => true,
  },
  { key: "force-change", label: "Require password change", icon: <KeyRound />, confirm: "Make them choose a new password at their next request?", show: (a) => !a.must_change_password },
  { key: "end-sessions", label: "Sign out everywhere", icon: <UserX />, confirm: "End every signed-in session of this account?", show: () => true },
  { key: "disable-2fa", label: "Turn off 2-step sign-in", icon: <ShieldOff />, confirm: "Remove their authenticator app (if they lost the phone)?", show: (a) => a.two_factor },
  { key: "deactivate", label: "Deactivate", icon: <UserX />, confirm: "Deactivate this account? They can't sign in until reactivated.", show: (a) => a.is_active },
  { key: "activate", label: "Reactivate", icon: <UserCheck />, confirm: "Reactivate this account?", show: (a) => !a.is_active },
];

function AccountDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [temp, setTemp] = useState<string | null>(null);
  const [addTurf, setAddTurf] = useState("");
  const [addRole, setAddRole] = useState<"manager" | "owner">("manager");
  const account = useQuery({ queryKey: ["admin", "users", "detail", id], queryFn: () => api<Account>(`/admin/users/${id}/`) });
  const turfs = useTurfOptions();
  const done = (a: Account, message: string) => {
    qc.setQueryData(["admin", "users", "detail", id], a);
    qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    toast.success(message);
  };
  const act = useMutation({
    mutationFn: (key: string) => api<Account>(`/admin/users/${id}/${key}/`, { method: "POST" }),
    onSuccess: (a, key) => {
      if (a.temporary_password) setTemp(a.temporary_password);
      done(a, ACTIONS.find((x) => x.key === key)?.label + " — done");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const membership = useMutation({
    mutationFn: ({ mid, body }: { mid: string; body: Partial<AccountMembership> }) =>
      api<Account>(`/admin/memberships/${mid}/`, { method: "PATCH", json: body }),
    onSuccess: (a) => done(a, "Membership updated"),
    onError: (e) => toast.error(errorText(e)),
  });
  const add = useMutation({
    mutationFn: () => api<Account>(`/admin/users/${id}/memberships/`, { method: "POST", json: { turf: addTurf, role: addRole } }),
    onSuccess: (a) => {
      setAddTurf("");
      done(a, "Added to turf");
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const a = account.data;
  const editable = a && !a.is_platform_admin;

  return (
    <Dialog open onClose={onClose} title={a ? a.full_name || a.email : "Account"} description={a?.email} wide>
      {account.isPending && <Skeleton className="h-48" />}
      {account.isError && <ErrorState error={account.error} onRetry={() => account.refetch()} />}
      {a && (
        <div className="flex flex-col gap-5 text-sm">
          <StatusBadges a={a} />
          {temp && <TempPassword value={temp} email={a.email} />}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Phone</dt>
              <dd>{a.phone || "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Username</dt>
              <dd>{a.username || "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Joined</dt>
              <dd>{when(a.date_joined)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last sign-in</dt>
              <dd>{when(a.last_login)}</dd>
            </div>
            {a.must_change_password && a.temp_password_expires_at && (
              <div>
                <dt className="text-muted-foreground">Temporary password expires</dt>
                <dd>{when(a.temp_password_expires_at)}</dd>
              </div>
            )}
          </dl>

          {editable ? (
            <section>
              <h3 className="mb-2 font-semibold">Fix access</h3>
              <div className="flex flex-wrap gap-2">
                {ACTIONS.filter((x) => x.show(a)).map((x) => (
                  <Button
                    key={x.key}
                    size="sm"
                    variant={x.key === "deactivate" ? "destructive" : "outline"}
                    disabled={act.isPending}
                    onClick={() => window.confirm(x.confirm) && act.mutate(x.key)}
                  >
                    {x.icon} {x.label}
                  </Button>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Passwords are never shown or set directly — a temporary password works once until the user picks their own.
              </p>
            </section>
          ) : (
            <p className="rounded-md bg-secondary p-3 text-muted-foreground">
              Platform administrator accounts can't be changed here. Use the break-glass deploy setting if an admin is locked out.
            </p>
          )}

          <section>
            <h3 className="mb-2 font-semibold">Turfs and roles</h3>
            {a.memberships.length === 0 && <p className="text-muted-foreground">Not a member of any turf.</p>}
            {a.memberships.length > 0 && (
              <Table>
                <tbody>
                  {a.memberships.map((m) => (
                    <tr key={m.id} className={m.is_active ? "" : "opacity-60"}>
                      <td>
                        {m.turf_name}
                        {m.turf_status !== "active" && <span className="ml-1 text-xs text-muted-foreground">({m.turf_status})</span>}
                      </td>
                      <td>
                        <Select
                          aria-label={`Role at ${m.turf_name}`}
                          value={m.role}
                          disabled={!editable || membership.isPending}
                          onChange={(e) => membership.mutate({ mid: m.id, body: { role: e.target.value as AccountMembership["role"] } })}
                        >
                          <option value="owner">Owner</option>
                          <option value="manager">Manager</option>
                        </Select>
                      </td>
                      <td className="text-right">
                        {editable && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={membership.isPending}
                            onClick={() => membership.mutate({ mid: m.id, body: { is_active: !m.is_active } })}
                          >
                            {m.is_active ? "Remove" : "Restore"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            {editable && (
              <form
                className="mt-3 flex flex-col gap-2 sm:flex-row"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (addTurf) add.mutate();
                }}
              >
                <Select aria-label="Turf" value={addTurf} onChange={(e) => setAddTurf(e.target.value)}>
                  <option value="">Add to a turf…</option>
                  {turfs.data?.results.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
                <Select aria-label="Role" value={addRole} onChange={(e) => setAddRole(e.target.value as "manager" | "owner")} className="sm:max-w-36">
                  <option value="manager">Manager</option>
                  <option value="owner">Owner</option>
                </Select>
                <Button type="submit" size="sm" className="h-9" disabled={!addTurf || add.isPending}>
                  Add
                </Button>
              </form>
            )}
          </section>

          <section>
            <h3 className="mb-2 font-semibold">Recent sign-in &amp; security events</h3>
            {a.security_events?.length ? (
              <ul className="max-h-56 divide-y overflow-y-auto rounded-md border">
                {a.security_events.map((e, i) => (
                  <li key={i} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                    <span>
                      {e.summary}
                      {e.by && <span className="text-muted-foreground"> · by {e.by}</span>}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {when(e.at)}
                      {e.ip && ` · ${e.ip}`}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">No events yet.</p>
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}

function CreateAccountDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const turfs = useTurfOptions();
  const [form, setForm] = useState({ email: "", full_name: "", phone: "", turf: "", role: "manager" });
  const [result, setResult] = useState<Account | null>(null);
  const create = useMutation({
    mutationFn: () => api<Account>("/admin/users/", { method: "POST", json: form }),
    onSuccess: (a) => {
      setResult(a);
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
  const fields = create.error instanceof ApiError ? create.error.fields : null;
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Dialog open onClose={onClose} title="New account" description="Creates an owner or manager login with a one-time temporary password.">
      {result?.temporary_password ? (
        <div className="flex flex-col gap-3">
          <TempPassword value={result.temporary_password} email={result.email} />
          <Button
            onClick={() => {
              onClose();
              onCreated(result.id);
            }}
          >
            Done
          </Button>
        </div>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <FormField label="Full name" error={fields?.full_name}>
            {(id) => <Input id={id} required value={form.full_name} onChange={set("full_name")} />}
          </FormField>
          <FormField label="Email" error={fields?.email}>
            {(id) => <Input id={id} type="email" required value={form.email} onChange={set("email")} />}
          </FormField>
          <FormField label="Mobile (optional)" hint="Used for SMS password-reset codes" error={fields?.phone}>
            {(id) => <Input id={id} type="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={set("phone")} />}
          </FormField>
          <FormField label="Role" error={fields?.role}>
            {(id) => (
              <Select id={id} value={form.role} onChange={set("role")}>
                <option value="manager">Manager</option>
                <option value="owner">Owner</option>
              </Select>
            )}
          </FormField>
          <FormField label="Turf" className="sm:col-span-2" error={fields?.turf}>
            {(id) => (
              <Select id={id} required value={form.turf} onChange={set("turf")}>
                <option value="">Choose a turf</option>
                {turfs.data?.results.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          {create.error && !fields && <p className="text-sm text-destructive sm:col-span-2">{errorText(create.error)}</p>}
          <Button type="submit" disabled={create.isPending} className="sm:col-span-2">
            Create account
          </Button>
        </form>
      )}
    </Dialog>
  );
}
