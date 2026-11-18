"""Super Admin sessions end ADMIN_SESSION_HOURS after sign-in, however active they are."""

import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .two_factor import AUTH_AT_KEY


@receiver(user_logged_in)
def _stamp_sign_in_time(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session[AUTH_AT_KEY] = time.time()


class AdminSessionLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_platform_admin:
            started = request.session.get(AUTH_AT_KEY)
            if started is None or time.time() - started > settings.ADMIN_SESSION_HOURS * 3600:
                logout(request)
        return self.get_response(request)
