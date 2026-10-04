"""Modèle Fournisseur de produits pharmaceutiques."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel
from utils.phone import validate_phone_number


class Supplier(SoftDeleteModel):
    """Fournisseur ou laboratoire pharmaceutique partenaire."""

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_("Raison sociale / Nom du fournisseur"),
    )
    contact_person = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Personne de contact"),
    )
    telephone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        validators=[validate_phone_number],
        verbose_name=_("Téléphone"),
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Adresse email"),
    )
    address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Adresse géographique"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Fournisseur actif"),
    )

    class Meta:
        db_table = "pharmacy_suppliers"
        verbose_name = _("Fournisseur pharmaceutique")
        verbose_name_plural = _("Fournisseurs pharmaceutiques")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
