"""Modèle Mouvement de stock (StockMovement)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from apps.pharmacy.models.batch import Batch
from apps.pharmacy.models.product import Product


class StockMovement(BaseModel):
    """Mouvement de stock inaltérable traçant toute entrée, sortie ou ajustement."""

    MOVEMENT_TYPES = (
        ("IN_PURCHASE", _("Entrée / Réception fournisseur")),
        ("OUT_SALE", _("Sortie / Vente au comptoir")),
        ("OUT_DISPENSE", _("Sortie / Délivrance ordonnance")),
        ("POS_ADJUST", _("Ajustement d'inventaire positif")),
        ("NEG_ADJUST", _("Ajustement d'inventaire négatif")),
        ("EXPIRED", _("Mise au rebut pour péremption")),
        ("RETURN", _("Retour / Annulation de vente")),
        ("LOSS", _("Perte ou casse")),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name=_("Produit concerné"),
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name=_("Lot associé"),
    )
    movement_type = models.CharField(
        max_length=25,
        choices=MOVEMENT_TYPES,
        verbose_name=_("Type de mouvement"),
    )
    quantity = models.IntegerField(
        verbose_name=_("Quantité mouvementée"),
        help_text=_("Positive pour entrée, négative pour sortie"),
    )
    previous_stock = models.IntegerField(
        verbose_name=_("Stock avant opération"),
    )
    new_stock = models.IntegerField(
        verbose_name=_("Stock après opération"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pharmacy_movements",
        verbose_name=_("Opérateur responsable"),
    )
    movement_date = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date et heure du mouvement"),
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Référence opération (ex: N° Vente, N° Réception)"),
    )
    reason = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Motif / Justification du mouvement"),
    )

    class Meta:
        db_table = "pharmacy_stock_movements"
        verbose_name = _("Mouvement de stock")
        verbose_name_plural = _("Mouvements de stock")
        ordering = ["-movement_date", "-created_at"]
        indexes = [
            models.Index(fields=["product", "-movement_date"], name="idx_mov_prod_date"),
            models.Index(fields=["movement_type"], name="idx_mov_type"),
        ]

    def __str__(self) -> str:
        return f"{self.get_movement_type_display()} : {self.quantity} x {self.product.name} par {self.user.full_name}"
