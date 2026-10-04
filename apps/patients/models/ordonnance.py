"""Modèles Ordonnance et LigneOrdonnance."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models.consultation import Consultation
from apps.patients.models.patient import Patient
from core.models import BaseModel


class Ordonnance(BaseModel):
    """Ordonnance médicale délivrée par un praticien pour un patient."""

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordonnances",
        verbose_name=_("Consultation associée"),
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="ordonnances",
        verbose_name=_("Patient"),
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ordonnances_delivrees",
        verbose_name=_("Médecin prescripteur"),
    )
    prescribed_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date de prescription"),
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", _("En attente de délivrance")),
            ("DELIVERED", _("Délivrée")),
            ("CANCELLED", _("Annulée")),
        ],
        default="PENDING",
        verbose_name=_("Statut de délivrance"),
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de délivrance"),
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions_delivrees",
        verbose_name=_("Pharmacien / Agent de délivrance"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Recommandations / Instructions générales"),
    )

    class Meta:
        db_table = "ordonnances"
        verbose_name = _("Ordonnance médicale")
        verbose_name_plural = _("Ordonnances médicales")
        ordering = ["-prescribed_at"]

    def __str__(self) -> str:
        date_str = timezone.localtime(self.prescribed_at).strftime("%d/%m/%Y")
        return f"Ordonnance du {date_str} - {self.patient.full_name} (Dr. {self.doctor.full_name})"


class LigneOrdonnance(BaseModel):
    """Ligne de prescription médicamenteuse figurant sur une ordonnance."""

    ordonnance = models.ForeignKey(
        Ordonnance,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Ordonnance"),
    )
    medication_name = models.CharField(
        max_length=200,
        verbose_name=_("Nom du médicament / Substance"),
    )
    posology = models.CharField(
        max_length=200,
        verbose_name=_("Posologie (ex: 1 cp 3x/jour)"),
    )
    duration = models.CharField(
        max_length=100,
        verbose_name=_("Durée du traitement (ex: 7 jours)"),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantité / Boîtes"),
    )

    class Meta:
        db_table = "lignes_ordonnance"
        verbose_name = _("Ligne d'ordonnance")
        verbose_name_plural = _("Lignes d'ordonnance")

    def __str__(self) -> str:
        return f"{self.medication_name} - {self.posology} ({self.duration})"
