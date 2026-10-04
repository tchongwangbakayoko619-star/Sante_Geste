"""Configuration de l'application Pharmacie pour SantéGeste."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PharmacyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pharmacy"
    verbose_name = _("Pharmacie & Gestion des Stocks")
