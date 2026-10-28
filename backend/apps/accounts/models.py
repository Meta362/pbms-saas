import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from apps.core.models import TimeStampedUUIDModel


class PlatformRole(models.TextChoices):
    NONE = "NONE", "None (Tenant User Only)"
    SUPER_ADMIN = "SUPER_ADMIN", "Platform Super Admin"
    PLATFORM_SUPPORT = "PLATFORM_SUPPORT", "Platform Support"


class LanguagePreference(models.TextChoices):
    KHMER = "km", "Khmer"
    ENGLISH = "en", "English"


class UserManager(BaseUserManager["User"]):
    def create_user(
        self,
        email: str,
        password: str | None = None,
        full_name: str = "",
        **extra_fields: object,
    ) -> "User":
        if not email:
            raise ValueError("Users must have an email address.")
        normalized_email = self.normalize_email(email).lower().strip()
        user = self.model(
            email=normalized_email,
            full_name=full_name,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str,
        full_name: str = "Platform Super Admin",
        **extra_fields: object,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_platform_staff", True)
        extra_fields.setdefault("platform_role", PlatformRole.SUPER_ADMIN)
        return self.create_user(email=email, password=password, full_name=full_name, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedUUIDModel):
    email = models.EmailField(unique=True, max_length=255, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_platform_staff = models.BooleanField(default=False)
    platform_role = models.CharField(
        max_length=32,
        choices=PlatformRole.choices,
        default=PlatformRole.NONE,
    )
    preferred_language = models.CharField(
        max_length=5,
        choices=LanguagePreference.choices,
        default=LanguagePreference.KHMER,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"


class AuthSession(TimeStampedUUIDModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="auth_sessions",
    )
    current_refresh_jti_hash = models.CharField(max_length=64, db_index=True)
    previous_refresh_jti_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    is_revoked = models.BooleanField(default=False, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=120, blank=True, default="")
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "accounts_authsession"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_revoked", "expires_at"]),
        ]

    def __str__(self) -> str:
        status = "REVOKED" if self.is_revoked else "ACTIVE"
        return f"Session {self.id} ({self.user.email}) [{status}]"
