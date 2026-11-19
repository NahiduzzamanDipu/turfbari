from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with email or username (case-insensitive) + password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or "").strip().lower()
        if not identifier or password is None:
            return None
        User = get_user_model()
        field = "email" if "@" in identifier else "username"
        try:
            user = User._default_manager.get(**{field: identifier})
        except User.DoesNotExist:
            # Run the hasher anyway so response timing doesn't reveal whether the account exists.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


def axes_username(request, credentials) -> str:
    """The login name django-axes counts failures against.

    Our login form posts `identifier` (email or username), not `username`, so without this axes saw
    no username at all and a username+IP lockout never triggered.
    """
    value = (credentials or {}).get("username")
    if not value:
        data = getattr(request, "data", None) or getattr(request, "POST", {})
        value = data.get("identifier") or data.get("username") or ""
    return str(value).strip().lower()


def axes_lockout_response(request, original_response=None, credentials=None, *args, **kwargs):
    """JSON (not HTML) when too many failed sign-ins locked this account, so the login page can say so."""
    from django.conf import settings
    from django.http import JsonResponse

    minutes = int(settings.AXES_COOLOFF_TIME.total_seconds() // 60)
    return JsonResponse(
        {
            "error": {
                "code": "account_locked",
                "message": f"Too many wrong passwords. Sign-in is locked for {minutes} minutes — "
                "or use “Forgot password” to reset it now.",
                "fields": None,
            }
        },
        status=429,
    )
