"""Filtres et balises de gabarit pour la présentation des patients et rendez-vous."""

from __future__ import annotations

from typing import Any

from django import template

from apps.patients.presenters import AppointmentPresenter
from apps.patients.presenters import PatientPresenter
from apps.patients.presenters import get_appointment_status_badge_class
from apps.patients.presenters import get_patient_status_badge_class
from apps.patients.presenters import get_patient_status_dot_class

register = template.Library()


@register.filter(name="appointment_status_badge_class")
def appointment_status_badge_class_filter(value: Any) -> str:
    """Retourne la classe CSS de badge pour un Appointment ou une chaîne de statut.

    Usage:
        {{ rdv|appointment_status_badge_class }}
        {{ rdv.status|appointment_status_badge_class }}
    """
    if hasattr(value, "status"):
        return get_appointment_status_badge_class(value.status)
    return get_appointment_status_badge_class(str(value) if value else None)


@register.filter(name="patient_status_badge_class")
def patient_status_badge_class_filter(value: Any) -> str:
    """Retourne la classe CSS de badge pour un Patient ou une chaîne de statut.

    Usage:
        {{ patient|patient_status_badge_class }}
        {{ patient.status|patient_status_badge_class }}
    """
    if hasattr(value, "status"):
        return get_patient_status_badge_class(value.status)
    return get_patient_status_badge_class(str(value) if value else None)


@register.filter(name="patient_status_dot_class")
def patient_status_dot_class_filter(value: Any) -> str:
    """Retourne la classe CSS de pastille de couleur pour un Patient ou une chaîne de statut.

    Usage:
        {{ patient|patient_status_dot_class }}
        {{ patient.status|patient_status_dot_class }}
    """
    if hasattr(value, "status"):
        return get_patient_status_dot_class(value.status)
    return get_patient_status_dot_class(str(value) if value else None)


@register.filter(name="as_appointment_presenter")
def as_appointment_presenter_filter(appointment: Any) -> AppointmentPresenter:
    """Enveloppe une instance de rendez-vous dans son presenter dédié."""
    return AppointmentPresenter(appointment)


@register.filter(name="as_patient_presenter")
def as_patient_presenter_filter(patient: Any) -> PatientPresenter:
    """Enveloppe une instance de patient dans son presenter dédié."""
    return PatientPresenter(patient)

