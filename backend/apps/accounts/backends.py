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
