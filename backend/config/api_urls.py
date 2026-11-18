"""All /api/ routes, grouped by audience: public, auth, admin, workspace."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.accounts import views as auth
from apps.applications.admin_views import AdminDashboardView, ApplicationAdminViewSet, TurfAdminViewSet
from apps.bookings import workspace_views as ws
from apps.expenses.views import ExpenseViewSet
from apps.turfs import public_views as public
from apps.turfs import workspace_views as setup

admin_router = SimpleRouter()
admin_router.register("applications", ApplicationAdminViewSet, basename="admin-applications")
admin_router.register("turfs", TurfAdminViewSet, basename="admin-turfs")

workspace_router = SimpleRouter()
workspace_router.register("bookings", ws.BookingViewSet, basename="ws-bookings")
workspace_router.register("customers", ws.CustomerViewSet, basename="ws-customers")
workspace_router.register("maintenance", ws.MaintenanceViewSet, basename="ws-maintenance")
workspace_router.register("fields", setup.FieldViewSet, basename="ws-fields")
workspace_router.register("pricing-rules", setup.PricingRuleViewSet, basename="ws-pricing")
workspace_router.register("expenses", ExpenseViewSet, basename="ws-expenses")

public_urls = [
    path("locations/", public.LocationsView.as_view()),
    path("amenities/", public.AmenitiesView.as_view()),
    path("stats/", public.StatsView.as_view()),
    path("turfs/", public.PublicTurfListView.as_view()),
    path("turfs/<slug:slug>/", public.PublicTurfDetailView.as_view()),
    path("turfs/<slug:slug>/availability/", public.PublicAvailabilityView.as_view()),
    path("turfs/<slug:slug>/book/", public.PublicBookingRequestView.as_view()),
    path("turfs/<slug:slug>/qr.svg", public.TurfQRCodeView.as_view()),
    path("bookings/lookup/", public.PublicBookingLookupView.as_view()),
    path("applications/", public.PublicApplicationView.as_view()),
]

auth_urls = [
    path("login/", auth.LoginView.as_view()),
    path("logout/", auth.LogoutView.as_view()),
    path("me/", auth.MeView.as_view()),
    path("switch-turf/", auth.SwitchTurfView.as_view()),
    path("change-password/", auth.ChangePasswordView.as_view()),
]

admin_urls = [
    path("dashboard/", AdminDashboardView.as_view()),
    path("", include(admin_router.urls)),
]

workspace_urls = [
    path("dashboard/", ws.DashboardView.as_view()),
    path("availability/", ws.AvailabilityView.as_view()),
    path("quote/", ws.QuoteView.as_view()),
    path("hours/", setup.HoursView.as_view()),
    path("settings/", setup.SettingsView.as_view()),
    path("managers/", setup.ManagersView.as_view()),
    path("managers/<uuid:pk>/", setup.ManagerDetailView.as_view()),
    path("reports/summary/", ws.ReportSummaryView.as_view()),
    path("reports/bookings.xlsx", ws.BookingsExportView.as_view()),
    path("", include(workspace_router.urls)),
]

urlpatterns = [
    path("public/", include(public_urls)),
    path("auth/", include(auth_urls)),
    path("admin/", include(admin_urls)),
    path("workspace/", include(workspace_urls)),
]
