"""Modèles Prestation et PrestationRealisee."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.patients.models.consultation import Consultation
from apps.patients.models.patient import Patient
from core.models import BaseModel


class Prestation(BaseModel):
    """Catalogue officiel des actes et prestations médicales de l'établissement."""

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name=_("Nom de la prestation"),
    )
    code = models.CharField(
        max_length=30,
        unique=True,
        verbose_name=_("Code acte / Tarifaire"),
    )
    category = models.CharField(
        max_length=50,
        default="CONSULTATION",
        verbose_name=_("Catégorie d'acte"),
    )
    standard_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Tarif standard (FCFA / EUR)"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Prestation active"),
    )

    class Meta:
        db_table = "prestations"
        verbose_name = _("Prestation médicale")
        verbose_name_plural = _("Prestations médicales")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name} ({self.standard_price})"


class PrestationRealisee(BaseModel):
    """Acte ou prestation médicale réalisée pour un patient, transmise à la caisse."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="prestations_realisees",
        verbose_name=_("Patient"),
    )
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestations",
        verbose_name=_("Consultation associée"),
    )
    prestation = models.ForeignKey(
        Prestation,
        on_delete=models.PROTECT,
        related_name="realisations",
        verbose_name=_("Prestation"),
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prestations_prescrites",
        verbose_name=_("Praticien prescripteur / exécutant"),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantité"),
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Prix unitaire"),
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Prix total"),
    )
    status = models.CharField(
        max_length=25,
        choices=[
            ("EN_ATTENTE_CAISSE", _("En attente de facturation")),
            ("FACTURE", _("Facturé")),
            ("PAYE", _("Payé")),
        ],
        default="EN_ATTENTE_CAISSE",
        verbose_name=_("Statut d'encaissement"),
    )

    class Meta:
        db_table = "prestations_realisees"
        verbose_name = _("Prestation réalisée")
        verbose_name_plural = _("Prestations réalisées")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.prestation.name} x{self.quantity} - {self.patient.full_name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.unit_price and self.prestation_id:
            self.unit_price = self.prestation.standard_price
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)
