"""Modèles Utilisateur, Profil Médical et OTP pour SantéGeste."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.managers import UserManager
from core.models import BaseModel
from utils.constants.otp import OTP_MAX_ATTEMPTS
from utils.enums import OTPPurposeEnum
from utils.phone import validate_phone_number

if TYPE_CHECKING:
    from django.db.models import QuerySet


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Modèle Utilisateur personnalisé avec authentification par email et rôles applicatifs."""

    # -------------------------------------------------------------------------
    # Authentification par Email (unique=True crée automatiquement un index B-Tree)
    # -------------------------------------------------------------------------
    email = models.EmailField(
        unique=True,
        verbose_name=_("Adresse email"),
    )
    first_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Prénom"),
    )
    last_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Nom"),
    )

    # -------------------------------------------------------------------------
    # Coordonnées
    # -------------------------------------------------------------------------
    telephone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[validate_phone_number],
        verbose_name=_("Téléphone"),
    )

    # -------------------------------------------------------------------------
    # État du compte et sécurité
    # -------------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Actif"),
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name=_("Membre du personnel"),
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name=_("Email vérifié"),
    )

    # -------------------------------------------------------------------------
    # Drapeaux de rôles applicatifs (RBAC)
    # -------------------------------------------------------------------------
    is_proprietaire = models.BooleanField(
        default=False,
        verbose_name=_("Propriétaire"),
    )
    is_responsable_pharmacie = models.BooleanField(
        default=False,
        verbose_name=_("Responsable pharmacie"),
    )
    is_vendeur_pharmacie = models.BooleanField(
        default=False,
        verbose_name=_("Vendeur pharmacie"),
    )
    is_caissier = models.BooleanField(
        default=False,
        verbose_name=_("Caissier"),
    )
    is_agent_accueil = models.BooleanField(
        default=False,
        verbose_name=_("Agent d'accueil"),
    )
    is_personnel_medical = models.BooleanField(
        default=False,
        verbose_name=_("Personnel médical"),
    )

    objects: UserManager = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        verbose_name = _("Utilisateur")
        verbose_name_plural = _("Utilisateurs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        """Retourne le nom complet ou l'email par défaut."""
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.email

    @property
    def active_roles(self) -> list[str]:
        """Retourne la liste des rôles actifs attribués à cet utilisateur."""
        roles_map = [
            ("proprietaire", self.is_proprietaire),
            ("responsable_pharmacie", self.is_responsable_pharmacie),
            ("vendeur_pharmacie", self.is_vendeur_pharmacie),
            ("caissier", self.is_caissier),
            ("agent_accueil", self.is_agent_accueil),
            ("personnel_medical", self.is_personnel_medical),
        ]
        return [role for role, active in roles_map if active]


class MedicalProfile(BaseModel):
    """Profil spécifique réservé aux membres du personnel médical."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medical_profile",
        verbose_name=_("Utilisateur"),
    )
    specialite = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Spécialité"),
    )
    numero_ordre = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Numéro d'ordre professionnel"),
    )

    class Meta:
        db_table = "medical_profiles"
        verbose_name = _("Profil médical")
        verbose_name_plural = _("Profils médicaux")
        constraints = [
            models.UniqueConstraint(
                fields=["numero_ordre"],
                condition=~models.Q(numero_ordre=""),
                name="unique_numero_ordre_non_empty",
            ),
        ]

    def __str__(self) -> str:
        return f"Profil médical de {self.user.email}"

    def clean(self) -> None:
        """Validation défensive inter-modèle : garantit que l'utilisateur est bien du personnel médical."""
        super().clean()
        if self.user_id and not self.user.is_personnel_medical:
            msg = _("Un profil médical ne peut être rattaché qu'à un utilisateur ayant le rôle personnel médical.")
            raise ValidationError(msg)


class OTP(BaseModel):
    """Code temporaire à usage unique pour les opérations d’authentification."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="otps",
        verbose_name=_("Utilisateur"),
    )

    code_hash = models.CharField(
        max_length=128,
        verbose_name=_("Hash du code OTP"),
    )

    purpose = models.CharField(
        max_length=30,
        choices=OTPPurposeEnum.choices,
        verbose_name=_("Objectif"),
    )

    expires_at = models.DateTimeField(
        verbose_name=_("Date d'expiration"),
    )

    is_used = models.BooleanField(
        default=False,
        verbose_name=_("Déjà utilisé"),
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date d'utilisation"),
    )

    attempts = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Nombre de tentatives"),
    )

    class Meta:
        db_table = "otps"
        verbose_name = _("Code OTP")
        verbose_name_plural = _("Codes OTP")
        indexes = [
            models.Index(
                fields=["user", "purpose", "is_used", "-created_at"],
                name="otps_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"OTP {self.user.email} - {self.purpose}"

    def is_expired(self) -> bool:
        """Vérifie si le code OTP a expiré."""
        return timezone.now() >= self.expires_at

    def is_valid(self) -> bool:
        """Vérifie si l'OTP peut encore être utilisé."""
        return (
            not self.is_used
            and not self.is_expired()
            and self.attempts < OTP_MAX_ATTEMPTS
        )

    def verify_code(self, raw_code: str) -> bool:
        """Vérifie cryptographiquement le code brut soumis par rapport au hachage stocké."""
        from utils.otp import verify_otp_code
        return verify_otp_code(raw_code, self.code_hash)

    def mark_as_used(self) -> None:
        """Marque l'OTP comme consommé et enregistre la date d'utilisation."""
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at", "updated_at"])

    def increment_attempts(self) -> None:
        """Incrémente le compteur de tentatives infructueuses."""
        self.attempts += 1
        self.save(update_fields=["attempts", "updated_at"])
