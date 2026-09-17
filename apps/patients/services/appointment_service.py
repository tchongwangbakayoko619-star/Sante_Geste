"""Service de gestion et planification des rendez-vous médicaux."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Appointment
from utils.enums import AppointmentStatusEnum

if TYPE_CHECKING:
    import uuid

    from apps.patients.models import Patient
    from apps.users.models import User


def find_conflicting_appointment(
    *,
    doctor: User | str | uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int = 30,
    exclude_appointment_id: uuid.UUID | str | None = None,
) -> Appointment | None:
    """Recherche et retourne un rendez-vous entrant en conflit d'agenda via filtrage purement SQL.

    Règle d'intersection d'intervalles :
    Deux consultations [start_A, end_A[ et [start_B, end_B[ se chevauchent ssi :
    (start_A < end_B) ET (end_A > start_B).

    L'optimisation SQL calcule la fin de consultation (`calculated_end`) directement au niveau du moteur
    relationnel (F("scheduled_at") + DurationField) sans charger ni itérer sur des créneaux en mémoire Python.
    """
    from django.db.models import DateTimeField
    from django.db.models import DurationField
    from django.db.models import ExpressionWrapper
    from django.db.models import F

    doctor_id = getattr(doctor, "pk", doctor)
    new_start = scheduled_at
    new_end = new_start + timedelta(minutes=duration_minutes)

    # Expression SQL calculant l'heure prévisionnelle de fin de chaque consultation
    duration_expr = ExpressionWrapper(
        F("estimated_duration_minutes") * 60 * 1000000,
        output_field=DurationField(),
    )
    end_expr = ExpressionWrapper(
        F("scheduled_at") + duration_expr,
        output_field=DateTimeField(),
    )

    qs = (
        Appointment.objects.annotate(calculated_end=end_expr)
        .filter(
            doctor_id=doctor_id,
            scheduled_at__lt=new_end,
            calculated_end__gt=new_start,
        )
        .exclude(status=AppointmentStatusEnum.CANCELLED)
    )

    if exclude_appointment_id:
        qs = qs.exclude(id=exclude_appointment_id)

    return qs.select_related("doctor").first()


def check_doctor_availability(
    doctor: User,
    scheduled_at: datetime,
    duration_minutes: int = 30,
    exclude_appointment_id: uuid.UUID | str | None = None,
) -> bool:
    """Vérifie si un praticien est disponible sans chevauchement de rendez-vous.

    Un praticien est disponible ssi :
    1. Il est actif au sein de l'établissement (is_active=True).
    2. Il fait partie du personnel médical habilité (is_personnel_medical=True).
    3. Aucun rendez-vous non-annulé ne chevauche le créneau demandé.
    """
    if not doctor.is_active or not doctor.is_personnel_medical:
        return False

    conflict = find_conflicting_appointment(
        doctor=doctor,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        exclude_appointment_id=exclude_appointment_id,
    )
    return conflict is None


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
    """Crée un rendez-vous médical en sérialisant les accès concurrents (verrou pessimiste)."""
    if not doctor.is_personnel_medical:
        raise ValidationError(
            _("L'utilisateur sélectionné n'est pas habilité comme personnel médical.")
        )
    if not doctor.is_active:
        raise ValidationError(
            _("Impossible de planifier un rendez-vous avec un praticien inactif ou ayant quitté l'établissement.")
        )

    user_model = get_user_model()
    with transaction.atomic():
        # Verrouillage pessimiste sur la ligne du praticien pour sérialiser
        # les réservations concurrentes et éliminer les conditions de course (double-booking).
        user_model.objects.select_for_update().get(pk=doctor.pk)

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


def reschedule_appointment(
    *,
    appointment: Appointment,
    new_scheduled_at: datetime,
    new_duration_minutes: int | None = None,
    new_doctor: User | None = None,
    notes: str | None = None,
    updated_by: User | None = None,
) -> Appointment:
    """Reporte ou réassigne un rendez-vous médical avec verrouillage pessimiste anti-concurrence."""
    target_doctor = new_doctor or appointment.doctor
    target_duration = new_duration_minutes or appointment.estimated_duration_minutes or 30

    if not target_doctor.is_personnel_medical:
        raise ValidationError(
            _("L'utilisateur sélectionné n'est pas habilité comme personnel médical.")
        )
    if not target_doctor.is_active:
        raise ValidationError(
            _("Impossible de planifier un rendez-vous avec un praticien inactif ou ayant quitté l'établissement.")
        )

    user_model = get_user_model()
    with transaction.atomic():
        # Sérialisation des modifications sur l'agenda du praticien cible
        user_model.objects.select_for_update().get(pk=target_doctor.pk)
        locked_apt = Appointment.objects.select_for_update().get(pk=appointment.pk)

        if not check_doctor_availability(
            doctor=target_doctor,
            scheduled_at=new_scheduled_at,
            duration_minutes=target_duration,
            exclude_appointment_id=locked_apt.pk,
        ):
            raise ValidationError(
                _("Le praticien a déjà une consultation programmée sur ce créneau horaire.")
            )

        locked_apt.doctor = target_doctor
        locked_apt.scheduled_at = new_scheduled_at
        locked_apt.estimated_duration_minutes = target_duration
        if notes is not None:
            locked_apt.notes = notes
        if updated_by:
            locked_apt.set_updated_by(updated_by)

        locked_apt.save()
        return locked_apt


def cancel_appointment(
    *,
    appointment: Appointment,
    cancellation_reason: str = "",
    cancelled_by: User | None = None,
) -> Appointment:
    """Annule un rendez-vous médical et libère immédiatement le créneau du praticien."""
    with transaction.atomic():
        locked_apt = Appointment.objects.select_for_update().get(pk=appointment.pk)
        locked_apt.status = AppointmentStatusEnum.CANCELLED
        if cancellation_reason:
            prefix = _("[ANNULÉ]")
            existing_notes = locked_apt.notes.strip()
            locked_apt.notes = f"{existing_notes}\n{prefix} {cancellation_reason}".strip()
        if cancelled_by:
            locked_apt.set_updated_by(cancelled_by)
        locked_apt.save(update_fields=["status", "notes", "updated_by", "updated_at"])
        return locked_apt


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


def get_appointment_daily_stats(target_date: datetime | None = None) -> dict[str, int]:
    """Calcule les statistiques consolidées de l'agenda et de la file d'attente journalière."""
    base_time = target_date or timezone.now()
    day_start = base_time.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    today_qs = Appointment.objects.filter(scheduled_at__gte=day_start, scheduled_at__lt=day_end)
    return {
        "today_count": today_qs.count(),
        "waiting_count": today_qs.filter(status=AppointmentStatusEnum.WAITING).count(),
        "in_consultation_count": today_qs.filter(status=AppointmentStatusEnum.IN_CONSULTATION).count(),
        "completed_count": today_qs.filter(status=AppointmentStatusEnum.COMPLETED).count(),
    }
