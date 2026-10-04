"""Modèle Rendez-vous médical."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models.patient import Patient
from core.models import SoftDeleteModel
from utils.enums import AppointmentStatusEnum
from utils.enums import PatientStatusEnum


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
