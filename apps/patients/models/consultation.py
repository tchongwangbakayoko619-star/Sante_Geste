"""Modèle Consultation médicale."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models.appointment import Appointment
from apps.patients.models.patient import Patient
from core.models import SoftDeleteModel
from utils.enums import AppointmentStatusEnum


class Consultation(SoftDeleteModel):
    """Consultation médicale réalisée par un praticien pour un patient."""

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultation",
        verbose_name=_("Rendez-vous associé"),
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="consultations",
        verbose_name=_("Patient"),
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        limit_choices_to={"is_personnel_medical": True},
        related_name="doctor_consultations",
        verbose_name=_("Médecin / Praticien"),
    )
    consultation_date = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name=_("Date et heure de la consultation"),
    )
    reason = models.CharField(
        max_length=255,
        verbose_name=_("Motif de la consultation"),
    )
    symptoms = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Symptômes et observations cliniques"),
    )
    vital_signs = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Constantes vitales (Tension, Poids, Température, Pouls)"),
        help_text=_("Ex: {'tension': '12/8', 'poids': 70, 'temperature': 37.2, 'pouls': 75}"),
    )
    diagnosis = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Diagnostic médical"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes confidentielles / Recommandations"),
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("IN_PROGRESS", _("En cours")),
            ("COMPLETED", _("Terminée")),
        ],
        default="COMPLETED",
        verbose_name=_("Statut de la consultation"),
    )

    class Meta:
        db_table = "consultations"
        verbose_name = _("Consultation médicale")
        verbose_name_plural = _("Consultations médicales")
        ordering = ["-consultation_date"]
        indexes = [
            models.Index(fields=["is_deleted", "-created_at"], name="consult_del_created_idx"),
            models.Index(fields=["doctor", "-consultation_date"], name="consult_doc_date_idx"),
            models.Index(fields=["patient", "-consultation_date"], name="consult_pat_date_idx"),
        ]

    def __str__(self) -> str:
        date_str = timezone.localtime(self.consultation_date).strftime("%d/%m/%Y %H:%M")
        return f"Consultation: {self.patient.full_name} par Dr. {self.doctor.full_name} ({date_str})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Met à jour le statut du rendez-vous lié si présent
        if self.appointment and self.appointment.status != AppointmentStatusEnum.COMPLETED:
            self.appointment.status = AppointmentStatusEnum.COMPLETED
            self.appointment.save(update_fields=["status", "updated_at"])
