"""Service métier d'agrégation des statistiques du tableau de bord.

Calculs basés exclusivement sur la base de données réelle et les modèles :
- Appointment (Rendez-vous médicaux)
- Patient (Dossiers patients)
- User / RBAC (Permissions et contextes utilisateurs)
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any

from django.db.models import Count
from django.db.models import Q
from django.utils import timezone

from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.users.services import rbac as rbac_service
from utils.enums import AppointmentStatusEnum

if TYPE_CHECKING:
    from apps.users.models import User


class DashboardService:
    """Service central de calcul des indicateurs et graphiques du tableau de bord."""

    @classmethod
    def get_dashboard_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Récupère l'ensemble des données réelles du dashboard selon l'utilisateur et la période."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        # 1. Détermination de la fenêtre temporelle
        start_date, end_date = cls._resolve_period_range(
            period=period,
            local_now=local_now,
            custom_start=custom_start,
            custom_end=custom_end,
        )

        # 2. Filtrage RBAC du QuerySet Appointment
        # Seul le personnel médical (médecin) restreint aux miens s'il n'est pas agent d'accueil/propriétaire/superuser
        appointment_qs = Appointment.objects.filter(is_deleted=False)
        patient_qs = Patient.objects.filter(is_deleted=False)

        if user and getattr(user, "is_authenticated", False):
            is_doctor_only = (
                getattr(user, "is_personnel_medical", False)
                and not getattr(user, "is_agent_accueil", False)
                and not getattr(user, "is_proprietaire", False)
                and not getattr(user, "is_superuser", False)
            )
            if is_doctor_only:
                appointment_qs = appointment_qs.filter(doctor=user)

        # 3. Métriques de la période sélectionnée (Agrégation ORM unique)
        period_appointments = appointment_qs.filter(
            scheduled_at__gte=start_date,
            scheduled_at__lte=end_date,
        )

        stats = period_appointments.aggregate(
            total_count=Count("id"),
            confirmed_count=Count(
                "id",
                filter=Q(
                    status__in=[
                        AppointmentStatusEnum.COMPLETED,
                        AppointmentStatusEnum.IN_CONSULTATION,
                        AppointmentStatusEnum.WAITING,
                    ]
                ),
            ),
            waiting_count=Count("id", filter=Q(status=AppointmentStatusEnum.WAITING)),
            scheduled_count=Count("id", filter=Q(status=AppointmentStatusEnum.SCHEDULED)),
            cancelled_count=Count("id", filter=Q(status=AppointmentStatusEnum.CANCELLED)),
            completed_count=Count("id", filter=Q(status=AppointmentStatusEnum.COMPLETED)),
            in_consultation_count=Count(
                "id", filter=Q(status=AppointmentStatusEnum.IN_CONSULTATION)
            ),
        )

        # 4. Métriques à venir & Nouveaux patients
        rdv_upcoming_count = appointment_qs.filter(
            scheduled_at__gte=now,
            status=AppointmentStatusEnum.SCHEDULED,
        ).count()

        total_patients = patient_qs.count()
        new_patients_period = patient_qs.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).count()

        # 5. Séries temporelles pour les graphiques (Courbe Hebdomadaire & Répartition Donut)
        weekly_activity = cls._build_weekly_activity_chart(appointment_qs=appointment_qs, local_now=local_now)
        status_breakdown = cls._build_status_breakdown(stats=stats)

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period_filter": period,
            "period_label": cls._get_period_label(period),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            # KPIs principaux
            "rdv_today_count": stats["total_count"] or 0,
            "rdv_confirmed_count": stats["confirmed_count"] or 0,
            "rdv_waiting_count": stats["waiting_count"] or 0,
            "rdv_scheduled_count": stats["scheduled_count"] or 0,
            "rdv_cancelled_count": stats["cancelled_count"] or 0,
            "rdv_completed_count": stats["completed_count"] or 0,
            "rdv_in_consultation_count": stats["in_consultation_count"] or 0,
            "rdv_upcoming_count": rdv_upcoming_count,
            "total_patients": total_patients,
            "new_patients_period": new_patients_period,
            # Graphiques
            "weekly_activity": weekly_activity,
            "status_breakdown": status_breakdown,
        }

    @classmethod
    def _resolve_period_range(
        cls,
        period: str,
        local_now: datetime,
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """Calcule les bornes d'extension temporelle (start_date, end_date) en UTC aware."""
        today = local_now.date()

        if period == "week":
            start_date = local_now - timedelta(days=local_now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        elif period == "month":
            start_date = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start_date.replace(day=28) + timedelta(days=4)
            end_date = next_month - timedelta(days=next_month.day)
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period == "custom" and custom_start and custom_end:
            start_date = custom_start
            end_date = custom_end
        else:  # today (par défaut)
            start_date = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)

        return start_date, end_date

    @classmethod
    def _get_period_label(cls, period: str) -> str:
        labels = {
            "today": "Aujourd'hui",
            "week": "Cette semaine",
            "month": "Ce mois",
            "custom": "Période personnalisée",
        }
        return labels.get(period, "Aujourd'hui")

    @classmethod
    def _build_weekly_activity_chart(
        cls, appointment_qs: Any, local_now: datetime
    ) -> dict[str, Any]:
        """Génère les données réelles pour le graphique d'activité sur la semaine en cours (du lundi au dimanche)."""
        monday = local_now - timedelta(days=local_now.weekday())
        monday_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        sunday_end = monday_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

        week_appointments = appointment_qs.filter(
            scheduled_at__gte=monday_start,
            scheduled_at__lte=sunday_end,
        )

        days_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        planned_counts = [0] * 7
        completed_counts = [0] * 7

        for rdv in week_appointments:
            rdv_local = timezone.localtime(rdv.scheduled_at)
            day_idx = rdv_local.weekday()
            planned_counts[day_idx] += 1
            if rdv.status in [
                AppointmentStatusEnum.COMPLETED,
                AppointmentStatusEnum.IN_CONSULTATION,
                AppointmentStatusEnum.WAITING,
            ]:
                completed_counts[day_idx] += 1

        max_val = max(planned_counts + [10])

        return {
            "labels": days_labels,
            "planned": planned_counts,
            "completed": completed_counts,
            "max_value": max_val,
            "has_data": any(planned_counts),
        }

    @classmethod
    def _build_status_breakdown(cls, stats: dict[str, Any]) -> dict[str, Any]:
        """Calcule les pourcentages réels et angles pour le Donut Chart des statuts."""
        total = stats["total_count"] or 0
        if total == 0:
            return {
                "total": 0,
                "has_data": False,
                "percentages": {"completed": 0, "waiting": 0, "cancelled": 0, "scheduled": 0},
                "dasharrays": {
                    "completed": "0 365",
                    "waiting": "0 365",
                    "cancelled": "0 365",
                    "scheduled": "0 365",
                },
                "dashoffsets": {"completed": "0", "waiting": "0", "cancelled": "0", "scheduled": "0"},
            }

        confirmed = stats["confirmed_count"] or 0
        waiting = stats["waiting_count"] or 0
        cancelled = stats["cancelled_count"] or 0
        scheduled = stats["scheduled_count"] or 0

        # Périmètre circonférence SVG = 2 * PI * 58 ≈ 364.42 (arrondi 365)
        circ = 365
        len_completed = int((confirmed / total) * circ)
        len_waiting = int((waiting / total) * circ)
        len_cancelled = int((cancelled / total) * circ)
        len_scheduled = int((scheduled / total) * circ)

        off_completed = 0
        off_waiting = -len_completed
        off_cancelled = -(len_completed + len_waiting)
        off_scheduled = -(len_completed + len_waiting + len_cancelled)

        return {
            "total": total,
            "has_data": True,
            "counts": {
                "confirmed": confirmed,
                "waiting": waiting,
                "cancelled": cancelled,
                "scheduled": scheduled,
            },
            "percentages": {
                "confirmed": round((confirmed / total) * 100, 1),
                "waiting": round((waiting / total) * 100, 1),
                "cancelled": round((cancelled / total) * 100, 1),
                "scheduled": round((scheduled / total) * 100, 1),
            },
            "dasharrays": {
                "confirmed": f"{len_completed} {circ}",
                "waiting": f"{len_waiting} {circ}",
                "cancelled": f"{len_cancelled} {circ}",
                "scheduled": f"{len_scheduled} {circ}",
            },
            "dashoffsets": {
                "confirmed": str(off_completed),
                "waiting": str(off_waiting),
                "cancelled": str(off_cancelled),
                "scheduled": str(off_scheduled),
            },
        }
