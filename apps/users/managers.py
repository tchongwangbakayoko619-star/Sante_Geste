"""Manager personnalisé pour le modèle Utilisateur de SantéGeste."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.users.models import User


class UserManager(BaseUserManager):
    """Manager personnalisé utilisant l'email comme identifiant unique."""

    use_in_migrations = True

    def _create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Crée et sauvegarde un utilisateur."""
        if not email:
            msg = _("L'email est obligatoire.")
            raise ValueError(msg)

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            **extra_fields,
        )

        if password is not None:
            validate_password(password, user=user)
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean(exclude=["password"])
        user.save(using=self._db)

        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Crée un utilisateur standard."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", False)

        return self._create_user(
            email,
            password,
            **extra_fields,
        )

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Crée un superutilisateur."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            msg = _("Un superuser doit avoir is_staff=True.")
            raise ValueError(msg)

        if extra_fields.get("is_superuser") is not True:
            msg = _("Un superuser doit avoir is_superuser=True.")
            raise ValueError(msg)

        return self._create_user(
            email,
            password,
            **extra_fields,
        )
