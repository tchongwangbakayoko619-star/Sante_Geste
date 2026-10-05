"""Modèles Facture et Paiement (Caisse & Facturation)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models.consultation import Consultation
from apps.patients.models.patient import Patient
from core.models import BaseModel


class Facture(BaseModel):
    """Facture émise par la Caisse pour les prestations d'un patient."""

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Numéro de facture"),
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="factures",
        verbose_name=_("Patient"),
    )
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factures",
        verbose_name=_("Consultation associée"),
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Montant total (FCFA / EUR)"),
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Montant encaisse"),
    )
    STATUS_CHOICES = (
        ("UNPAID", _("Non payée")),
        ("PARTIALLY_PAID", _("Partiellement payée")),
        ("PAID", _("Payée")),
        ("CANCELLED", _("Annulée")),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="UNPAID",
        verbose_name=_("Statut de paiement"),
    )
    issued_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date d'émission"),
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="factures_emises",
        verbose_name=_("Caissier / Agent émetteur"),
    )

    class Meta:
        db_table = "factures"
        verbose_name = _("Facture")
        verbose_name_plural = _("Factures")
        ordering = ["-issued_at"]

    def __str__(self) -> str:
        return f"{self.invoice_number} - {self.patient.full_name} ({self.total_amount} FCFA - {self.get_status_display()})"

    @property
    def remaining_amount(self):
        return max(0, self.total_amount - self.paid_amount)


class Paiement(BaseModel):
    """Enregistrement d'un règlement financier perçu à la caisse."""

    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Numéro de reçu"),
    )
    facture = models.ForeignKey(
        Facture,
        on_delete=models.CASCADE,
        related_name="paiements",
        verbose_name=_("Facture associée"),
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="paiements_encaisses",
        verbose_name=_("Caissier"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Montant régle"),
    )
    PAYMENT_METHOD_CHOICES = (
        ("ESPECES", _("Espèces")),
        ("CARTE", _("Carte Bancaire")),
        ("MOBILE_MONEY", _("Mobile Money (Orange/MTN/Moov)")),
        ("VIREMENT", _("Virement / Chèque")),
    )

    payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        default="ESPECES",
        verbose_name=_("Mode de règlement"),
    )
    paid_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date de règlement"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes de caisse"),
    )

    class Meta:
        db_table = "paiements"
        verbose_name = _("Paiement / Règlement")
        verbose_name_plural = _("Paiements / Règlements")
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        num = self.receipt_number or "En cours"
        return f"Reçu {num} - {self.amount} FCFA par {self.get_payment_method_display()} (Facture {self.facture.invoice_number})"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            today_str = timezone.now().strftime("%Y%m%d")
            prefix = f"REC-{today_str}-"
            last_p = Paiement.objects.filter(receipt_number__startswith=prefix).order_by("-receipt_number").first()
            if last_p and last_p.receipt_number:
                try:
                    last_seq = int(last_p.receipt_number.split("-")[-1])
                    seq = last_seq + 1
                except ValueError:
                    seq = Paiement.objects.count() + 1
            else:
                seq = 1
            self.receipt_number = f"{prefix}{seq:04d}"

        super().save(*args, **kwargs)
        # Recalcule le montant payé et met à jour le statut de la facture
        facture = self.facture
        total_paid = sum(p.amount for p in facture.paiements.all())
        facture.paid_amount = total_paid
        if total_paid >= facture.total_amount:
            facture.status = "PAID"
            # Marquer les prestations associées comme payées
            facture.prestations_realisees.all().update(status="PAYE")
            if facture.consultation:
                facture.consultation.prestations.all().update(status="PAYE")
        elif total_paid > 0:
            facture.status = "PARTIALLY_PAID"
        else:
            facture.status = "UNPAID"
        facture.save(update_fields=["paid_amount", "status", "updated_at"])
