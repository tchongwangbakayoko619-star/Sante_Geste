"""Modèle Produit / Médicament."""

from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel
from apps.pharmacy.models.category import Category
from utils.validators import validate_image_file_size


class Product(SoftDeleteModel):
    """Fiche produit / médicament référencé à la pharmacie."""

    name = models.CharField(
        max_length=200,
        verbose_name=_("Dénomination commerciale"),
    )
    dci = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Principe actif / DCI"),
        help_text=_("Dénomination Commune Internationale (ex: Paracétamol, Amoxicilline)"),
    )
    dosage = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Dosage (ex: 500 mg, 1 g, 250 mg/5 ml)"),
    )
    form = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Forme pharmaceutique (ex: Comprimé, Sirop, Injectable)"),
    )
    reference_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Code référence / Code-barres"),
    )
    unit = models.CharField(
        max_length=50,
        default="Boîte",
        verbose_name=_("Unité de conditionnement (ex: Boîte, Flacon, Ampoule)"),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("Catégorie"),
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Prix d'achat unitaire standard (FCFA)"),
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Prix de vente au public (FCFA)"),
    )
    min_stock_threshold = models.PositiveIntegerField(
        default=10,
        verbose_name=_("Seuil d'alerte de stock minimum"),
    )
    current_stock = models.IntegerField(
        default=0,
        verbose_name=_("Quantité totale en stock"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Produit actif"),
    )
    image = models.ImageField(
        upload_to="pharmacy/products/",
        blank=True,
        null=True,
        validators=[validate_image_file_size],
        verbose_name=_("Photo / Image du médicament"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description / Remarques cliniques"),
    )

    class Meta:
        db_table = "pharmacy_products"
        verbose_name = _("Produit pharmaceutique")
        verbose_name_plural = _("Produits pharmaceutiques")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="idx_prod_name"),
            models.Index(fields=["dci"], name="idx_prod_dci"),
            models.Index(fields=["reference_code"], name="idx_prod_ref"),
        ]

    def __str__(self) -> str:
        details = f"{self.dosage} - {self.form}".strip(" -")
        return f"{self.name} ({details})" if details else self.name

    @property
    def is_in_stock(self) -> bool:
        return self.current_stock > 0

    @property
    def is_low_stock(self) -> bool:
        return self.current_stock <= self.min_stock_threshold
