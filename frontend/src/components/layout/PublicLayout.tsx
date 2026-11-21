import { LayoutDashboard, Menu, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { useMe } from "@/features/auth/auth";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useLanguage } from "@/lib/i18n";

const NAV = [
  { to: "/#contact", label: "Contact" },
  { to: "/booking-status", label: "Check booking" },
  { to: "/register-turf", label: "Register your turf" },
];

export function PublicLayout() {
  const me = useMe();
  const [open, setOpen] = useState(false);
  const signedIn = me.data?.authenticated;
  const { t } = useLanguage();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-lg">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
          <Link to="/" aria-label="TurfBari home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition hover:text-foreground",
                    isActive && "text-foreground",
                  )
                }
              >
                {t(item.label)}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <LanguageSwitcher compact />
            {signedIn ? (
              <Button asChild size="sm">
                <Link to={me.data?.home ?? "/"}>
                  <LayoutDashboard /> {t("Dashboard")}
                </Link>
              </Button>
            ) : (
              <Button asChild size="sm" variant="outline">
                <Link to="/login">{t("Sign in")}</Link>
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label={t(open ? "Close menu" : "Open menu")}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X /> : <Menu />}
            </Button>
          </div>
        </div>
        {open && (
          <nav className="border-t px-4 py-2 md:hidden" aria-label="Mobile">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                className="block rounded-md px-2 py-3 text-sm font-medium"
              >
                {t(item.label)}
              </Link>
            ))}
          </nav>
        )}
      </header>
      <div className="flex-1">
        <Outlet />
      </div>
      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <Logo className="[&_span]:text-lg" />
          <p>Turf management and booking pages for football turfs in Bangladesh.</p>
          <p>
            <Link to="/legal/terms" className="hover:text-foreground hover:underline">
              Terms
            </Link>{" "}
            ·{" "}
            <Link to="/legal/privacy" className="hover:text-foreground hover:underline">
              Privacy
            </Link>{" "}
            ·{" "}
            <Link to="/legal" className="hover:text-foreground hover:underline">
              All policies
            </Link>{" "}
            · © {new Date().getFullYear()} TurfBari
          </p>
        </div>
      </footer>
    </div>
  );
}
