"""Custom user model. Defined in Phase 2 because Django cannot swap AUTH_USER_MODEL later.

Role and tenant membership are NOT stored on the user (except the platform-admin flag);
turf owners and managers get their access from tenants.TenantMembership (Phase 3).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("is_platform_admin", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        """Creates the TurfBari Super Admin (platform admin + Django superuser)."""
        extra.update(is_staff=True, is_superuser=True, is_platform_admin=True)
        return self._create_user(email, password, **extra)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=40, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can open the emergency Django admin.")
    is_platform_admin = models.BooleanField(default=False, help_text="TurfBari Super Admin.")

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        # Uniqueness is case-insensitive twice over: save() lowercases, and the utf8mb4 *_ci
        # collation (MySQL 0900_ai_ci / MariaDB unicode_ci) compares case-insensitively.
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.username:
            self.username = self.username.strip().lower()
        else:
            self.username = None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email


class TwoFactorDevice(models.Model):
    """Authenticator-app secret for one user. `confirmed` only after the first correct code."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)  # last accepted TOTP step: blocks code replay
    recovery_hashes = models.JSONField(default=list, blank=True)  # sha256 of unused recovery codes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"2FA for {self.user}"
