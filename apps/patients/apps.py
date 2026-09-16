"""Configuration de l'application patients et rendez-vous."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PatientsConfig(AppConfig):
    """Configuration Django pour le module patients."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patients"
    verbose_name = _("Patients & Rendez-vous")
