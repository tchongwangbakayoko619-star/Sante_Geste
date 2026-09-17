"""Couche de présentation (Presenters & View Models) pour le module patients.

Sépare strictement la logique métier du domaine des classes CSS et tokens graphiques
(Tailwind CSS) du design system CS² Health.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.enums import AppointmentStatusEnum
from utils.enums import PatientStatusEnum

if TYPE_CHECKING:
    from apps.patients.models import Appointment
    from apps.patients.models import Patient


# -----------------------------------------------------------------------------
# Dictionnaires de tokens de style UI (Design System CS² Health)
# -----------------------------------------------------------------------------

APPOINTMENT_STATUS_BADGE_CLASSES: dict[str, str] = {
    AppointmentStatusEnum.SCHEDULED: "bg-blue-50 text-blue-700 border-blue-200 ring-blue-600/20",
    AppointmentStatusEnum.WAITING: "bg-amber-50 text-amber-700 border-amber-200 ring-amber-600/20",
    AppointmentStatusEnum.IN_CONSULTATION: "bg-purple-50 text-purple-700 border-purple-200 ring-purple-600/20",
    AppointmentStatusEnum.COMPLETED: "bg-emerald-50 text-emerald-700 border-emerald-200 ring-emerald-600/20",
    AppointmentStatusEnum.CANCELLED: "bg-rose-50 text-rose-700 border-rose-200 ring-rose-600/20",
    AppointmentStatusEnum.MISSED: "bg-neutral-100 text-neutral-600 border-neutral-200 ring-neutral-500/20",
}

PATIENT_STATUS_BADGE_CLASSES: dict[str, str] = {
    PatientStatusEnum.ACTIVE: "bg-emerald-50 text-emerald-700 border-emerald-200 ring-emerald-600/20",
    PatientStatusEnum.ARCHIVED: "bg-neutral-100 text-neutral-600 border-neutral-200 ring-neutral-500/20",
    PatientStatusEnum.DECEASED: "bg-rose-50 text-rose-700 border-rose-200 ring-rose-600/20",
    PatientStatusEnum.TRANSFERRED: "bg-amber-50 text-amber-700 border-amber-200 ring-amber-600/20",
    PatientStatusEnum.SUSPENDED: "bg-purple-50 text-purple-700 border-purple-200 ring-purple-600/20",
}

PATIENT_STATUS_DOT_CLASSES: dict[str, str] = {
    PatientStatusEnum.ACTIVE: "bg-emerald-500",
    PatientStatusEnum.ARCHIVED: "bg-neutral-400",
    PatientStatusEnum.DECEASED: "bg-rose-500",
    PatientStatusEnum.TRANSFERRED: "bg-amber-500",
    PatientStatusEnum.SUSPENDED: "bg-purple-500",
}


# -----------------------------------------------------------------------------
# Fonctions utilitaires d'accès aux tokens UI
# -----------------------------------------------------------------------------

def get_appointment_status_badge_class(status: str | None) -> str:
    """Retourne les classes Tailwind CSS du badge pour un statut de rendez-vous."""
    if not status:
        return "bg-neutral-100 text-neutral-700 border-neutral-200"
    return APPOINTMENT_STATUS_BADGE_CLASSES.get(
        status, "bg-neutral-100 text-neutral-700 border-neutral-200"
    )


def get_patient_status_badge_class(status: str | None) -> str:
    """Retourne les classes Tailwind CSS du badge pour un statut de dossier patient."""
    if not status:
        return "bg-neutral-100 text-neutral-700 border-neutral-200"
    return PATIENT_STATUS_BADGE_CLASSES.get(
        status, "bg-neutral-100 text-neutral-700 border-neutral-200"
    )


def get_patient_status_dot_class(status: str | None) -> str:
    """Retourne la classe Tailwind CSS de la pastille indicatrice pour le statut patient."""
    if not status:
        return "bg-neutral-400"
    return PATIENT_STATUS_DOT_CLASSES.get(status, "bg-neutral-400")


# -----------------------------------------------------------------------------
# Classes Presenters dédiées (Design Pattern Presenter / View Model)
# -----------------------------------------------------------------------------

class AppointmentPresenter:
    """Presenter dédié à l'affichage et au rendu d'un rendez-vous médical."""

    def __init__(self, appointment: Appointment) -> None:
        self.appointment = appointment

    @property
    def status_badge_class(self) -> str:
        """Classes Tailwind CSS du badge de statut."""
        return get_appointment_status_badge_class(self.appointment.status)


class PatientPresenter:
    """Presenter dédié à l'affichage et au rendu d'un dossier patient."""

    def __init__(self, patient: Patient) -> None:
        self.patient = patient

    @property
    def status_badge_class(self) -> str:
        """Classes Tailwind CSS du badge de statut."""
        return get_patient_status_badge_class(self.patient.status)

    @property
    def status_dot_class(self) -> str:
        """Classe Tailwind CSS de la pastille de couleur du statut."""
        return get_patient_status_dot_class(self.patient.status)
