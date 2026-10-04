"""Modèles Vente (Sale) et Ligne de Vente (SaleItem)."""

from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from apps.patients.models import Facture, Ordonnance, Patient
from apps.pharmacy.models.batch import Batch
from apps.pharmacy.models.product import Product


class Sale(BaseModel):
    """Vente de produits pharmaceutiques (au comptoir ou sur ordonnance)."""

    STATUS_CHOICES = (
        ("DRAFT", _("Brouillon / En cours")),
        ("PENDING_PAYMENT", _("En attente de paiement à la caisse")),
        ("COMPLETED", _("Payée et finalisée")),
        ("CANCELLED", _("Annulée")),
    )

    sale_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Numéro de vente (ex: VTE-2026-0001)"),
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_sales",
        verbose_name=_("Patient (si identifié)"),
    )
    client_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Nom du client (si vente anonyme au comptoir)"),
    )
    ordonnance = models.ForeignKey(
        Ordonnance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_sales",
        verbose_name=_("Ordonnance médicale associée"),
    )
    facture = models.OneToOneField(
        Facture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_sale",
        verbose_name=_("Facture Caisse associée"),
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pharmacy_sales",
        verbose_name=_("Vendeur / Pharmacien"),
    )
    sale_date = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date et heure de la vente"),
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Sous-total (FCFA)"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Remise commerciale (FCFA)"),
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Total net à payer (FCFA)"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        verbose_name=_("Statut de la vente"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes / Instructions de délivrance"),
    )

    class Meta:
        db_table = "pharmacy_sales"
        verbose_name = _("Vente pharmacie")
        verbose_name_plural = _("Ventes pharmacie")
        ordering = ["-sale_date", "-created_at"]
        indexes = [
            models.Index(fields=["sale_number"], name="idx_sale_num"),
            models.Index(fields=["status", "-sale_date"], name="idx_sale_status_date"),
        ]

    def __str__(self) -> str:
        beneficiary = self.patient.full_name if self.patient else (self.client_name or _("Client comptoir"))
        return f"{self.sale_number} - {beneficiary} ({self.total_amount} FCFA - {self.get_status_display()})"


class SaleItem(BaseModel):
    """Ligne de produit au sein d'une vente en pharmacie."""

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Vente"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sale_items",
        verbose_name=_("Produit vendu"),
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sale_items",
        verbose_name=_("Lot prélevé (FEFO)"),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantité délivrée"),
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Prix unitaire (FCFA)"),
    )
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Sous-total ligne (FCFA)"),
    )

    class Meta:
        db_table = "pharmacy_sale_items"
        verbose_name = _("Ligne de vente pharmacie")
        verbose_name_plural = _("Lignes de vente pharmacie")

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product.name} ({self.total_price} FCFA)"

    def save(self, *args, **kwargs):
        if not self.unit_price and self.product_id:
            self.unit_price = self.product.selling_price
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)
