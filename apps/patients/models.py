"""Modèles pour la gestion des dossiers patients et des rendez-vous médicaux."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from core.models import SoftDeleteModel
from utils.enums import AllergenCategoryEnum
from utils.enums import AllergyCriticalityEnum
from utils.enums import AllergyVerificationStatusEnum
from utils.enums import AppointmentStatusEnum
from utils.enums import BloodGroupEnum
from utils.enums import GenderEnum
from utils.phone import validate_phone_number


class Patient(SoftDeleteModel):
    """Dossier patient centralisé SantéGeste / CS² Health."""

    patient_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name=_("Matricule / Identifiant patient"),
        help_text=_("Numéro unique généré automatiquement au format PAT-YYYY-XXXX."),
    )
    first_name = models.CharField(
        max_length=150,
        verbose_name=_("Prénom(s)"),
    )
    last_name = models.CharField(
        max_length=150,
        verbose_name=_("Nom de famille"),
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date de naissance"),
    )
    gender = models.CharField(
        max_length=1,
        choices=GenderEnum.choices,
        default=GenderEnum.OTHER,
        verbose_name=_("Sexe / Genre"),
    )
    blood_group = models.CharField(
        max_length=10,
        choices=BloodGroupEnum.choices,
        default=BloodGroupEnum.UNKNOWN,
        verbose_name=_("Groupe sanguin"),
    )
    phone_number = models.CharField(
        max_length=20,
        db_index=True,
        validators=[validate_phone_number],
        verbose_name=_("Numéro de téléphone"),
    )
    email = models.EmailField(
        null=True,
        blank=True,
        verbose_name=_("Adresse email"),
    )
    address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Adresse de résidence"),
    )
    profession = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Profession"),
    )

    # Personne à contacter en cas d'urgence
    emergency_contact_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Nom du contact d'urgence"),
    )
    emergency_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[validate_phone_number],
        verbose_name=_("Téléphone du contact d'urgence"),
    )
    emergency_contact_relation = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Lien de parenté"),
    )

    # Données médicales critiques / alertes
    allergies = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Allergies connues"),
        help_text=_("Mentionner toutes les allergies médicamenteuses, alimentaires ou respiratoires."),
    )
    chronic_diseases = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Affections chroniques / Antécédents majeurs"),
        help_text=_("Ex: Diabète type 2, HTA, Asthme, Drépanocytose, etc."),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Dossier actif"),
    )

    class Meta(SoftDeleteModel.Meta):
        db_table = "patients"
        verbose_name = _("Patient")
        verbose_name_plural = _("Patients")
        ordering = ["-created_at"]
        indexes = [
            *SoftDeleteModel.Meta.indexes,
            models.Index(fields=["last_name", "first_name"], name="patient_name_idx"),
            models.Index(fields=["phone_number"], name="patient_phone_idx"),
            models.Index(fields=["patient_number"], name="patient_num_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.patient_number} - {self.full_name}"

    @property
    def full_name(self) -> str:
        """Retourne le nom complet formaté (NOM Prénom)."""
        return f"{self.last_name.upper()} {self.first_name.title()}".strip()

    @property
    def age(self) -> int | None:
        """Calcule l'âge révolu du patient."""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def has_critical_alerts(self) -> bool:
        """Vrai si le patient a des allergies ou pathologies chroniques signalées."""
        has_text_alerts = bool(
            (self.allergies and self.allergies.strip())
            or (self.chronic_diseases and self.chronic_diseases.strip())
        )
        return has_text_alerts or self.patient_allergies.exists()

    @property
    def critical_allergies(self):
        """Retourne le queryset des allergies à risque vital élevé."""
        return self.patient_allergies.filter(
            criticality=AllergyCriticalityEnum.HIGH
        ).select_related("allergen")

    def get_absolute_url(self) -> str:
        return reverse("patients:patient_detail", kwargs={"pk": self.pk})


class Allergen(BaseModel):
    """Référentiel des substances et molécules allergènes."""

    name = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
        verbose_name=_("Nom de la substance"),
    )
    category = models.CharField(
        max_length=30,
        choices=AllergenCategoryEnum.choices,
        default=AllergenCategoryEnum.MEDICATION,
        db_index=True,
        verbose_name=_("Catégorie"),
    )
    atc_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("Code ATC"),
        help_text=_("Code de classification anatomique, thérapeutique et chimique de l'OMS (ex: J01C)."),
    )
    cross_reactivity_group = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("Groupe de réactivité croisée"),
        help_text=_("Ex: Bêta-lactamines, Sulfamides, AINS."),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description / Précisions pharmacologiques"),
    )

    class Meta:
        db_table = "allergens"
        verbose_name = _("Allergène")
        verbose_name_plural = _("Allergènes")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="allergen_name_idx"),
            models.Index(fields=["atc_code"], name="allergen_atc_idx"),
            models.Index(fields=["category"], name="allergen_cat_idx"),
        ]

    def __str__(self) -> str:
        if self.atc_code:
            return f"{self.name} [{self.atc_code}]"
        return self.name


class PatientAllergy(BaseModel):
    """Allergie codifiée et documentée pour un patient."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="patient_allergies",
        verbose_name=_("Patient"),
    )
    allergen = models.ForeignKey(
        Allergen,
        on_delete=models.PROTECT,
        related_name="patient_allergies",
        verbose_name=_("Allergène / Substance"),
    )
    criticality = models.CharField(
        max_length=25,
        choices=AllergyCriticalityEnum.choices,
        default=AllergyCriticalityEnum.HIGH,
        db_index=True,
        verbose_name=_("Niveau de criticité"),
    )
    verification_status = models.CharField(
        max_length=25,
        choices=AllergyVerificationStatusEnum.choices,
        default=AllergyVerificationStatusEnum.CONFIRMED,
        verbose_name=_("Statut de vérification"),
    )
    reaction = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Manifestation clinique / Réaction"),
        help_text=_("Ex: Œdème de Quincke, Choc anaphylactique, Urticaire, Bronchospasme..."),
    )
    diagnosed_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date du diagnostic"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Observations médicales complémentaires"),
    )

    class Meta:
        db_table = "patient_allergies"
        verbose_name = _("Allergie patient")
        verbose_name_plural = _("Allergies patients")
        ordering = ["-criticality", "allergen__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "allergen"],
                name="unique_patient_allergen",
            ),
        ]
        indexes = [
            models.Index(fields=["patient", "criticality"], name="pat_allergy_crit_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.patient.full_name} - {self.allergen.name} ({self.get_criticality_display()})"

    @property
    def has_life_threatening_risk(self) -> bool:
        """Indique si l'allergie présente un danger vital immédiat (anaphylaxie)."""
        return self.criticality == AllergyCriticalityEnum.HIGH


class Appointment(SoftDeleteModel):
    """Rendez-vous médical planifié pour un patient auprès d'un praticien."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="appointments",
        verbose_name=_("Patient"),
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doctor_appointments",
        verbose_name=_("Médecin / Praticien"),
    )
    scheduled_at = models.DateTimeField(
        db_index=True,
        verbose_name=_("Date et heure du rendez-vous"),
    )
    estimated_duration_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Durée estimée (minutes)"),
    )
    reason = models.CharField(
        max_length=255,
        verbose_name=_("Motif de consultation"),
    )
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatusEnum.choices,
        default=AppointmentStatusEnum.SCHEDULED,
        db_index=True,
        verbose_name=_("Statut du rendez-vous"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes ou observations"),
    )

    class Meta(SoftDeleteModel.Meta):
        db_table = "appointments"
        verbose_name = _("Rendez-vous")
        verbose_name_plural = _("Rendez-vous")
        ordering = ["scheduled_at"]
        indexes = [
            *SoftDeleteModel.Meta.indexes,
            models.Index(fields=["doctor", "scheduled_at"], name="rdv_doctor_date_idx"),
            models.Index(fields=["status", "scheduled_at"], name="rdv_status_date_idx"),
        ]

    def __str__(self) -> str:
        date_str = timezone.localtime(self.scheduled_at).strftime("%d/%m/%Y %H:%M")
        return f"RDV: {self.patient.full_name} ({self.get_status_display()}) - {date_str}"

    @property
    def end_time(self) -> datetime:
        """Calcule l'heure prévisionnelle de fin de rendez-vous."""
        return self.scheduled_at + timedelta(minutes=self.estimated_duration_minutes)

    @property
    def is_past(self) -> bool:
        """Indique si le rendez-vous est déjà passé."""
        return timezone.now() > self.end_time

    @property
    def status_badge_class(self) -> str:
        """Classes Tailwind CSS pour le badge de statut CS² Health."""
        mapping = {
            AppointmentStatusEnum.SCHEDULED: "bg-blue-50 text-blue-700 border-blue-200 ring-blue-600/20",
            AppointmentStatusEnum.WAITING: "bg-amber-50 text-amber-700 border-amber-200 ring-amber-600/20",
            AppointmentStatusEnum.IN_CONSULTATION: "bg-purple-50 text-purple-700 border-purple-200 ring-purple-600/20",
            AppointmentStatusEnum.COMPLETED: "bg-emerald-50 text-emerald-700 border-emerald-200 ring-emerald-600/20",
            AppointmentStatusEnum.CANCELLED: "bg-rose-50 text-rose-700 border-rose-200 ring-rose-600/20",
            AppointmentStatusEnum.MISSED: "bg-neutral-100 text-neutral-600 border-neutral-200 ring-neutral-500/20",
        }
        return mapping.get(self.status, "bg-neutral-100 text-neutral-700 border-neutral-200")

