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


@register.simple_tag(takes_context=True)
def query_transform(context: dict[str, Any], **kwargs: Any) -> str:
    """Met à jour les paramètres GET de la requête courante en préservant l'ensemble des filtres actifs.

    Usage:
        <a href="?{% query_transform page=2 %}">Page 2</a>
        <a href="?{% query_transform ordering='last_name' %}">Trier par nom</a>
    """
    request = context.get("request")
    if not request:
        return ""
    query = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None and v != "":
            query[k] = str(v)
        else:
            query.pop(k, None)
    return query.urlencode()


@register.filter(name="get_elided_page_range")
def get_elided_page_range(page_obj: Any, on_each_side: int = 1) -> list[Any]:
    """Retourne la plage de pages élidée pour la pagination navigable.

    Usage:
        {% for page_num in page_obj|get_elided_page_range %}
            ...
        {% endfor %}
    """
    if not hasattr(page_obj, "paginator") or not hasattr(page_obj, "number"):
        return []
    return list(
        page_obj.paginator.get_elided_page_range(
            number=page_obj.number,
            on_each_side=on_each_side,
            on_ends=1,
        )
    )


@register.filter(name="split")
def split_filter(value: Any, delimiter: str = ",") -> list[str]:
    """Divise une chaîne en liste selon un délimiteur.

    Usage:
        {% for item in "08,09,10"|split:"," %}
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    if not value:
        return []
    return [s.strip() for s in str(value).split(delimiter) if s.strip()]


@register.filter(name="split_lines")
def split_lines_filter(value: Any) -> list[str]:
    """Divise une chaîne multiligne en liste de lignes nettoyées pour listes à puces.

    Usage:
        {% for line in ordonnance.notes|split_lines %}
            <li>• {{ line }}</li>
        {% endfor %}
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    lines = [line.strip().lstrip("-•*").strip() for line in str(value).splitlines()]
    return [l for l in lines if l]


