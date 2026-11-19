import {
  BarChart3,
  Building2,
  CalendarClock,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  CreditCard,
  Clock,
  Grid2x2,
  HeartPulse,
  History,
  Inbox,
  LayoutDashboard,
  Palette,
  MessageSquareText,
  Receipt,
  Settings,
  ShieldCheck,
  Tags,
  TicketPercent,
  UserCog,
  Users,
  Wrench,
} from "lucide-react";
import { type ComponentType, lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, useParams } from "react-router";
import { AppShell, type NavItem } from "@/components/layout/AppShell";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { RequireRole } from "@/features/auth/auth";
import { LoginPage } from "@/features/auth/LoginPage";
import { ForgotPasswordPage, SetPasswordPage } from "@/features/auth/PasswordPages";
import { BookingStatusPage } from "@/features/public/BookingStatusPage";
import { HomePage } from "@/features/public/HomePage";
import { RegisterTurfPage } from "@/features/public/RegisterTurfPage";
import { TurfDetailPage } from "@/features/public/TurfDetailPage";
import { NotFoundPage } from "@/features/system/NotFoundPage";
import { SystemStatusPage } from "@/features/system/SystemStatusPage";

/**
 * Signed-in screens load on demand, so the public pages (what players open) download much less.
 * `page(() => import(...), "Name")` lazy-loads one named export.
 */
function page<M extends Record<string, unknown>>(load: () => Promise<M>, name: keyof M & string) {
  const Component = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })));
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center" role="status" aria-label="Loading">
          <span className="size-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
        </div>
      }
    >
      <Component />
    </Suspense>
  );
}

/** /turf/<slug> (singular) is accepted as a short form of /turfs/<slug>. */
function TurfAlias() {
  const { slug = "" } = useParams();
  return <Navigate to={`/turfs/${slug}`} replace />;
}

const adminPages = () => import("@/features/admin/AdminPages");
const billingPages = () => import("@/features/admin/BillingPages");
const activityPages = () => import("@/features/audit/ActivityLog");
const accountPage = () => import("@/features/auth/AccountPage");
const operationsPages = () => import("@/features/workspace/OperationsPages");
const setupPages = () => import("@/features/workspace/SetupPages");
const platformPages = () => import("@/features/admin/PlatformPages");
const smsPages = () => import("@/features/sms/SmsPages");

const ADMIN_NAV: NavItem[] = [
  { to: "/admin", label: "Overview", icon: <LayoutDashboard />, end: true },
  { to: "/admin/applications", label: "Applications", icon: <Inbox />, badge: "pending_applications" },
  { to: "/admin/turfs", label: "Turfs", icon: <Building2 /> },
  { to: "/admin/billing", label: "Plans & payments", icon: <CreditCard />, badge: "pending_payments" },
  { to: "/admin/subscriptions", label: "Subscriptions", icon: <CalendarClock /> },
  { to: "/admin/promo-codes", label: "Promo codes", icon: <TicketPercent /> },
  { to: "/admin/accounts", label: "Accounts", icon: <UserCog /> },
  { to: "/admin/sms", label: "SMS", icon: <MessageSquareText /> },
  { to: "/admin/health", label: "Health", icon: <HeartPulse /> },
  { to: "/admin/audit", label: "Audit log", icon: <History /> },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: "/workspace", label: "Dashboard", icon: <LayoutDashboard />, end: true },
  { to: "/workspace/book", label: "Book a slot", icon: <CalendarPlus /> },
  { to: "/workspace/payments", label: "Payment verification", icon: <ShieldCheck />, badge: "pending_payments_to_verify" },
  { to: "/workspace/bookings", label: "Bookings", icon: <CalendarDays />, badge: "pending_bookings" },
  { to: "/workspace/customers", label: "Customers", icon: <Users /> },
  { to: "/workspace/maintenance", label: "Maintenance", icon: <Wrench /> },
  { to: "/workspace/fields", label: "Fields", icon: <Grid2x2 /> },
  { to: "/workspace/hours", label: "Opening hours", icon: <Clock /> },
  { to: "/workspace/slots", label: "Slot schedule", icon: <CalendarRange /> },
  { to: "/workspace/pricing", label: "Pricing", icon: <Tags /> },
  { to: "/workspace/expenses", label: "Expenses", icon: <Receipt />, ownerOnly: true },
  { to: "/workspace/reports", label: "Reports", icon: <BarChart3 />, ownerOnly: true },
  { to: "/workspace/team", label: "Team", icon: <UserCog />, ownerOnly: true },
  { to: "/workspace/activity", label: "Activity", icon: <History />, ownerOnly: true },
  { to: "/workspace/sms", label: "SMS", icon: <MessageSquareText />, permission: "view_sms" },
  { to: "/workspace/subscription", label: "Subscription", icon: <CreditCard /> },
  { to: "/workspace/design", label: "Page design", icon: <Palette /> },
  { to: "/workspace/settings", label: "Settings", icon: <Settings /> },
];

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      // The public turf directory was retired: old links land on the home page.
      { path: "/explore", element: <Navigate to="/" replace /> },
      { path: "/turf/:slug", element: <TurfAlias /> },
      { path: "/turfs/:slug", element: <TurfDetailPage /> },
      { path: "/register-turf", element: <RegisterTurfPage /> },
      { path: "/booking-status", element: <BookingStatusPage /> },
      { path: "/status", element: <SystemStatusPage /> },
    ],
  },
  { path: "/login", element: <LoginPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/set-password", element: <SetPasswordPage /> },
  {
    path: "/admin",
    element: (
      <RequireRole role="admin">
        <AppShell nav={ADMIN_NAV} area="admin" />
      </RequireRole>
    ),
    children: [
      { index: true, element: page(adminPages, "AdminDashboardPage") },
      { path: "applications", element: page(adminPages, "AdminApplicationsPage") },
      { path: "turfs", element: page(adminPages, "AdminTurfsPage") },
      { path: "billing", element: page(billingPages, "AdminBillingPage") },
      { path: "promo-codes", element: page(() => import("@/features/admin/PromoCodesPage"), "AdminPromoCodesPage") },
      { path: "accounts", element: page(() => import("@/features/admin/AccountsPage"), "AdminAccountsPage") },
      { path: "sms", element: page(smsPages, "AdminSmsPage") },
      { path: "subscriptions", element: page(platformPages, "AdminSubscriptionsPage") },
      { path: "health", element: page(platformPages, "AdminHealthPage") },
      { path: "audit", element: page(activityPages, "AdminAuditPage") },
      { path: "account", element: page(accountPage, "AccountPage") },
    ],
  },
  {
    path: "/workspace",
    element: (
      <RequireRole role="workspace">
        <AppShell nav={WORKSPACE_NAV} area="workspace" />
      </RequireRole>
    ),
    children: [
      { index: true, element: page(() => import("@/features/workspace/DashboardPage"), "DashboardPage") },
      { path: "book", element: page(() => import("@/features/workspace/SlotBoardPage"), "SlotBoardPage") },
      { path: "bookings", element: page(() => import("@/features/workspace/BookingsPage"), "BookingsPage") },
      { path: "payments", element: page(() => import("@/features/workspace/PaymentVerificationPage"), "PaymentVerificationPage") },
      { path: "customers", element: page(operationsPages, "CustomersPage") },
      { path: "maintenance", element: page(operationsPages, "MaintenancePage") },
      { path: "fields", element: page(setupPages, "FieldsPage") },
      { path: "hours", element: page(setupPages, "HoursPage") },
      { path: "slots", element: page(() => import("@/features/workspace/SchedulePages"), "SlotSchedulePage") },
      { path: "pricing", element: page(setupPages, "PricingPage") },
      { path: "expenses", element: page(operationsPages, "ExpensesPage") },
      { path: "reports", element: page(operationsPages, "ReportsPage") },
      { path: "team", element: page(setupPages, "ManagersPage") },
      { path: "activity", element: page(activityPages, "WorkspaceActivityPage") },
      { path: "settings", element: page(setupPages, "SettingsPage") },
      { path: "design", element: page(() => import("@/features/workspace/DesignPage"), "DesignPage") },
      { path: "sms", element: page(smsPages, "WorkspaceSmsPage") },
      { path: "subscription", element: page(() => import("@/features/workspace/SubscriptionPage"), "SubscriptionPage") },
      { path: "account", element: page(accountPage, "AccountPage") },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
