"""Application-wide enumerations."""

from django.db import models


class OTPPurposeEnum(models.TextChoices):
    """OTP Purposes enumeration."""

    REGISTRATION = "registration", "Inscription"
    PASSWORD_RESET = "password_reset", "Réinitialisation mot de passe"
    TWO_FACTOR = "two_factor", "Authentification à deux facteurs"


class UserRoleEnum(models.TextChoices):
    """Rôles applicatifs SantéGeste / CS² Health."""

    PERSONNEL_MEDICAL = "personnel_medical", "Personnel médical"
    PROPRIETAIRE = "proprietaire", "Propriétaire de l'établissement"
    RESPONSABLE_PHARMACIE = "responsable_pharmacie", "Responsable pharmacie"
    VENDEUR_PHARMACIE = "vendeur_pharmacie", "Vendeur pharmacie"
    CAISSIER = "caissier", "Caissier"
    AGENT_ACCUEIL = "agent_accueil", "Agent d'accueil"
