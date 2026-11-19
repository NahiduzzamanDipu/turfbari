"""All /api/ routes, grouped by audience: public, auth, admin, workspace."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.accounts import two_factor
from apps.accounts import views as auth
from apps.applications.admin_views import AdminDashboardView, ApplicationAdminViewSet, TurfAdminViewSet
from apps.audit import views as audit
from apps.bookings import workspace_views as ws
from apps.common.live import LiveView
from apps.expenses.views import ExpenseViewSet
from apps.subscriptions import views as subs
from apps.turfs import public_views as public
from apps.turfs import workspace_views as setup

admin_router = SimpleRouter()
admin_router.register("applications", ApplicationAdminViewSet, basename="admin-applications")
admin_router.register("turfs", TurfAdminViewSet, basename="admin-turfs")
admin_router.register("plans", subs.PlanAdminViewSet, basename="admin-plans")
admin_router.register("payments", subs.PaymentAdminViewSet, basename="admin-payments")
admin_router.register("promo-codes", subs.PromoCodeAdminViewSet, basename="admin-promo-codes")

workspace_router = SimpleRouter()
workspace_router.register("bookings", ws.BookingViewSet, basename="ws-bookings")
workspace_router.register("customers", ws.CustomerViewSet, basename="ws-customers")
workspace_router.register("maintenance", ws.MaintenanceViewSet, basename="ws-maintenance")
workspace_router.register("fields", setup.FieldViewSet, basename="ws-fields")
workspace_router.register("pricing-rules", setup.PricingRuleViewSet, basename="ws-pricing")
workspace_router.register("expenses", ExpenseViewSet, basename="ws-expenses")
workspace_router.register("photos", setup.PhotoViewSet, basename="ws-photos")

public_urls = [
    path("locations/", public.LocationsView.as_view()),
    path("amenities/", public.AmenitiesView.as_view()),
    path("stats/", public.StatsView.as_view()),
    path("turfs/", public.PublicTurfListView.as_view()),
    path("turfs/<slug:slug>/", public.PublicTurfDetailView.as_view()),
    path("turfs/<slug:slug>/availability/", public.PublicAvailabilityView.as_view()),
    path("turfs/<slug:slug>/book/", public.PublicBookingRequestView.as_view()),
    path("turfs/<slug:slug>/hold/", public.PublicHoldView.as_view()),
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
    path("2fa/", two_factor.TwoFactorStatusView.as_view()),
    path("2fa/setup/", two_factor.TwoFactorSetupView.as_view()),
    path("2fa/confirm/", two_factor.TwoFactorConfirmView.as_view()),
    path("2fa/disable/", two_factor.TwoFactorDisableView.as_view()),
    path("2fa/recovery-codes/", two_factor.RecoveryCodesView.as_view()),
    path("2fa/verify/", two_factor.TwoFactorVerifyView.as_view()),
    path("2fa/resend/", two_factor.ResendEmailCodeView.as_view()),
]

admin_urls = [
    path("dashboard/", AdminDashboardView.as_view()),
    path("turfs/<uuid:pk>/assign-plan/", subs.AssignPlanView.as_view()),
    path("audit/", audit.AdminAuditView.as_view()),
    path("", include(admin_router.urls)),
]

workspace_urls = [
    path("dashboard/", ws.DashboardView.as_view()),
    path("availability/", ws.AvailabilityView.as_view()),
    path("quote/", ws.QuoteView.as_view()),
    path("hours/", setup.HoursView.as_view()),
    path("settings/", setup.SettingsView.as_view()),
    path("profile-picture/", setup.ProfilePictureView.as_view()),
    path("managers/", setup.ManagersView.as_view()),
    path("managers/<uuid:pk>/", setup.ManagerDetailView.as_view()),
    path("activity/", audit.WorkspaceActivityView.as_view()),
    path("subscription/", subs.SubscriptionOverviewView.as_view()),
    path("subscription/order/", subs.SubscriptionOrderView.as_view()),
    path("subscription/invoices/<uuid:pk>/manual-payment/", subs.InvoiceManualPaymentView.as_view()),
    path("subscription/invoices/<uuid:pk>/pay-online/", subs.InvoicePayOnlineView.as_view()),
    path("subscription/invoices/<uuid:pk>/cancel/", subs.InvoiceCancelView.as_view()),
    path("subscription/invoices/<uuid:pk>/promo/", subs.InvoicePromoView.as_view()),
    path("reports/summary/", ws.ReportSummaryView.as_view()),
    path("reports/bookings.xlsx", ws.BookingsExportView.as_view()),
    path("", include(workspace_router.urls)),
]

payment_urls = [
    path("sslcommerz/success/", subs.SSLCommerzCallbackView.as_view(outcome="success")),
    path("sslcommerz/fail/", subs.SSLCommerzCallbackView.as_view(outcome="fail")),
    path("sslcommerz/cancel/", subs.SSLCommerzCallbackView.as_view(outcome="cancel")),
    path("sslcommerz/ipn/", subs.SSLCommerzCallbackView.as_view(outcome="ipn")),
]

urlpatterns = [
    path("live/", LiveView.as_view()),
    path("public/", include(public_urls)),
    path("payments/", include(payment_urls)),
    path("auth/", include(auth_urls)),
    path("admin/", include(admin_urls)),
    path("workspace/", include(workspace_urls)),
]
