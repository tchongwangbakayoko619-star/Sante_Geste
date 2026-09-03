"""Mixins réutilisables pour les formulaires de l'application users."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PasswordConfirmationMixin:
    """Mixin pour valider et comparer deux champs de mot de passe."""

    password1_field: str = "password1"
    password2_field: str = "password2"

    def clean_passwords(self, cleaned_data: dict[str, Any], *, user=None) -> None:
        """Valide la correspondance des mots de passe et leur complexité."""
        password1 = cleaned_data.get(self.password1_field)
        password2 = cleaned_data.get(self.password2_field)

        if password1 and password2 and password1 != password2:
            self.add_error(
                self.password2_field,
                _("Les mots de passe ne correspondent pas."),
            )

        if password1:
            try:
                validate_password(password1, user=user)
            except ValidationError as error:
                self.add_error(self.password1_field, error)
