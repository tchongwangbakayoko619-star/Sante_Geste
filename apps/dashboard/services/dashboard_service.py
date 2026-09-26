"""Service métier d'agrégation des statistiques du tableau de bord.

Calculs basés exclusivement sur la base de données réelle et les modèles :
- Appointment (Rendez-vous médicaux)
- Patient (Dossiers patients)
- User / RBAC (Permissions et contextes utilisateurs)
"""

from __future__ import annotations

import calendar
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

        # 5. Séries temporelles pour les graphiques (Courbe d'activité adaptative & Donut)
        activity_chart = cls._build_activity_chart(
            appointment_qs=appointment_qs,
            period=period,
            start_date=start_date,
            end_date=end_date,
            local_now=local_now,
        )
        status_breakdown = cls._build_status_breakdown(stats=stats)

        # 6. File d'attente du jour (Les 5 prochains RDV du jour ou en attente)
        recent_appointments = (
            appointment_qs.filter(scheduled_at__gte=start_date, scheduled_at__lte=end_date)
            .select_related("patient", "doctor")
            .order_by("scheduled_at")[:5]
        )

        # 7. Nouveaux patients récents (Les 5 derniers créés)
        recent_patients = patient_qs.order_by("-created_at")[:5]

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_filter": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
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
            "activity_chart": activity_chart,
            "weekly_activity": activity_chart,  # Rétrocompatibilité avec les tests et templates existants
            "status_breakdown": status_breakdown,
            # Listes réelles
            "recent_appointments": recent_appointments,
            "recent_patients": recent_patients,
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
        if period == "week":
            start_date = local_now - timedelta(days=local_now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        elif period == "month":
            start_date = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            num_days = calendar.monthrange(local_now.year, local_now.month)[1]
            end_date = local_now.replace(day=num_days, hour=23, minute=59, second=59, microsecond=999999)
        elif period == "year":
            start_date = local_now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = local_now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        elif period == "custom" and custom_start and custom_end:
            if custom_start > custom_end:
                custom_start, custom_end = custom_end, custom_start
            start_date = custom_start.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = custom_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:  # today (par défaut)
            start_date = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)

        return start_date, end_date

    @classmethod
    def _get_period_label(
        cls,
        period: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> str:
        """Retourne le libellé lisible de la période."""
        if period == "today":
            return "Aujourd'hui"
        if period == "week":
            return "Cette semaine"
        if period == "month":
            return "Ce mois"
        if period == "year":
            year_val = start_date.year if start_date else timezone.now().year
            return f"Année {year_val}"
        if period == "custom" and start_date and end_date:
            return f"Du {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"
        return "Aujourd'hui"

    @classmethod
    def _compute_spline(cls, pts: list[tuple[float, float]]) -> tuple[str, str]:
        """Génère un chemin lissé de Bézier cubique (spline) et la surface fermée pour le SVG."""
        if not pts:
            return "", ""
        if len(pts) == 1:
            x, y = pts[0]
            line_path = f"M {x} {y}"
            area_path = f"M {x} 220 L {x} {y} L {x} 220 Z"
            return line_path, area_path

        k = 0.2
        n = len(pts)
        segments = []
        for i in range(n - 1):
            p_prev = pts[max(0, i - 1)]
            p_curr = pts[i]
            p_next = pts[i + 1]
            p_nnext = pts[min(n - 1, i + 2)]
            cp1x = round(p_curr[0] + (p_next[0] - p_prev[0]) * k, 1)
            cp1y = round(max(20.0, min(220.0, p_curr[1] + (p_next[1] - p_prev[1]) * k)), 1)
            cp2x = round(p_next[0] - (p_nnext[0] - p_curr[0]) * k, 1)
            cp2y = round(max(20.0, min(220.0, p_next[1] - (p_nnext[1] - p_curr[1]) * k)), 1)
            segments.append(f"C {cp1x} {cp1y}, {cp2x} {cp2y}, {p_next[0]} {p_next[1]}")
        line_path = f"M {pts[0][0]} {pts[0][1]} " + " ".join(segments)
        area_path = f"{line_path} L {pts[-1][0]} 220 L {pts[0][0]} 220 Z"
        return line_path, area_path

    @classmethod
    def _build_activity_chart(
        cls,
        appointment_qs: Any,
        period: str,
        start_date: datetime,
        end_date: datetime,
        local_now: datetime,
    ) -> dict[str, Any]:
        """Génère les données réelles et les coordonnées SVG pour n'importe quelle période temporelle."""
        period_appointments = appointment_qs.filter(
            scheduled_at__gte=start_date,
            scheduled_at__lte=end_date,
        )

        today_idx = -1
        chart_title = "Activité & Consultation"
        chart_subtitle = "Évolution comparative des RDV planifiés vs consultations honorées"

        if period == "today":
            # 7 créneaux horaires réguliers (08h, 10h, 12h, 14h, 16h, 18h, 20h)
            time_slots = [8, 10, 12, 14, 16, 18, 20]
            slot_labels = [f"{h:02d}h" for h in time_slots]
            planned_counts = [0] * len(time_slots)
            completed_counts = [0] * len(time_slots)

            for rdv in period_appointments:
                rdv_local = timezone.localtime(rdv.scheduled_at)
                hour = rdv_local.hour
                best_idx = min(range(len(time_slots)), key=lambda i: abs(time_slots[i] - hour))
                planned_counts[best_idx] += 1
                if rdv.status in [
                    AppointmentStatusEnum.COMPLETED,
                    AppointmentStatusEnum.IN_CONSULTATION,
                    AppointmentStatusEnum.WAITING,
                ]:
                    completed_counts[best_idx] += 1

            xs = [round(60.0 + i * (570.0 / 6), 1) for i in range(7)]
            col_w = round(570.0 / 7, 1)
            points_meta = []
            for i in range(7):
                points_meta.append({
                    "day": slot_labels[i],
                    "short_label": slot_labels[i],
                    "show_label": True,
                    "x": xs[i],
                    "col_w": col_w,
                    "col_x": round(xs[i] - col_w / 2.0, 1),
                })
            now_hour = local_now.hour
            today_idx = min(range(len(time_slots)), key=lambda i: abs(time_slots[i] - now_hour))
            chart_title = "Activité de la Journée & Consultation"
            chart_subtitle = "Évolution par créneau horaire des consultations du jour"

        elif period == "week":
            days_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
            planned_counts = [0] * 7
            completed_counts = [0] * 7

            for rdv in period_appointments:
                rdv_local = timezone.localtime(rdv.scheduled_at)
                day_idx = rdv_local.weekday()
                planned_counts[day_idx] += 1
                if rdv.status in [
                    AppointmentStatusEnum.COMPLETED,
                    AppointmentStatusEnum.IN_CONSULTATION,
                    AppointmentStatusEnum.WAITING,
                ]:
                    completed_counts[day_idx] += 1

            xs = [60.0, 155.0, 250.0, 345.0, 440.0, 535.0, 630.0]
            col_w = 94.0
            points_meta = []
            for i in range(7):
                points_meta.append({
                    "day": days_labels[i],
                    "short_label": days_labels[i],
                    "show_label": True,
                    "x": xs[i],
                    "col_w": col_w,
                    "col_x": round(xs[i] - col_w / 2.0, 1),
                })
            today_idx = local_now.weekday()
            chart_title = "Activité Hebdomadaire & Consultation"
            chart_subtitle = "Évolution comparative des RDV planifiés vs consultations honorées"

        elif period == "month":
            # Découpage mensuel (jours du mois en cours)
            num_days = calendar.monthrange(start_date.year, start_date.month)[1]
            planned_counts = [0] * num_days
            completed_counts = [0] * num_days

            for rdv in period_appointments:
                rdv_local = timezone.localtime(rdv.scheduled_at)
                day_idx = rdv_local.day - 1
                if 0 <= day_idx < num_days:
                    planned_counts[day_idx] += 1
                    if rdv.status in [
                        AppointmentStatusEnum.COMPLETED,
                        AppointmentStatusEnum.IN_CONSULTATION,
                        AppointmentStatusEnum.WAITING,
                    ]:
                        completed_counts[day_idx] += 1

            step_x = 570.0 / (num_days - 1) if num_days > 1 else 0
            col_w = round(step_x, 1) if step_x > 0 else 94.0
            points_meta = []
            key_days = {1, 5, 10, 15, 20, 25, num_days}
            for i in range(num_days):
                day_num = i + 1
                x = round(60.0 + i * step_x, 1)
                points_meta.append({
                    "day": f"{day_num:02d}/{start_date.month:02d}",
                    "short_label": str(day_num),
                    "show_label": day_num in key_days,
                    "x": x,
                    "col_w": col_w,
                    "col_x": round(x - col_w / 2.0, 1),
                })
            if start_date.month == local_now.month and start_date.year == local_now.year:
                today_idx = local_now.day - 1
            chart_title = "Activité Mensuelle & Consultation"
            chart_subtitle = f"Évolution quotidienne des consultations ({start_date.strftime('%B %Y')})"

        elif period == "year":
            # Découpage annuel par 12 mois
            month_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]
            planned_counts = [0] * 12
            completed_counts = [0] * 12

            for rdv in period_appointments:
                rdv_local = timezone.localtime(rdv.scheduled_at)
                m_idx = rdv_local.month - 1
                planned_counts[m_idx] += 1
                if rdv.status in [
                    AppointmentStatusEnum.COMPLETED,
                    AppointmentStatusEnum.IN_CONSULTATION,
                    AppointmentStatusEnum.WAITING,
                ]:
                    completed_counts[m_idx] += 1

            step_x = 570.0 / 11
            col_w = round(step_x, 1)
            points_meta = []
            for i in range(12):
                x = round(60.0 + i * step_x, 1)
                points_meta.append({
                    "day": month_labels[i],
                    "short_label": month_labels[i],
                    "show_label": True,
                    "x": x,
                    "col_w": col_w,
                    "col_x": round(x - col_w / 2.0, 1),
                })
            if start_date.year == local_now.year:
                today_idx = local_now.month - 1
            chart_title = f"Activité Annuelle {start_date.year}"
            chart_subtitle = "Évolution mensuelle des consultations et admissions"

        else:
            # Période personnalisée (custom)
            start_d = start_date.date()
            end_d = end_date.date()
            total_days = max(1, (end_d - start_d).days + 1)

            if total_days <= 31:
                # Mode journalier
                planned_counts = [0] * total_days
                completed_counts = [0] * total_days

                for rdv in period_appointments:
                    rdv_local = timezone.localtime(rdv.scheduled_at)
                    d_idx = (rdv_local.date() - start_d).days
                    if 0 <= d_idx < total_days:
                        planned_counts[d_idx] += 1
                        if rdv.status in [
                            AppointmentStatusEnum.COMPLETED,
                            AppointmentStatusEnum.IN_CONSULTATION,
                            AppointmentStatusEnum.WAITING,
                        ]:
                            completed_counts[d_idx] += 1

                step_x = 570.0 / (total_days - 1) if total_days > 1 else 0
                col_w = round(step_x, 1) if step_x > 0 else 94.0
                points_meta = []
                for i in range(total_days):
                    cur_date = start_d + timedelta(days=i)
                    x = round(60.0 + i * step_x, 1)
                    show = (total_days <= 10) or (i == 0) or (i == total_days - 1) or (i % max(1, total_days // 6) == 0)
                    points_meta.append({
                        "day": cur_date.strftime("%d/%m"),
                        "short_label": cur_date.strftime("%d/%m"),
                        "show_label": show,
                        "x": x,
                        "col_w": col_w,
                        "col_x": round(x - col_w / 2.0, 1),
                    })
                    if cur_date == local_now.date():
                        today_idx = i
            else:
                # Période plus longue : regrouper en 10 tranches équidistantes
                num_buckets = 10
                bucket_size = total_days / num_buckets
                planned_counts = [0] * num_buckets
                completed_counts = [0] * num_buckets

                for rdv in period_appointments:
                    rdv_local = timezone.localtime(rdv.scheduled_at)
                    diff_days = (rdv_local.date() - start_d).days
                    b_idx = min(num_buckets - 1, int(diff_days / bucket_size))
                    if 0 <= b_idx < num_buckets:
                        planned_counts[b_idx] += 1
                        if rdv.status in [
                            AppointmentStatusEnum.COMPLETED,
                            AppointmentStatusEnum.IN_CONSULTATION,
                            AppointmentStatusEnum.WAITING,
                        ]:
                            completed_counts[b_idx] += 1

                step_x = 570.0 / (num_buckets - 1)
                col_w = round(step_x, 1)
                points_meta = []
                for i in range(num_buckets):
                    b_start = start_d + timedelta(days=int(i * bucket_size))
                    x = round(60.0 + i * step_x, 1)
                    points_meta.append({
                        "day": b_start.strftime("%d/%m"),
                        "short_label": b_start.strftime("%d/%m"),
                        "show_label": True,
                        "x": x,
                        "col_w": col_w,
                        "col_x": round(x - col_w / 2.0, 1),
                    })

            chart_title = "Activité sur la Période Sélectionnée"
            chart_subtitle = f"Du {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        # Échelle Y dynamique
        n_points = len(planned_counts)
        raw_max = max(planned_counts + [4])
        rem = raw_max % 4
        max_val = raw_max if rem == 0 else raw_max + (4 - rem)
        if max_val < 4:
            max_val = 4

        pts_planned = [
            (points_meta[i]["x"], round(220.0 - (planned_counts[i] / max_val) * 200.0, 1))
            for i in range(n_points)
        ]
        pts_completed = [
            (points_meta[i]["x"], round(220.0 - (completed_counts[i] / max_val) * 200.0, 1))
            for i in range(n_points)
        ]

        planned_path, planned_area = cls._compute_spline(pts_planned)
        completed_path, completed_area = cls._compute_spline(pts_completed)

        points = []
        for i in range(n_points):
            points.append({
                "day": points_meta[i]["day"],
                "short_label": points_meta[i].get("short_label", points_meta[i]["day"]),
                "show_label": points_meta[i].get("show_label", True),
                "x": points_meta[i]["x"],
                "col_w": points_meta[i]["col_w"],
                "col_x": points_meta[i]["col_x"],
                "planned_val": planned_counts[i],
                "completed_val": completed_counts[i],
                "planned_y": pts_planned[i][1],
                "completed_y": pts_completed[i][1],
            })

        y_ticks = [
            {"val": max_val, "y": 20},
            {"val": int(max_val * 0.75), "y": 70},
            {"val": int(max_val * 0.50), "y": 120},
            {"val": int(max_val * 0.25), "y": 170},
            {"val": 0, "y": 220},
        ]

        total_planned = sum(planned_counts)
        total_completed = sum(completed_counts)
        completion_rate = round((total_completed / total_planned * 100), 1) if total_planned > 0 else 0.0

        return {
            "title": chart_title,
            "subtitle": chart_subtitle,
            "labels": [p["day"] for p in points_meta],
            "planned": planned_counts,
            "completed": completed_counts,
            "today_idx": today_idx,
            "total_planned": total_planned,
            "total_completed": total_completed,
            "completion_rate": completion_rate,
            "max_value": max_val,
            "has_data": any(planned_counts),
            "planned_path": planned_path,
            "planned_area": planned_area,
            "completed_path": completed_path,
            "completed_area": completed_area,
            "points": points,
            "y_ticks": y_ticks,
        }

    @classmethod
    def _build_weekly_activity_chart(
        cls, appointment_qs: Any, local_now: datetime
    ) -> dict[str, Any]:
        """Méthode de compatibilité pour l'activité hebdomadaire."""
        monday = local_now - timedelta(days=local_now.weekday())
        monday_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        sunday_end = monday_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        return cls._build_activity_chart(
            appointment_qs=appointment_qs,
            period="week",
            start_date=monday_start,
            end_date=sunday_end,
            local_now=local_now,
        )

    @classmethod
    def _build_status_breakdown(cls, stats: dict[str, Any]) -> dict[str, Any]:
        """Calcule les pourcentages réels et angles pour le Donut Chart des statuts."""
        total = stats["total_count"] or 0
        if total == 0:
            return {
                "total": 0,
                "has_data": False,
                "percentages": {"confirmed": 0, "waiting": 0, "cancelled": 0, "scheduled": 0},
                "dasharrays": {
                    "confirmed": "0 365",
                    "waiting": "0 365",
                    "cancelled": "0 365",
                    "scheduled": "0 365",
                },
                "dashoffsets": {"confirmed": "0", "waiting": "0", "cancelled": "0", "scheduled": "0"},
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
