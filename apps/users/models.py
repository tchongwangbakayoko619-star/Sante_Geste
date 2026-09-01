"""User, MedicalProfile, and OTP models for SanteGeste."""

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.users.managers import UserManager
from core.models import BaseModel
from core.models import TimeStampedModel
from utils.enums import OTPPurposeEnum
from utils.validators import validate_phone_number


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Custom User model for SanteGeste with role-based flags and email authentication."""

    # Authentification
    email = models.EmailField(unique=True, verbose_name="Adresse email")
    username = models.CharField(max_length=150, unique=True, verbose_name="Nom d'utilisateur")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Prénom")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Nom")

    # Champs Django standards
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    is_staff = models.BooleanField(default=False, verbose_name="Membre du personnel")
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name="Date d'inscription")


    # Champs spécifiques SantéGeste
    telephone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[validate_phone_number],
        verbose_name="Téléphone",
    )


    # Vérification par email (OTP)
    is_verified = models.BooleanField(default=False, verbose_name="Email vérifié")

    # Rôles (BooleanField, cumulables)
    is_proprietaire = models.BooleanField(default=False, verbose_name="Propriétaire")
    is_responsable_pharmacie = models.BooleanField(default=False, verbose_name="Responsable pharmacie")
    is_vendeur_pharmacie = models.BooleanField(default=False, verbose_name="Vendeur pharmacie")
    is_caissier = models.BooleanField(default=False, verbose_name="Caissier")
    is_agent_accueil = models.BooleanField(default=False, verbose_name="Agent d'accueil")
    is_personnel_medical = models.BooleanField(default=False, verbose_name="Personnel médical")

    objects: UserManager = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self) -> str:
        return self.email


class MedicalProfile(TimeStampedModel):
    """Profil spécifique réservé aux membres du personnel médical."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="medical_profile",
        verbose_name="Utilisateur",
    )
    specialite = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Spécialité",
    )
    numero_ordre = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Numéro d'ordre de médecin/infirmier",
    )

    class Meta:
        db_table = "medical_profiles"
        verbose_name = "Profil médical"
        verbose_name_plural = "Profils médicaux"

    def __str__(self) -> str:
        return f"Profil médical de {self.user.email}"


class OTP(TimeStampedModel):
    """One-Time Password model for email verification and password reset."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="otps",
        verbose_name="Utilisateur",
    )
    code_hash = models.CharField(max_length=128, verbose_name="Hash du code OTP")
    purpose = models.CharField(max_length=20, choices=OTPPurposeEnum.choices, verbose_name="Objectif")
    expires_at = models.DateTimeField(verbose_name="Date d'expiration")
    is_used = models.BooleanField(default=False, verbose_name="Déjà utilisé")
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Nombre de tentatives")

    class Meta:
        db_table = "otps"
        verbose_name = "Code OTP"
        verbose_name_plural = "Codes OTP"
        indexes = [
            models.Index(fields=["user", "purpose", "is_used"]),
        ]

    def is_expired(self) -> bool:
        """Check if the OTP code has expired."""
        return timezone.now() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if the OTP is active, unexpired, and under attempt threshold."""
        return not self.is_used and not self.is_expired() and self.attempts < 5
