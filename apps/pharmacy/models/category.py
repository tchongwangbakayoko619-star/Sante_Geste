"""Modèle Catégorie de produits pharmaceutiques."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel


class Category(SoftDeleteModel):
    """Catégorie de classification des médicaments et consommables (ex: Antibiotique, Antipaludique)."""

    name = models.CharField(
        max_length=120,
        unique=True,
        verbose_name=_("Nom de la catégorie"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description"),
    )

    class Meta:
        db_table = "pharmacy_categories"
        verbose_name = _("Catégorie pharmaceutique")
        verbose_name_plural = _("Catégories pharmaceutiques")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
