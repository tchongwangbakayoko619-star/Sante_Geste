"""Application-wide enumerations."""

from django.db import models


class OTPPurposeEnum(models.TextChoices):
    """OTP Purposes enumeration."""

    REGISTRATION = "registration", "Inscription"
    PASSWORD_RESET = "password_reset", "Réinitialisation mot de passe"
