"""Modèles pour la gestion des dossiers patients et des rendez-vous médicaux."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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
from utils.enums import PatientStatusEnum
from utils.phone import normalize_phone_number
from utils.phone import validate_phone_number


class Patient(SoftDeleteModel):
    """Dossier patient centralisé SantéGeste / CS² Health."""

    patient_number = models.CharField(
        max_length=32,
        unique=True,
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
    # Note d'architecture sur la dualité de gestion des allergies :
    # ------------------------------------------------------------
    # 1. `allergies` (texte libre ci-dessous) : Utilisé pour la saisie déclarative rapide
    #    à l'admission administrative (Agent d'accueil). Rôle purement informatif sans qualification pharmacologique.
    # 2. `PatientAllergy` (modèle relationnel ci-après) : Renseigné exclusivement par le personnel médical
    #    pour codifier les substances (OMS / ATC), évaluer la criticité FHIR et alimenter le CDSS
    #    (Clinical Decision Support System) afin de bloquer automatiquement les prescriptions contre-indiquées.
    allergies = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Allergies connues (déclaration libre)"),
        help_text=_(
            "Saisie déclarative initiale lors de l'admission administrative (Agent d'accueil). "
            "Rôle informatif rapide, complété par les allergies codifiées (PatientAllergy) "
            "renseignées par le personnel médical pour la sécurisation active des prescriptions."
        ),
    )
    chronic_diseases = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Affections chroniques / Antécédents majeurs"),
        help_text=_("Ex: Diabète type 2, HTA, Asthme, Drépanocytose, etc."),
    )

    status = models.CharField(
        max_length=20,
        choices=PatientStatusEnum.choices,
        default=PatientStatusEnum.ACTIVE,
        blank=True,
        verbose_name=_("Statut du dossier"),
        help_text=_("Cycle de vie clinique et administratif du dossier patient (aligné FHIR/HL7)."),
    )
    deceased_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date et heure du décès"),
        help_text=_("Renseigné obligatoirement si le patient est déclaré décédé."),
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
            models.Index(fields=["status"], name="patient_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.patient_number} - {self.full_name}"

    def clean(self) -> None:
        """Validation du statut vital (identitovigilance) et normalisation téléphonique E.164."""
        super().clean()
        if not self.status:
            self.status = PatientStatusEnum.ACTIVE
        if self.status == PatientStatusEnum.DECEASED and not self.deceased_at:
            self.deceased_at = timezone.now()
        elif self.status != PatientStatusEnum.DECEASED and self.deceased_at:
            self.deceased_at = None

        # Normalisation et validation automatique au format international standard E.164
        phone_errors = {}
        if self.phone_number:
            try:
                self.phone_number = normalize_phone_number(self.phone_number)
            except ValidationError as exc:
                phone_errors["phone_number"] = exc

        if self.emergency_contact_phone:
            try:
                self.emergency_contact_phone = normalize_phone_number(self.emergency_contact_phone)
            except ValidationError as exc:
                phone_errors["emergency_contact_phone"] = exc

        if phone_errors:
            raise ValidationError(phone_errors)

    def save(self, *args, **kwargs):
        if not self.patient_number:
            from apps.patients.services.patient_service import generate_patient_number

            self.patient_number = generate_patient_number()
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        """Indique si le dossier est actif pour les soins et rendez-vous courants.

        Rétrocompatibilité : Vrai ssi le dossier n'est pas soft-deleted et a le statut ACTIVE.
        """
        return not self.is_deleted and self.status == PatientStatusEnum.ACTIVE

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
        """Indique si le dossier présente des alertes médicales critiques.

        Consolide la dualité de gestion des allergies :
        - Déclarative (texte libre) : saisie informelle dans `allergies` ou `chronic_diseases`.
        - Structurée (relationnelle) : présence d'au moins une allergie codifiée dans `patient_allergies`.
        """
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
        verbose_name=_("Nom de la substance"),
    )
    category = models.CharField(
        max_length=30,
        choices=AllergenCategoryEnum.choices,
        default=AllergenCategoryEnum.MEDICATION,
        verbose_name=_("Catégorie"),
    )
    atc_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Code ATC"),
        help_text=_("Code de classification anatomique, thérapeutique et chimique de l'OMS (ex: J01C)."),
    )
    cross_reactivity_group = models.CharField(
        max_length=100,
        blank=True,
        default="",
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
            models.Index(fields=["atc_code"], name="allergen_atc_idx"),
            models.Index(fields=["category"], name="allergen_cat_idx"),
            models.Index(fields=["cross_reactivity_group"], name="allergen_cross_idx"),
        ]

    def __str__(self) -> str:
        if self.atc_code:
            return f"{self.name} [{self.atc_code}]"
        return self.name


class PatientAllergy(BaseModel):
    """Allergie codifiée et documentée pour un patient (Sécurisation des prescriptions).

    Architecture clinique à deux niveaux (Dualité) :
    -------------------------------------------------
    1. Niveau 1 (Admission administrative - Agent d'accueil) :
       `Patient.allergies` est un champ texte libre permettant de consigner instantanément
       les déclarations du patient sans barrière lexicale ni formation pharmacologique.
       Rôle purement informatif et d'alerte visuelle.

    2. Niveau 2 (Prescription sécurisée & CDSS - Personnel médical) :
       `PatientAllergy` est le modèle relationnel strict liant le patient à un `Allergen`.
       Chaque substance dispose d'une codification OMS/ATC (`atc_code`), d'une famille de réactivité
       croisée (`cross_reactivity_group`), d'un niveau de criticité FHIR (`criticality`) et d'un
       statut de vérification clinique (`verification_status`).
       C'est ce modèle qui alimente le moteur d'aide à la décision clinique (CDSS)
       via `check_allergy_contraindication()` pour sécuriser et bloquer les prescriptions à risque.
    """

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
        limit_choices_to={"is_personnel_medical": True},
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

    def clean(self) -> None:
        """Vérifie l'éligibilité du patient et l'absence de conflit d'agenda pour le médecin."""
        super().clean()

        # Contrôle du cycle de vie du patient (identitovigilance)
        if self.patient_id:
            pat = getattr(self, "patient", None) or Patient.all_objects.filter(pk=self.patient_id).first()
            if pat:
                if pat.status == PatientStatusEnum.DECEASED:
                    raise ValidationError(
                        {"patient": _("Impossible de planifier un rendez-vous pour un patient déclaré décédé.")}
                    )
                if pat.status in (PatientStatusEnum.ARCHIVED, PatientStatusEnum.SUSPENDED):
                    raise ValidationError(
                        {
                            "patient": _(
                                "Le dossier de ce patient est %(status)s. Veuillez réactiver le dossier avant de programmer un rendez-vous."
                            )
                            % {"status": pat.get_status_display().lower()}
                        }
                    )

        # Contrôle du praticien (habilitation médicale et statut actif au sein de l'établissement)
        if self.doctor_id:
            user_model = get_user_model()
            doc = getattr(self, "doctor", None) or user_model.objects.filter(pk=self.doctor_id).first()
            if doc:
                if not doc.is_personnel_medical:
                    raise ValidationError(
                        {
                            "doctor": _(
                                "L'utilisateur assigné n'est pas habilité comme personnel médical."
                            )
                        }
                    )
                if not doc.is_active:
                    is_new = not self.pk
                    doctor_changed = False
                    if not is_new:
                        old_doc_id = (
                            Appointment.objects.filter(pk=self.pk)
                            .values_list("doctor_id", flat=True)
                            .first()
                        )
                        doctor_changed = old_doc_id != self.doctor_id
                    if is_new or doctor_changed:
                        raise ValidationError(
                            {
                                "doctor": _(
                                    "Ce praticien n'est plus en activité au sein de l'établissement. "
                                    "Impossible de lui assigner un rendez-vous."
                                )
                            }
                        )

        if not self.doctor_id or not self.scheduled_at:
            return

        # Les rendez-vous annulés ne bloquent pas le créneau
        if self.status == AppointmentStatusEnum.CANCELLED:
            return

        from apps.patients.services.appointment_service import find_conflicting_appointment

        conflict = find_conflicting_appointment(
            doctor=self.doctor_id,
            scheduled_at=self.scheduled_at,
            duration_minutes=self.estimated_duration_minutes or 30,
            exclude_appointment_id=self.pk,
        )
        if conflict:
            doctor_display = ""
            if hasattr(self, "doctor") and self.doctor:
                doctor_display = self.doctor.full_name or self.doctor.email
            raise ValidationError(
                {
                    "scheduled_at": _(
                        "Conflit d'agenda : Le praticien %(doctor)s a déjà une consultation "
                        "programmée sur ce créneau (de %(start)s à %(end)s)."
                    )
                    % {
                        "doctor": f"Dr. {doctor_display}" if doctor_display else "",
                        "start": timezone.localtime(conflict.scheduled_at).strftime("%H:%M"),
                        "end": timezone.localtime(conflict.end_time).strftime("%H:%M"),
                    }
                }
            )

    def save(self, *args, **kwargs):
        """Valide la cohérence des créneaux avant enregistrement avec verrouillage pessimiste anti-concurrence."""
        from django.db import transaction

        update_fields = kwargs.get("update_fields")
        requires_schedule_validation = (
            update_fields is None
            or "scheduled_at" in update_fields
            or "doctor" in update_fields
            or "patient" in update_fields
            or "estimated_duration_minutes" in update_fields
            or "status" in update_fields
        )
        if requires_schedule_validation and self.doctor_id:
            user_model = get_user_model()
            with transaction.atomic():
                user_model.objects.select_for_update().filter(pk=self.doctor_id).first()
                self.clean()
                return super().save(*args, **kwargs)

        self.clean()
        return super().save(*args, **kwargs)


