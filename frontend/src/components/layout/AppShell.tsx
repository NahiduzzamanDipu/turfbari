import { ExternalLink, KeyRound, LogOut, Menu, X } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { useLogout, useMe, useSwitchTurf } from "@/features/auth/auth";
import { type LiveState, useLiveSync } from "@/lib/live";
import type { ManagerPermissions } from "@/lib/types";
import { SubscriptionBanner } from "@/features/workspace/SubscriptionBanner";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useLanguage } from "@/lib/i18n";

export interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  end?: boolean;
  ownerOnly?: boolean;
  /** Managers see it only with this permission (owners always do). */
  permission?: keyof ManagerPermissions;
  /** Live count shown as a badge (e.g. booking requests waiting). */
  badge?: keyof Pick<
    LiveState,
    | "pending_requests"
    | "pending_payments_to_verify"
    | "pending_bookings"
    | "pending_applications"
    | "pending_payments"
    | "pending_recharges"
    | "pending_registration_payments"
  >;
}

/** Sidebar shell shared by the Super Admin console and the turf workspace. */
export function AppShell({ nav, area }: { nav: NavItem[]; area: "admin" | "workspace" }) {
  const me = useMe();
  const logout = useLogout();
  const switchTurf = useSwitchTurf();
  const [open, setOpen] = useState(false);
  const live = useLiveSync(area);
  const data = me.data;
  const { t } = useLanguage();
  const active = data?.memberships.find((m) => m.turf_id === data.active_turf_id);
  const isOwner = active?.role === "owner";
  const items = nav.filter(
    (item) =>
      area === "admin" ||
      isOwner ||
      (!item.ownerOnly && (!item.permission || Boolean(active?.permissions?.[item.permission]))),
  );

  const sidebar = (
    <div className="flex h-full flex-col gap-4 p-4">
      <Link to="/" className="px-2">
        <Logo />
      </Link>
      {area === "workspace" && data && data.memberships.length > 0 && (
        <div className="rounded-lg bg-secondary/70 p-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Workspace</p>
          {data.memberships.length > 1 ? (
            <select
              aria-label="Switch turf"
              className="mt-1 w-full bg-transparent text-sm font-semibold outline-none"
              value={data.active_turf_id ?? ""}
              onChange={(e) => switchTurf.mutate(e.target.value)}
            >
              {data.memberships.map((m) => (
                <option key={m.turf_id} value={m.turf_id}>
                  {m.turf_name}
                </option>
              ))}
            </select>
          ) : (
            <p className="mt-0.5 truncate text-sm font-semibold">{active?.turf_name}</p>
          )}
          <p className="text-xs capitalize text-muted-foreground">{active?.role}</p>
        </div>
      )}
      {area === "admin" && (
        <div className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold uppercase tracking-wide text-primary-foreground">
          Super Admin
        </div>
      )}
      <nav className="flex flex-1 flex-col gap-0.5" aria-label="Sections">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground [&_svg]:size-4",
                isActive && "bg-secondary text-foreground",
              )
            }
          >
            {item.icon}
            {t(item.label)}
            {item.badge && (live?.[item.badge] ?? 0) > 0 && (
              <span
                className="ml-auto rounded-full bg-amber-500 px-2 py-0.5 text-xs font-semibold text-white"
                aria-label={`${live?.[item.badge]} waiting`}
              >
                {live?.[item.badge]}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      {area === "workspace" && active && (
        <a
          href={`/turfs/${active.turf_slug}`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 px-3 text-xs text-muted-foreground hover:text-foreground"
        >
          <ExternalLink className="size-3.5" /> View public page
        </a>
      )}
      <div className="border-t pt-3">
        <div className="mb-2 px-2"><LanguageSwitcher /></div>
        <p className="truncate px-3 text-sm font-medium">{data?.user?.full_name || data?.user?.email}</p>
        <p className="truncate px-3 text-xs text-muted-foreground">{data?.user?.email}</p>
        <NavLink
          to={`/${area}/account`}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            cn(
              "mt-2 flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground [&_svg]:size-4",
              isActive && "bg-secondary text-foreground",
            )
          }
        >
          <KeyRound /> {t("My account & password")}
        </NavLink>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          <LogOut /> {t("Sign out")}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-dvh border-r bg-card/50 lg:block">{sidebar}</aside>
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/85 px-4 backdrop-blur lg:hidden">
        <Logo className="[&_span]:text-xl" />
        <LanguageSwitcher compact />
        <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}>
          <Menu />
        </Button>
      </header>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] overflow-y-auto bg-background shadow-xl">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-2"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
            >
              <X />
            </Button>
            {sidebar}
          </aside>
        </div>
      )}
      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        {area === "workspace" && <SubscriptionBanner />}
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight sm:text-4xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center justify-between text-sm text-muted-foreground [&_svg]:size-4">
        <span>{label}</span>
        {icon}
      </div>
      <p className="tabular mt-2 text-2xl font-bold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
