"""Modèle Lot de médicament (Batch)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from apps.pharmacy.models.product import Product
from apps.pharmacy.models.supplier import Supplier


class Batch(BaseModel):
    """Lot d'un produit pharmaceutique avec suivi de date de péremption (FEFO)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name=_("Produit"),
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
        verbose_name=_("Fournisseur"),
    )
    batch_number = models.CharField(
        max_length=100,
        verbose_name=_("Numéro de lot"),
    )
    expiry_date = models.DateField(
        verbose_name=_("Date de péremption"),
    )
    initial_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Quantité initiale reçue"),
    )
    current_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Quantité restante en stock"),
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Prix d'achat unitaire pour ce lot"),
    )
    entry_date = models.DateField(
        default=timezone.now,
        verbose_name=_("Date d'entrée en stock"),
    )
    STATUS_CHOICES = (
        ("ACTIVE", _("Actif en stock")),
        ("DEPLETED", _("Épuisé")),
        ("EXPIRED", _("Périmé")),
        ("QUARANTINE", _("En quarantaine / Bloqué")),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
        verbose_name=_("Statut du lot"),
    )

    class Meta:
        db_table = "pharmacy_batches"
        verbose_name = _("Lot pharmaceutique")
        verbose_name_plural = _("Lots pharmaceutiques")
        ordering = ["expiry_date", "entry_date"]
        indexes = [
            models.Index(fields=["product", "status", "expiry_date"], name="idx_batch_fefo"),
            models.Index(fields=["batch_number"], name="idx_batch_num"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - Lot {self.batch_number} (Exp: {self.expiry_date.strftime('%d/%m/%Y')})"

    @property
    def is_expired(self) -> bool:
        return self.expiry_date < date.today()

    @property
    def days_until_expiry(self) -> int:
        return (self.expiry_date - date.today()).days
