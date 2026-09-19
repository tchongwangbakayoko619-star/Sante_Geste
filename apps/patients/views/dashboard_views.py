"""Vue principale du tableau de bord médical (Espace de travail connecté)."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.views.generic import TemplateView

from apps.patients.models import Appointment
from apps.patients.models import Patient
from utils.enums import AppointmentStatusEnum


class DashboardHomeView(TemplateView):
    """Vue d'accueil affichant le tableau de bord temps réel pour l'utilisateur connecté

    ou la page vitrine institutionnelle pour les visiteurs anonymes.
    """

    template_name = "pages/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        # Heure et date locales
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        # Salutation temporelle (Bonjour en journée, Bonsoir après 18h)
        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"
        today_date = today.strftime("%d/%m/%Y")
        period_filter = self.request.GET.get("period", "today")

        # 1. Métriques des rendez-vous du jour
        today_appointments = Appointment.objects.filter(
            is_deleted=False,
            scheduled_at__date=today,
        )
        rdv_today_count = today_appointments.count()

        rdv_confirmed_count = today_appointments.filter(
            status__in=[
                AppointmentStatusEnum.COMPLETED,
                AppointmentStatusEnum.IN_CONSULTATION,
                AppointmentStatusEnum.WAITING,
            ]
        ).count()

        rdv_waiting_count = today_appointments.filter(
            status=AppointmentStatusEnum.WAITING
        ).count()

        rdv_scheduled_count = today_appointments.filter(
            status=AppointmentStatusEnum.SCHEDULED
        ).count()

        rdv_cancelled_count = today_appointments.filter(
            status=AppointmentStatusEnum.CANCELLED
        ).count()

        # 2. Métriques à venir et dossiers patients
        rdv_upcoming_count = Appointment.objects.filter(
            is_deleted=False,
            scheduled_at__gte=now,
            status=AppointmentStatusEnum.SCHEDULED,
        ).count()

        total_patients = Patient.objects.filter(is_deleted=False).count()
        new_patients_today = Patient.objects.filter(
            is_deleted=False,
            created_at__date=today,
        ).count()

        context.update(
            {
                "greeting": greeting,
                "today_date": today_date,
                "period_filter": period_filter,
                "rdv_today_count": rdv_today_count,
                "rdv_confirmed_count": rdv_confirmed_count,
                "rdv_waiting_count": rdv_waiting_count,
                "rdv_scheduled_count": rdv_scheduled_count,
                "rdv_cancelled_count": rdv_cancelled_count,
                "rdv_upcoming_count": rdv_upcoming_count,
                "total_patients": total_patients,
                "new_patients_today": new_patients_today,
            }
        )
        return context
