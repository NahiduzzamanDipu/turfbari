import {
  BadgeCheck,
  BarChart3,
  Building2,
  CalendarClock,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  CreditCard,
  FileText,
  Clock,
  Grid2x2,
  HeartPulse,
  History,
  Inbox,
  Landmark,
  LayoutDashboard,
  Palette,
  PlugZap,
  MessageSquareText,
  Receipt,
  Repeat,
  Scale,
  Settings,
  ShieldCheck,
  Tags,
  TicketPercent,
  UserCog,
  Users,
  Wallet,
  Wrench,
} from "lucide-react";
import { type ComponentType, lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, useParams } from "react-router";
import { AppShell, type NavItem } from "@/components/layout/AppShell";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { RequireRole } from "@/features/auth/auth";
import { TurfDetailPage } from "@/features/public/TurfDetailPage";
import { NotFoundPage } from "@/features/system/NotFoundPage";

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

const passwordPages = () => import("@/features/auth/PasswordPages");
const adminPages = () => import("@/features/admin/AdminPages");
const billingPages = () => import("@/features/admin/BillingPages");
const activityPages = () => import("@/features/audit/ActivityLog");
const accountPage = () => import("@/features/auth/AccountPage");
const operationsPages = () => import("@/features/workspace/OperationsPages");
const setupPages = () => import("@/features/workspace/SetupPages");
const walletAdmin = () => import("@/features/admin/WalletAdminPages");
const configPages = () => import("@/features/admin/ConfigPages");
const platformPages = () => import("@/features/admin/PlatformPages");
const smsPages = () => import("@/features/sms/SmsPages");
const advancePages = () => import("@/features/workspace/AdvanceBookingPages");
const legalPublic = () => import("@/features/legal/PublicLegalPages");
const legalAdmin = () => import("@/features/legal/AdminLegalPages");
const legalWorkspace = () => import("@/features/legal/WorkspaceLegalPages");

const ADMIN_NAV: NavItem[] = [
  { to: "/admin", label: "Overview", icon: <LayoutDashboard />, end: true },
  { to: "/admin/applications", label: "Applications", icon: <Inbox />, badge: "pending_applications" },
  { to: "/admin/registration-payments", label: "Registration payments", icon: <BadgeCheck />, badge: "pending_registration_payments" },
  { to: "/admin/turfs", label: "Turfs", icon: <Building2 /> },
  { to: "/admin/billing", label: "Plans & payments", icon: <CreditCard />, badge: "pending_payments" },
  { to: "/admin/subscriptions", label: "Subscriptions", icon: <CalendarClock /> },
  { to: "/admin/promo-codes", label: "Promo codes", icon: <TicketPercent /> },
  { to: "/admin/accounts", label: "Accounts", icon: <UserCog /> },
  { to: "/admin/sms", label: "SMS", icon: <MessageSquareText /> },
  { to: "/admin/sms-wallet", label: "SMS wallets", icon: <Wallet />, badge: "pending_recharges" },
  { to: "/admin/sms-usage", label: "SMS usage", icon: <BarChart3 /> },
  { to: "/admin/finance", label: "Finance", icon: <Landmark /> },
  { to: "/admin/api", label: "API", icon: <PlugZap /> },
  { to: "/admin/legal", label: "Legal & Compliance", icon: <Scale /> },
  { to: "/admin/health", label: "Health", icon: <HeartPulse /> },
  { to: "/admin/audit", label: "Audit log", icon: <History /> },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: "/workspace", label: "Dashboard", icon: <LayoutDashboard />, end: true },
  { to: "/workspace/book", label: "Book a slot", icon: <CalendarPlus /> },
  { to: "/workspace/payments", label: "Payment verification", icon: <ShieldCheck />, badge: "pending_payments_to_verify" },
  { to: "/workspace/bookings", label: "Bookings", icon: <CalendarDays />, badge: "pending_bookings" },
  { to: "/workspace/advance-bookings", label: "Advance & recurring", icon: <Repeat />, permission: "advance_bookings" },
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
  { to: "/workspace/legal", label: "Legal & Policies", icon: <FileText /> },
];

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { path: "/", element: page(() => import("@/features/public/HomePage"), "HomePage") },
      // The public turf directory was retired: old links land on the home page.
      { path: "/explore", element: <Navigate to="/" replace /> },
      { path: "/turf/:slug", element: <TurfAlias /> },
      { path: "/turfs/:slug", element: <TurfDetailPage /> },
      { path: "/register-turf", element: page(() => import("@/features/public/RegisterTurfPage"), "RegisterTurfPage") },
      { path: "/booking-status", element: page(() => import("@/features/public/BookingStatusPage"), "BookingStatusPage") },
      { path: "/registration-status", element: page(() => import("@/features/public/RegistrationStatusPage"), "RegistrationStatusPage") },
      { path: "/status", element: page(() => import("@/features/system/SystemStatusPage"), "SystemStatusPage") },
      { path: "/terms", element: <Navigate to="/legal/terms" replace /> },
      { path: "/legal", element: page(legalPublic, "LegalIndexPage") },
      { path: "/legal/sector/:slug", element: page(legalPublic, "SectorLegalPage") },
      { path: "/legal/:slug", element: page(legalPublic, "LegalDocumentPage") },
    ],
  },
  { path: "/login", element: page(() => import("@/features/auth/LoginPage"), "LoginPage") },
  { path: "/forgot-password", element: page(passwordPages, "ForgotPasswordPage") },
  { path: "/set-password", element: page(passwordPages, "SetPasswordPage") },
  { path: "/accept-terms", element: page(legalWorkspace, "LegalGatePage") },
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
      { path: "registration-payments", element: page(() => import("@/features/admin/RegistrationPaymentsPage"), "AdminRegistrationPaymentsPage") },
      { path: "turfs", element: page(adminPages, "AdminTurfsPage") },
      { path: "billing", element: page(billingPages, "AdminBillingPage") },
      { path: "promo-codes", element: page(() => import("@/features/admin/PromoCodesPage"), "AdminPromoCodesPage") },
      { path: "accounts", element: page(() => import("@/features/admin/AccountsPage"), "AdminAccountsPage") },
      { path: "sms", element: page(smsPages, "AdminSmsPage") },
      { path: "sms-usage", element: page(smsPages, "AdminSmsUsagePage") },
      { path: "sms-wallet", element: page(walletAdmin, "AdminSmsWalletPage") },
      { path: "finance", element: page(walletAdmin, "AdminFinancePage") },
      { path: "api", element: page(configPages, "AdminApiPage") },
      { path: "terms", element: <Navigate to="/admin/legal" replace /> },
      { path: "legal", element: page(legalAdmin, "AdminLegalPage") },
      { path: "legal/documents/:id", element: page(legalAdmin, "AdminLegalDocumentPage") },
      { path: "legal/versions/:id/edit", element: page(legalAdmin, "AdminLegalEditorPage") },
      { path: "legal/versions/:a/compare/:b", element: page(legalAdmin, "AdminLegalComparePage") },
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
      { path: "advance-bookings", element: page(advancePages, "AdvanceBookingsPage") },
      { path: "advance-bookings/new", element: page(advancePages, "CreateAdvanceBookingPage") },
      { path: "advance-bookings/:id", element: page(advancePages, "SeriesDetailPage") },
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
      { path: "legal", element: page(legalWorkspace, "LegalPoliciesPage") },
      { path: "account", element: page(accountPage, "AccountPage") },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
