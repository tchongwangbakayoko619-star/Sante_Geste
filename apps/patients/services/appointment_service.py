"""Service de gestion et planification des rendez-vous médicaux."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Appointment
from utils.enums import AppointmentStatusEnum

if TYPE_CHECKING:
    import uuid

    from apps.patients.models import Patient
    from apps.users.models import User


def check_doctor_availability(
    doctor: User,
    scheduled_at: datetime,
    duration_minutes: int = 30,
    exclude_appointment_id: uuid.UUID | str | None = None,
) -> bool:
    """Vérifie si un praticien est disponible sans chevauchement de rendez-vous."""
    new_start = scheduled_at
    new_end = new_start + timedelta(minutes=duration_minutes)

    # Fenêtre élargie pour charger les RDV du créneau
    window_start = new_start - timedelta(hours=8)
    window_end = new_end + timedelta(hours=8)

    qs = Appointment.objects.filter(
        doctor=doctor,
        scheduled_at__gte=window_start,
        scheduled_at__lte=window_end,
    ).exclude(status=AppointmentStatusEnum.CANCELLED)

    if exclude_appointment_id:
        qs = qs.exclude(id=exclude_appointment_id)

    for apt in qs:
        # Chevauchement si (apt.start < new_end) et (apt.end > new_start)
        if apt.scheduled_at < new_end and apt.end_time > new_start:
            return False

    return True


def create_appointment(
    *,
    patient: Patient,
    doctor: User,
    scheduled_at: datetime,
    estimated_duration_minutes: int = 30,
    reason: str,
    notes: str = "",
    created_by: User | None = None,
) -> Appointment:
    """Crée un rendez-vous médical en vérifiant l'absence de conflit d'agenda."""
    if not check_doctor_availability(doctor, scheduled_at, estimated_duration_minutes):
        raise ValidationError(
            _("Le praticien a déjà une consultation programmée sur ce créneau horaire.")
        )

    appointment = Appointment(
        patient=patient,
        doctor=doctor,
        scheduled_at=scheduled_at,
        estimated_duration_minutes=estimated_duration_minutes,
        reason=reason,
        notes=notes,
        status=AppointmentStatusEnum.SCHEDULED,
    )
    if created_by:
        appointment.set_created_by(created_by)
        appointment.set_updated_by(created_by)
    appointment.save()
    return appointment


def update_appointment_status(
    *,
    appointment: Appointment,
    new_status: str,
    updated_by: User | None = None,
) -> Appointment:
    """Met à jour le statut du cycle de vie du rendez-vous."""
    valid_statuses = dict(AppointmentStatusEnum.choices)
    if new_status not in valid_statuses:
        raise ValidationError(_("Statut de rendez-vous non valide : %(status)s") % {"status": new_status})

    appointment.status = new_status
    if updated_by:
        appointment.set_updated_by(updated_by)
    appointment.save(update_fields=["status", "updated_by", "updated_at"])
    return appointment

