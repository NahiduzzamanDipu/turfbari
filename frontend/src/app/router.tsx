import {
  BarChart3,
  Building2,
  CalendarDays,
  CalendarPlus,
  CreditCard,
  Clock,
  Grid2x2,
  History,
  Inbox,
  LayoutDashboard,
  Receipt,
  Settings,
  Tags,
  UserCog,
  Users,
  Wrench,
} from "lucide-react";
import { createBrowserRouter } from "react-router";
import { AppShell, type NavItem } from "@/components/layout/AppShell";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { AdminApplicationsPage, AdminDashboardPage, AdminTurfsPage } from "@/features/admin/AdminPages";
import { AdminBillingPage } from "@/features/admin/BillingPages";
import { AdminAuditPage, WorkspaceActivityPage } from "@/features/audit/ActivityLog";
import { AccountPage } from "@/features/auth/AccountPage";
import { RequireRole } from "@/features/auth/auth";
import { LoginPage } from "@/features/auth/LoginPage";
import { BookingStatusPage } from "@/features/public/BookingStatusPage";
import { ExplorePage } from "@/features/public/ExplorePage";
import { HomePage } from "@/features/public/HomePage";
import { RegisterTurfPage } from "@/features/public/RegisterTurfPage";
import { TurfDetailPage } from "@/features/public/TurfDetailPage";
import { NotFoundPage } from "@/features/system/NotFoundPage";
import { SystemStatusPage } from "@/features/system/SystemStatusPage";
import { BookingsPage } from "@/features/workspace/BookingsPage";
import { DashboardPage } from "@/features/workspace/DashboardPage";
import { SlotBoardPage } from "@/features/workspace/SlotBoardPage";
import { SubscriptionPage } from "@/features/workspace/SubscriptionPage";
import {
  CustomersPage,
  ExpensesPage,
  MaintenancePage,
  ReportsPage,
} from "@/features/workspace/OperationsPages";
import { FieldsPage, HoursPage, ManagersPage, PricingPage, SettingsPage } from "@/features/workspace/SetupPages";

const ADMIN_NAV: NavItem[] = [
  { to: "/admin", label: "Overview", icon: <LayoutDashboard />, end: true },
  { to: "/admin/applications", label: "Applications", icon: <Inbox /> },
  { to: "/admin/turfs", label: "Turfs", icon: <Building2 /> },
  { to: "/admin/billing", label: "Plans & payments", icon: <CreditCard /> },
  { to: "/admin/audit", label: "Audit log", icon: <History /> },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: "/workspace", label: "Dashboard", icon: <LayoutDashboard />, end: true },
  { to: "/workspace/book", label: "Book a slot", icon: <CalendarPlus /> },
  { to: "/workspace/bookings", label: "Bookings", icon: <CalendarDays /> },
  { to: "/workspace/customers", label: "Customers", icon: <Users /> },
  { to: "/workspace/maintenance", label: "Maintenance", icon: <Wrench /> },
  { to: "/workspace/fields", label: "Fields", icon: <Grid2x2 /> },
  { to: "/workspace/hours", label: "Opening hours", icon: <Clock /> },
  { to: "/workspace/pricing", label: "Pricing", icon: <Tags /> },
  { to: "/workspace/expenses", label: "Expenses", icon: <Receipt />, ownerOnly: true },
  { to: "/workspace/reports", label: "Reports", icon: <BarChart3 />, ownerOnly: true },
  { to: "/workspace/team", label: "Team", icon: <UserCog />, ownerOnly: true },
  { to: "/workspace/activity", label: "Activity", icon: <History />, ownerOnly: true },
  { to: "/workspace/subscription", label: "Subscription", icon: <CreditCard /> },
  { to: "/workspace/settings", label: "Settings", icon: <Settings /> },
];

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/explore", element: <ExplorePage /> },
      { path: "/turfs/:slug", element: <TurfDetailPage /> },
      { path: "/register-turf", element: <RegisterTurfPage /> },
      { path: "/booking-status", element: <BookingStatusPage /> },
      { path: "/status", element: <SystemStatusPage /> },
    ],
  },
  { path: "/login", element: <LoginPage /> },
  {
    path: "/admin",
    element: (
      <RequireRole role="admin">
        <AppShell nav={ADMIN_NAV} area="admin" />
      </RequireRole>
    ),
    children: [
      { index: true, element: <AdminDashboardPage /> },
      { path: "applications", element: <AdminApplicationsPage /> },
      { path: "turfs", element: <AdminTurfsPage /> },
      { path: "billing", element: <AdminBillingPage /> },
      { path: "audit", element: <AdminAuditPage /> },
      { path: "account", element: <AccountPage /> },
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
      { index: true, element: <DashboardPage /> },
      { path: "book", element: <SlotBoardPage /> },
      { path: "bookings", element: <BookingsPage /> },
      { path: "customers", element: <CustomersPage /> },
      { path: "maintenance", element: <MaintenancePage /> },
      { path: "fields", element: <FieldsPage /> },
      { path: "hours", element: <HoursPage /> },
      { path: "pricing", element: <PricingPage /> },
      { path: "expenses", element: <ExpensesPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "team", element: <ManagersPage /> },
      { path: "activity", element: <WorkspaceActivityPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "subscription", element: <SubscriptionPage /> },
      { path: "account", element: <AccountPage /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
