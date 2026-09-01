"""Custom User manager for SanteGeste."""

from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for authentication."""

    use_in_migrations = True

    def _create_user(
        self,
        email: str,
        username: str,
        password: str | None,
        **extra_fields: Any,
    ) -> Any:
        """Create and save a user with the given email, username, and password."""
        if not email:
            raise ValueError("L'email est obligatoire.")
        if not username:
            raise ValueError("Le username est obligatoire.")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        username: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create a standard user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", False)
        return self._create_user(email, username, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        username: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superuser doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superuser doit avoir is_superuser=True.")

        return self._create_user(email, username, password, **extra_fields)
