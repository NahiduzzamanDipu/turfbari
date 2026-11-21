"""All /api/ routes, grouped by audience: public, auth, admin, workspace."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.accounts import admin_views as accounts_admin
from apps.accounts import two_factor
from apps.accounts import views as auth
from apps.applications import registration_views as reg
from apps.applications.admin_views import AdminDashboardView, ApplicationAdminViewSet, TurfAdminViewSet
from apps.assistant import views as assistant
from apps.audit import views as audit
from apps.bookings import series_views as series
from apps.bookings import verification_views as verify
from apps.bookings import workspace_views as ws
from apps.common import platform_views as platform
from apps.common.live import LiveView
from apps.demo import views as demo
from apps.expenses.views import ExpenseViewSet
from apps.homepage import api as homepage
from apps.legal import admin_views as legal_admin
from apps.legal import views as legal
from apps.notifications import campaigns as sms_campaigns
from apps.notifications import usage as sms_usage
from apps.notifications import views as sms
from apps.notifications import wallet_views as sms_wallet
from apps.subscriptions import admin_tools as subs_admin
from apps.subscriptions import views as subs
from apps.turfs import design_views as design
from apps.turfs import public_views as public
from apps.turfs import slot_views as slots
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
workspace_router.register("slot-templates", slots.SlotTemplateViewSet, basename="ws-slot-templates")
workspace_router.register("expenses", ExpenseViewSet, basename="ws-expenses")
workspace_router.register("photos", setup.PhotoViewSet, basename="ws-photos")

public_urls = [
    path("assistant/status/", assistant.PublicAssistantStatusView.as_view()),
    path("assistant/conversations/", assistant.PublicConversationStartView.as_view()),
    path("assistant/messages/", assistant.PublicConversationView.as_view()),
    path("assistant/conversations/clear/", assistant.PublicConversationClearView.as_view()),
    path("assistant/feedback/", assistant.PublicFeedbackView.as_view()),
    path("language-settings/", platform.PublicLanguageSettingsView.as_view()),
    path("demo/qr.svg", demo.DemoQRCodeView.as_view()),
    path("demo/owner-access/", demo.DemoOwnerAccessView.as_view()),
    path("demo/turf/", demo.DemoTurfView.as_view()),
    path("demo/availability/", demo.DemoAvailabilityView.as_view()),
    path("demo/hold/", demo.DemoHoldView.as_view()),
    path("demo/book/", demo.DemoBookingCreateView.as_view()),
    path("demo/bookings/status/<str:reference>/", demo.DemoBookingStatusView.as_view()),
    path("demo/owner/workspace/", demo.DemoOwnerWorkspaceView.as_view()),
    path("demo/owner/bookings/<uuid:pk>/", demo.DemoBookingActionView.as_view()),
    path("demo/owner/slots/", demo.DemoSlotsView.as_view()),
    path("demo/owner/slots/<uuid:pk>/", demo.DemoSlotDetailView.as_view()),
    # Legacy public endpoint intentionally returns only non-sensitive demo configuration.
    path("demo/workspace/", demo.DemoWorkspaceView.as_view()),
    path("plans/", homepage.PublicPlansView.as_view()),
    path("sms-pricing/", homepage.PublicSmsPricingView.as_view()),
    path("youtube/homepage/", homepage.PublicHomepageYoutubeView.as_view()),
    path("youtube/", homepage.PublicYoutubeView.as_view()),
    path("faqs/", homepage.PublicFAQsView.as_view()),
    path("client-showcase/", homepage.PublicClientShowcaseView.as_view()),
    path("contact/", platform.PublicContactView.as_view()),
    path("locations/", public.LocationsView.as_view()),
    path("amenities/", public.AmenitiesView.as_view()),
    path("turfs/<slug:slug>/", public.PublicTurfDetailView.as_view()),
    path("turfs/<slug:slug>/availability/", public.PublicAvailabilityView.as_view()),
    path("turfs/<slug:slug>/book/", public.PublicBookingRequestView.as_view()),
    path("turfs/<slug:slug>/hold/", public.PublicHoldView.as_view()),
    path("turfs/<slug:slug>/qr.svg", public.TurfQRCodeView.as_view()),
    path("bookings/lookup/", public.PublicBookingLookupView.as_view()),
    path("applications/", public.PublicApplicationView.as_view()),
    path("registration/options/", reg.RegistrationOptionsView.as_view()),
    path("registration/quote/", reg.RegistrationQuoteView.as_view()),
    path("registration/status/", reg.RegistrationStatusView.as_view()),
    path("registration/resubmit/", reg.RegistrationResubmitView.as_view()),
    path("legal/", legal.PublicLegalIndexView.as_view()),
    path("legal/required/", legal.PublicRequiredView.as_view()),
    path("legal/versions/<int:pk>/", legal.PublicVersionView.as_view()),
    path("legal/sector/<slug:slug>/", legal.PublicSectorLegalView.as_view()),
    path("legal/<slug:slug>/", legal.PublicLegalDocumentView.as_view()),
]

legal_urls = [
    path("status/", legal.LegalStatusView.as_view()),
    path("pending/", legal.LegalPendingView.as_view()),
    path("accept/", legal.LegalAcceptView.as_view()),
]

auth_urls = [
    path("language/", auth.LanguagePreferenceView.as_view()),
    path("login/", auth.LoginView.as_view()),
    path("logout/", auth.LogoutView.as_view()),
    path("me/", auth.MeView.as_view()),
    path("switch-turf/", auth.SwitchTurfView.as_view()),
    path("change-password/", auth.ChangePasswordView.as_view()),
    path("password-reset/", auth.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", auth.PasswordResetConfirmView.as_view()),
    path("2fa/", two_factor.TwoFactorStatusView.as_view()),
    path("2fa/setup/", two_factor.TwoFactorSetupView.as_view()),
    path("2fa/confirm/", two_factor.TwoFactorConfirmView.as_view()),
    path("2fa/disable/", two_factor.TwoFactorDisableView.as_view()),
    path("2fa/recovery-codes/", two_factor.RecoveryCodesView.as_view()),
    path("2fa/verify/", two_factor.TwoFactorVerifyView.as_view()),
    path("2fa/resend/", two_factor.ResendEmailCodeView.as_view()),
]

admin_urls = [
    path("assistant/settings/", assistant.AdminAssistantSettingsView.as_view()),
    path("assistant/articles/", assistant.AdminKnowledgeArticlesView.as_view()),
    path("assistant/articles/<uuid:pk>/", assistant.AdminKnowledgeArticlesView.as_view()),
    path("assistant/import/", assistant.AdminKnowledgeImportView.as_view()),
    path("assistant/sources/", assistant.AdminKnowledgeSourcesView.as_view()),
    path("assistant/sources/<uuid:pk>/", assistant.AdminKnowledgeSourcesView.as_view()),
    path("assistant/reindex/", assistant.AdminKnowledgeReindexView.as_view()),
    path("assistant/analytics/", assistant.AdminAssistantAnalyticsView.as_view()),
    path("assistant/questions/", assistant.AdminSuggestedQuestionsView.as_view()),
    path("assistant/questions/<uuid:pk>/", assistant.AdminSuggestedQuestionsView.as_view()),
    path("language-settings/", platform.AdminLanguageSettingsView.as_view()),
    path("demo/workspaces/", demo.AdminDemoWorkspacesView.as_view()),
    path("demo/workspaces/<uuid:pk>/", demo.AdminDemoWorkspaceDetailView.as_view()),
    path("demo/workspaces/<uuid:pk>/reset/", demo.AdminDemoWorkspaceResetView.as_view()),
    path("demo/workspaces/<uuid:pk>/activity/", demo.AdminDemoWorkspaceActivityView.as_view()),
    path("homepage/faqs/", homepage.AdminFAQsView.as_view()),
    path("homepage/faqs/<uuid:pk>/", homepage.AdminFAQsView.as_view()),
    path("homepage/client-showcase/", homepage.AdminClientShowcaseView.as_view()),
    path("homepage/client-showcase/<uuid:turf_id>/", homepage.AdminClientShowcaseItemView.as_view()),
    path("onboarding/", homepage.AdminOnboardingView.as_view()),
    path("onboarding/<uuid:pk>/", homepage.AdminOnboardingView.as_view()),
    path("dashboard/", AdminDashboardView.as_view()),
    path("registration-payments/", reg.AdminRegistrationPaymentsView.as_view()),
    path("registration-payments/<uuid:pk>/approve/", reg.AdminRegistrationApproveView.as_view()),
    path("registration-payments/<uuid:pk>/reject/", reg.AdminRegistrationRejectView.as_view()),
    path("turfs/<uuid:pk>/assign-plan/", subs.AssignPlanView.as_view()),
    path("turfs/<uuid:pk>/subscription-history/", subs_admin.AdminTurfSubscriptionHistoryView.as_view()),
    path("turfs/<uuid:pk>/extend-subscription/", subs_admin.AdminExtendSubscriptionView.as_view()),
    path("turfs/<uuid:pk>/end-subscription/", subs_admin.AdminEndSubscriptionView.as_view()),
    path("subscriptions/", subs_admin.AdminSubscriptionsView.as_view()),
    path("health/", subs_admin.AdminHealthView.as_view()),
    path("api-config/", platform.AdminApiConfigView.as_view()),
    path("contact-settings/", platform.AdminContactSettingsView.as_view()),
    path("api-config/youtube/homepage/", platform.AdminHomepageYoutubeView.as_view()),
    path("api-config/youtube/booking/", platform.AdminYoutubeView.as_view()),
    path("api-config/youtube/", platform.AdminYoutubeView.as_view()),
    path("api-config/bulksmsbd/", platform.AdminBulkSmsView.as_view()),
    path("api-config/booking/", platform.AdminBookingPolicyView.as_view()),
    path("api-config/credentials/", platform.AdminCredentialSmsView.as_view()),
    path("api-config/recurring/", platform.AdminRecurringPolicyView.as_view()),
    path("legal/", legal_admin.AdminLegalOverviewView.as_view()),
    path("legal/sectors/", legal_admin.AdminSectorsView.as_view()),
    path("legal/sectors/<uuid:pk>/", legal_admin.AdminSectorDetailView.as_view()),
    path("legal/documents/", legal_admin.AdminDocumentsView.as_view()),
    path("legal/documents/<uuid:pk>/", legal_admin.AdminDocumentDetailView.as_view()),
    path("legal/documents/<uuid:pk>/versions/", legal_admin.AdminDocumentVersionsView.as_view()),
    path("legal/documents/<uuid:pk>/standard-text/", legal_admin.AdminStandardTextView.as_view()),
    path("legal/versions/<int:pk>/", legal_admin.AdminVersionView.as_view()),
    path("legal/versions/<int:pk>/publish/", legal_admin.AdminVersionPublishView.as_view()),
    path("legal/versions/<int:pk>/unpublish/", legal_admin.AdminVersionUnpublishView.as_view()),
    path("legal/versions/<int:pk>/compare/<int:other>/", legal_admin.AdminVersionCompareView.as_view()),
    path("legal/acceptances/", legal_admin.AdminAcceptancesView.as_view()),
    path("legal/pending/", legal_admin.AdminPendingView.as_view()),
    path("audit/", audit.AdminAuditView.as_view()),
    path("sms/", sms.AdminSmsOverviewView.as_view()),
    path("sms/messages/", sms.AdminSmsMessagesView.as_view()),
    path("sms/usage/", sms_usage.AdminSmsUsageView.as_view()),
    path("sms/pricing/", sms_wallet.AdminPricingView.as_view()),
    path("sms/recharges/", sms_wallet.AdminRechargeListView.as_view()),
    path("sms/recharges/<uuid:pk>/<slug:decision>/", sms_wallet.AdminRechargeDecisionView.as_view()),
    path("sms/wallets/", sms_wallet.AdminWalletsView.as_view()),
    path("sms/messages/<uuid:pk>/refund/", sms_wallet.AdminSmsRefundView.as_view()),
    path("turfs/<uuid:pk>/sms/", sms_wallet.AdminTurfSmsView.as_view()),
    path("turfs/<uuid:pk>/sms/adjust/", sms_wallet.AdminWalletAdjustView.as_view()),
    path("finance/", sms_wallet.AdminFinanceView.as_view()),
    path("api-config/payments/", sms_wallet.AdminPaymentSettingsView.as_view()),
    path("sms/messages/<uuid:pk>/retry/", sms.AdminSmsRetryView.as_view()),
    path("sms/test/", sms.AdminSmsTestView.as_view()),
    path("sms/templates/", sms.AdminSmsTemplatesView.as_view()),
    path("sms/templates/<slug:kind>/", sms.AdminSmsTemplatesView.as_view()),
    path("users/", accounts_admin.AccountListView.as_view()),
    path("users/<uuid:pk>/", accounts_admin.AccountDetailView.as_view()),
    path("users/<uuid:pk>/memberships/", accounts_admin.AccountMembershipsView.as_view()),
    path("users/<uuid:pk>/credential/", accounts_admin.AccountCredentialView.as_view()),
    path("users/<uuid:pk>/credential/resend/", accounts_admin.AccountCredentialResendView.as_view()),
    path("users/<uuid:pk>/<slug:action>/", accounts_admin.AccountActionView.as_view()),
    path("memberships/<uuid:pk>/", accounts_admin.MembershipDetailView.as_view()),
    path("", include(admin_router.urls)),
]

workspace_urls = [
    path("dashboard/", ws.DashboardView.as_view()),
    path("availability/", ws.AvailabilityView.as_view()),
    path("booking-series/", series.SeriesListView.as_view()),
    path("booking-series/preview/", series.SeriesPreviewView.as_view()),
    path("booking-series/<uuid:pk>/", series.SeriesDetailView.as_view()),
    path("booking-series/<uuid:pk>/confirm/", series.SeriesConfirmView.as_view()),
    path("booking-series/<uuid:pk>/cancel/", series.SeriesCancelView.as_view()),
    path("booking-series/<uuid:pk>/add-date/", series.SeriesAddDateView.as_view()),
    path("booking-series/<uuid:pk>/reschedule/", series.SeriesRescheduleView.as_view()),
    path("payment-verifications/", verify.PaymentVerificationListView.as_view()),
    path("payment-verifications/<uuid:pk>/approve/", verify.PaymentApproveView.as_view()),
    path("payment-verifications/<uuid:pk>/reject/", verify.PaymentRejectView.as_view()),
    path("quote/", ws.QuoteView.as_view()),
    path("hours/", setup.HoursView.as_view()),
    path("price-categories/", slots.PriceCategoriesView.as_view()),
    path("design/", design.DesignView.as_view()),
    path("design/publish/", design.DesignPublishView.as_view()),
    path("settings/", setup.SettingsView.as_view()),
    path("profile-picture/", setup.ProfilePictureView.as_view()),
    path("booking-page/qr.<str:kind>", setup.BookingQRView.as_view()),
    path("booking-page/poster-info/", setup.BookingPosterInfoView.as_view()),
    path("managers/", setup.ManagersView.as_view()),
    path("managers/<uuid:pk>/", setup.ManagerDetailView.as_view()),
    path("activity/", audit.WorkspaceActivityView.as_view()),
    path("sms/", sms.WorkspaceSmsView.as_view()),
    path("sms/settings/", sms.WorkspaceSmsSettingsView.as_view()),
    path("sms/usage/", sms_usage.WorkspaceSmsUsageView.as_view()),
    path("sms/wallet/", sms_wallet.WalletView.as_view()),
    path("sms/wallet/ledger/", sms_wallet.LedgerView.as_view()),
    path("sms/wallet/recharge/", sms_wallet.RechargeView.as_view()),
    path("sms/retry-blocked/", sms_wallet.RetryBlockedView.as_view()),
    path("sms/messages/<uuid:pk>/retry/", sms_wallet.RetryBlockedView.as_view()),
    path("sms/send/", sms_campaigns.SingleSmsView.as_view()),
    path("sms/campaigns/", sms_campaigns.CampaignListView.as_view()),
    path("sms/campaigns/preview/", sms_campaigns.CampaignPreviewView.as_view()),
    path("sms/campaigns/<uuid:pk>/", sms_campaigns.CampaignDetailView.as_view()),
    path("subscription/", subs.SubscriptionOverviewView.as_view()),
    path("subscription/order/", subs.SubscriptionOrderView.as_view()),
    path("subscription/invoices/<uuid:pk>/manual-payment/", subs.InvoiceManualPaymentView.as_view()),
    path("subscription/invoices/<uuid:pk>/pay-online/", subs.InvoicePayOnlineView.as_view()),
    path("subscription/invoices/<uuid:pk>/cancel/", subs.InvoiceCancelView.as_view()),
    path("subscription/invoices/<uuid:pk>/promo/", subs.InvoicePromoView.as_view()),
    path("reports/summary/", ws.ReportSummaryView.as_view()),
    path("reports/bookings.xlsx", ws.BookingsExportView.as_view()),
    path("customers/export.xlsx", ws.CustomerExportView.as_view()),
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
    path("system/tick/", sms.TickView.as_view()),
    path("public/", include(public_urls)),
    path("payments/", include(payment_urls)),
    path("auth/", include(auth_urls)),
    path("legal/", include(legal_urls)),
    path("admin/", include(admin_urls)),
    path("workspace/", include(workspace_urls)),
]
