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
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import Any

from django.db.models import Avg
from django.db.models import Count
from django.db.models import F
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone

from apps.patients.models import Appointment
from apps.patients.models import Consultation
from apps.patients.models import Facture
from apps.patients.models import Ordonnance
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import Prestation
from apps.patients.models import PrestationRealisee
from apps.pharmacy.models import Batch
from apps.pharmacy.models import Category
from apps.pharmacy.models import Product
from apps.pharmacy.models import Sale
from apps.pharmacy.models import SaleItem
from apps.pharmacy.models import StockMovement
from apps.pharmacy.models import Supplier
from apps.users.services import rbac as rbac_service
from utils.enums import AppointmentStatusEnum

if TYPE_CHECKING:
    from apps.users.models import User


def format_fcfa(val: Decimal | int | float | None) -> str:
    """Formate un montant numérique en FCFA avec séparateur de milliers espace."""
    if val is None:
        val = 0
    return f"{int(round(float(val))):,}".replace(",", " ") + " FCFA"


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

        is_doctor_only = False
        is_medical_staff = False
        if user and getattr(user, "is_authenticated", False):
            is_medical_staff = bool(getattr(user, "is_personnel_medical", False))
            is_doctor_only = (
                is_medical_staff
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
            period="week" if period == "today" else period,
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

        # 8. Données et consultations spécifiques au personnel soignant (médecin)
        consultation_qs = Consultation.objects.filter(is_deleted=False)
        ordonnance_qs = Ordonnance.objects.all()

        if is_doctor_only and user:
            consultation_qs = consultation_qs.filter(doctor=user)
            ordonnance_qs = ordonnance_qs.filter(doctor=user)

        doctor_consultations_count = consultation_qs.filter(
            consultation_date__gte=start_date,
            consultation_date__lte=end_date,
        ).count()

        doctor_ordonnances_count = ordonnance_qs.filter(
            prescribed_at__gte=start_date,
            prescribed_at__lte=end_date,
        ).count()

        recent_consultations = (
            consultation_qs.select_related("patient", "doctor")
            .order_by("-consultation_date")[:5]
        )

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
            # Rôles et mode praticien
            "is_doctor_only": is_doctor_only,
            "is_medical_staff": is_medical_staff,
            "doctor_consultations_count": doctor_consultations_count,
            "doctor_ordonnances_count": doctor_ordonnances_count,
            "recent_consultations": recent_consultations,
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
            "charts_config": {
                "activity": {
                    "has_data": bool(activity_chart.get("has_data")),
                    "labels": list(activity_chart.get("labels", [])),
                    "planned": list(activity_chart.get("planned", [])),
                    "completed": list(activity_chart.get("completed", [])),
                    "today_idx": activity_chart.get("today_idx", -1),
                    "total_planned": activity_chart.get("total_planned", 0),
                    "total_completed": activity_chart.get("total_completed", 0),
                    "completion_rate": float(activity_chart.get("completion_rate", 0)),
                },
                "status_breakdown": {
                    "has_data": bool(status_breakdown.get("has_data")),
                    "total": int(status_breakdown.get("total", 0)),
                    "counts": {
                        "confirmed": int(status_breakdown.get("counts", {}).get("confirmed", 0)),
                        "waiting": int(status_breakdown.get("counts", {}).get("waiting", 0)),
                        "cancelled": int(status_breakdown.get("counts", {}).get("cancelled", 0)),
                        "scheduled": int(status_breakdown.get("counts", {}).get("scheduled", 0)),
                    },
                    "percentages": {
                        "confirmed": float(status_breakdown.get("percentages", {}).get("confirmed", 0)),
                        "waiting": float(status_breakdown.get("percentages", {}).get("waiting", 0)),
                        "cancelled": float(status_breakdown.get("percentages", {}).get("cancelled", 0)),
                        "scheduled": float(status_breakdown.get("percentages", {}).get("scheduled", 0)),
                    },
                },
            },
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
            chart_title = "Activité Hebdomadaire & Prise en Charge"
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

    # =========================================================================
    # 1. DASHBOARD AGENT D'ACCUEIL
    # =========================================================================
    @classmethod
    def get_accueil_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège les statistiques, flux de patients et rendez-vous pour l'Agent d'accueil."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        start_date, end_date = cls._resolve_period_range(
            period=period, local_now=local_now, custom_start=custom_start, custom_end=custom_end
        )

        appointment_qs = Appointment.objects.filter(is_deleted=False)
        patient_qs = Patient.objects.filter(is_deleted=False)

        total_patients = patient_qs.count()
        new_patients_today = patient_qs.filter(created_at__date=today).count()
        new_patients_period = patient_qs.filter(created_at__gte=start_date, created_at__lte=end_date).count()

        today_appointments = appointment_qs.filter(scheduled_at__date=today)
        appointments_today_count = today_appointments.count()
        appointments_waiting_count = today_appointments.filter(status=AppointmentStatusEnum.WAITING).count()

        period_appointments = appointment_qs.filter(scheduled_at__gte=start_date, scheduled_at__lte=end_date)
        stats = period_appointments.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=AppointmentStatusEnum.COMPLETED)),
            cancelled=Count("id", filter=Q(status=AppointmentStatusEnum.CANCELLED)),
            in_consultation=Count("id", filter=Q(status=AppointmentStatusEnum.IN_CONSULTATION)),
            waiting=Count("id", filter=Q(status=AppointmentStatusEnum.WAITING)),
            scheduled=Count("id", filter=Q(status=AppointmentStatusEnum.SCHEDULED)),
        )

        upcoming_count = appointment_qs.filter(
            scheduled_at__gte=now,
            status=AppointmentStatusEnum.SCHEDULED,
        ).count()

        activity_chart = cls._build_activity_chart(
            appointment_qs=appointment_qs,
            period="week" if period == "today" else period,
            start_date=start_date,
            end_date=end_date,
            local_now=local_now,
        )
        status_breakdown = cls._build_status_breakdown(
            stats={
                "total_count": stats["total"] or 0,
                "confirmed_count": (stats["completed"] or 0) + (stats["in_consultation"] or 0),
                "waiting_count": stats["waiting"] or 0,
                "cancelled_count": stats["cancelled"] or 0,
                "scheduled_count": stats["scheduled"] or 0,
            }
        )

        today_rdv_list = (
            today_appointments.select_related("patient", "doctor")
            .order_by("scheduled_at")[:10]
        )
        waiting_queue = (
            today_appointments.filter(status=AppointmentStatusEnum.WAITING)
            .select_related("patient", "doctor")
            .order_by("scheduled_at")[:10]
        )
        recent_patients = patient_qs.order_by("-created_at")[:8]

        imminent_appointments = (
            appointment_qs.filter(
                scheduled_at__gte=now,
                scheduled_at__lte=now + timedelta(hours=1),
                status=AppointmentStatusEnum.SCHEDULED,
            ).select_related("patient", "doctor")[:5]
        )
        missing_info_patients = patient_qs.filter(
            Q(phone_number="") | Q(emergency_contact_phone="")
        ).order_by("-created_at")[:5]

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
            "total_patients": total_patients,
            "new_patients_today": new_patients_today,
            "new_patients_period": new_patients_period,
            "appointments_today_count": appointments_today_count,
            "appointments_waiting_count": appointments_waiting_count,
            "appointments_completed_period": stats["completed"] or 0,
            "appointments_cancelled_period": stats["cancelled"] or 0,
            "upcoming_count": upcoming_count,
            "rdv_today_count": appointments_today_count,
            "rdv_waiting_count": appointments_waiting_count,
            "rdv_confirmed_count": stats["completed"] or 0,
            "rdv_cancelled_count": stats["cancelled"] or 0,
            "rdv_upcoming_count": upcoming_count,
            "activity_chart": activity_chart,
            "weekly_activity": activity_chart,
            "status_breakdown": status_breakdown,
            "today_rdv_list": today_rdv_list,
            "waiting_queue": waiting_queue,
            "recent_patients": recent_patients,
            "imminent_appointments": imminent_appointments,
            "missing_info_patients": missing_info_patients,
        }

    # =========================================================================
    # 2. DASHBOARD PERSONNEL MÉDICAL
    # =========================================================================
    @classmethod
    def get_medical_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège les consultations, patients et actes pour le Personnel médical (médecin / soignant)."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        start_date, end_date = cls._resolve_period_range(
            period=period, local_now=local_now, custom_start=custom_start, custom_end=custom_end
        )

        appointment_qs = Appointment.objects.filter(is_deleted=False)
        consultation_qs = Consultation.objects.filter(is_deleted=False)
        prestation_qs = PrestationRealisee.objects.all()

        is_doctor_only = False
        if user and getattr(user, "is_authenticated", False):
            if user.is_personnel_medical and not user.is_superuser and not user.is_proprietaire:
                is_doctor_only = True
                appointment_qs = appointment_qs.filter(doctor=user)
                consultation_qs = consultation_qs.filter(doctor=user)
                prestation_qs = prestation_qs.filter(doctor=user)

        my_rdv_today = appointment_qs.filter(scheduled_at__date=today).count()
        my_waiting_count = appointment_qs.filter(scheduled_at__date=today, status=AppointmentStatusEnum.WAITING).count()
        my_consultations_today = consultation_qs.filter(consultation_date__date=today).count()
        my_prestations_today = prestation_qs.filter(created_at__date=today).count()
        my_upcoming_count = appointment_qs.filter(scheduled_at__gte=now, status=AppointmentStatusEnum.SCHEDULED).count()
        my_consultations_period = consultation_qs.filter(consultation_date__gte=start_date, consultation_date__lte=end_date).count()

        activity_chart = cls._build_activity_chart(
            appointment_qs=appointment_qs,
            period="week" if period == "today" else period,
            start_date=start_date,
            end_date=end_date,
            local_now=local_now,
        )

        top_prestations = (
            prestation_qs.filter(created_at__gte=start_date, created_at__lte=end_date)
            .values("prestation__name")
            .annotate(total_count=Count("id"), total_val=Sum("total_price"))
            .order_by("-total_count")[:5]
        )

        my_today_agenda = (
            appointment_qs.filter(scheduled_at__date=today)
            .select_related("patient")
            .order_by("scheduled_at")[:10]
        )
        my_waiting_queue = (
            appointment_qs.filter(scheduled_at__date=today, status=AppointmentStatusEnum.WAITING)
            .select_related("patient")
            .order_by("scheduled_at")[:10]
        )
        my_upcoming_rdv = (
            appointment_qs.filter(scheduled_at__gte=now)
            .select_related("patient")
            .order_by("scheduled_at")[:8]
        )
        my_recent_consultations = (
            consultation_qs.select_related("patient")
            .order_by("-consultation_date")[:8]
        )

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"
        doc_profile = getattr(user, "medical_profile", None) if user else None

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
            "is_doctor_only": is_doctor_only,
            "is_medical_staff": True,
            "specialite": doc_profile.specialite if doc_profile else "Médecine Générale",
            "my_rdv_today": my_rdv_today,
            "my_waiting_count": my_waiting_count,
            "my_consultations_today": my_consultations_today,
            "my_prestations_today": my_prestations_today,
            "my_upcoming_count": my_upcoming_count,
            "my_consultations_period": my_consultations_period,
            "doctor_consultations_count": my_consultations_period,
            "recent_consultations": my_recent_consultations,
            "activity_chart": activity_chart,
            "weekly_activity": activity_chart,
            "top_prestations": list(top_prestations),
            "my_today_agenda": my_today_agenda,
            "my_waiting_queue": my_waiting_queue,
            "my_upcoming_rdv": my_upcoming_rdv,
            "my_recent_consultations": my_recent_consultations,
        }

    # =========================================================================
    # 3. DASHBOARD CAISSIER
    # =========================================================================
    @classmethod
    def get_caisse_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège les encaissements, factures et modes de paiement pour le Caissier."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        start_date, end_date = cls._resolve_period_range(
            period=period, local_now=local_now, custom_start=custom_start, custom_end=custom_end
        )

        paiement_qs = Paiement.objects.all()
        facture_qs = Facture.objects.all()
        prestation_realisee_qs = PrestationRealisee.objects.all()

        today_collected = paiement_qs.filter(paid_at__date=today).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        today_payments_count = paiement_qs.filter(paid_at__date=today).count()

        period_collected = paiement_qs.filter(paid_at__gte=start_date, paid_at__lte=end_date).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        period_payments_count = paiement_qs.filter(paid_at__gte=start_date, paid_at__lte=end_date).count()

        unpaid_count = facture_qs.filter(status="UNPAID").count()
        partially_paid_count = facture_qs.filter(status="PARTIALLY_PAID").count()
        pending_acts_count = prestation_realisee_qs.filter(facture__isnull=True).count()

        remaining_total = facture_qs.filter(status__in=["UNPAID", "PARTIALLY_PAID"]).aggregate(
            rem=Sum(F("total_amount") - F("paid_amount"))
        )["rem"] or Decimal("0.00")

        payment_methods_agg = (
            paiement_qs.filter(paid_at__gte=start_date, paid_at__lte=end_date)
            .values("payment_method")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        pm_display = dict(Paiement.PAYMENT_METHOD_CHOICES)
        payment_methods = [
            {
                "code": pm["payment_method"],
                "label": str(pm_display.get(pm["payment_method"], pm["payment_method"])),
                "total": pm["total"],
                "total_formatted": format_fcfa(pm["total"]),
                "count": pm["count"],
            }
            for pm in payment_methods_agg
        ]

        recent_payments = paiement_qs.select_related("facture__patient", "cashier").order_by("-paid_at")[:10]
        unpaid_invoices = facture_qs.filter(status__in=["UNPAID", "PARTIALLY_PAID"]).select_related("patient").order_by("-issued_at")[:8]
        pending_acts = prestation_realisee_qs.filter(facture__isnull=True).select_related("patient", "doctor", "prestation").order_by("-created_at")[:8]

        high_unpaid = facture_qs.filter(status__in=["UNPAID", "PARTIALLY_PAID"], total_amount__gte=50000).select_related("patient")[:5]

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
            "today_collected_amount": today_collected,
            "today_collected_formatted": format_fcfa(today_collected),
            "today_payments_count": today_payments_count,
            "period_collected_amount": period_collected,
            "period_collected_formatted": format_fcfa(period_collected),
            "period_payments_count": period_payments_count,
            "unpaid_invoices_count": unpaid_count,
            "partially_paid_invoices_count": partially_paid_count,
            "pending_acts_count": pending_acts_count,
            "total_remaining_to_collect": remaining_total,
            "total_remaining_formatted": format_fcfa(remaining_total),
            "payment_methods": payment_methods,
            "recent_payments": recent_payments,
            "unpaid_invoices": unpaid_invoices,
            "pending_acts": pending_acts,
            "high_unpaid": high_unpaid,
        }

    # =========================================================================
    # 4. DASHBOARD VENDEUR PHARMACIE
    # =========================================================================
    @classmethod
    def get_pharmacie_vendeur_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège les ventes au comptoir, délivrances et stocks critiques pour le Vendeur pharmacie."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()
        warning_expiry_date = today + timedelta(days=90)

        start_date, end_date = cls._resolve_period_range(
            period=period, local_now=local_now, custom_start=custom_start, custom_end=custom_end
        )

        sale_qs = Sale.objects.exclude(status="CANCELLED")
        product_qs = Product.objects.filter(is_deleted=False)
        batch_qs = Batch.objects.filter(status="ACTIVE", current_quantity__gt=0)
        ordonnance_qs = Ordonnance.objects.all()

        today_sales_count = sale_qs.filter(sale_date__date=today).count()
        today_sales_amount = sale_qs.filter(sale_date__date=today).aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
        period_sales_count = sale_qs.filter(sale_date__gte=start_date, sale_date__lte=end_date).count()
        period_sales_amount = sale_qs.filter(sale_date__gte=start_date, sale_date__lte=end_date).aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")

        available_products_count = product_qs.filter(current_stock__gt=0).count()
        out_of_stock_count = product_qs.filter(current_stock=0).count()
        low_stock_count = product_qs.filter(current_stock__gt=0, current_stock__lte=F("min_stock_threshold")).count()
        pending_prescriptions_count = ordonnance_qs.filter(status="PENDING").count()
        expiring_batches_count = batch_qs.filter(expiry_date__lte=warning_expiry_date, expiry_date__gt=today).count()

        top_selling = (
            SaleItem.objects.filter(
                sale__sale_date__gte=start_date,
                sale__sale_date__lte=end_date,
                sale__status__in=["COMPLETED", "PENDING_PAYMENT"],
            )
            .values("product__name", "product__dci")
            .annotate(qty_sold=Sum("quantity"), total_revenue=Sum("total_price"))
            .order_by("-qty_sold")[:6]
        )

        recent_sales = Sale.objects.select_related("seller", "patient").order_by("-sale_date")[:8]
        pending_prescriptions = ordonnance_qs.filter(status="PENDING").select_related("patient", "doctor").order_by("-prescribed_at")[:6]
        out_of_stock_products = product_qs.filter(current_stock__lte=F("min_stock_threshold")).order_by("current_stock")[:6]
        expiring_batches = batch_qs.filter(expiry_date__lte=warning_expiry_date).select_related("product", "supplier").order_by("expiry_date")[:6]

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
            "today_sales_count": today_sales_count,
            "today_sales_amount": today_sales_amount,
            "today_sales_formatted": format_fcfa(today_sales_amount),
            "period_sales_count": period_sales_count,
            "period_sales_amount": period_sales_amount,
            "period_sales_formatted": format_fcfa(period_sales_amount),
            "available_products_count": available_products_count,
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
            "pending_prescriptions_count": pending_prescriptions_count,
            "expiring_batches_count": expiring_batches_count,
            "top_selling": list(top_selling),
            "recent_sales": recent_sales,
            "pending_prescriptions": pending_prescriptions,
            "out_of_stock_products": out_of_stock_products,
            "expiring_batches": expiring_batches,
        }

    # =========================================================================
    # 5. DASHBOARD RESPONSABLE PHARMACIE
    # =========================================================================
    @classmethod
    def get_pharmacie_responsable_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège la gestion complète des stocks, valorisation et ventes pour le Responsable pharmacie."""
        vendeur_data = cls.get_pharmacie_vendeur_data(user, period, custom_start, custom_end)

        start_date = timezone.datetime.fromisoformat(vendeur_data["start_date"])
        end_date = timezone.datetime.fromisoformat(vendeur_data["end_date"])

        product_qs = Product.objects.filter(is_deleted=False)
        batch_qs = Batch.objects.filter(status="ACTIVE")
        movement_qs = StockMovement.objects.all()

        stock_val = product_qs.aggregate(val=Sum(F("current_stock") * F("purchase_price")))["val"] or Decimal("0.00")
        total_products = product_qs.count()

        today = timezone.localdate()
        expired_batches_count = batch_qs.filter(current_quantity__gt=0, expiry_date__lte=today).count()
        period_entries_count = movement_qs.filter(movement_type="IN_PURCHASE", movement_date__gte=start_date, movement_date__lte=end_date).count()
        period_entries_value = movement_qs.filter(movement_type="IN_PURCHASE", movement_date__gte=start_date, movement_date__lte=end_date).aggregate(
            v=Sum(F("quantity") * F("product__purchase_price"))
        )["v"] or Decimal("0.00")

        category_stock = (
            Category.objects.annotate(
                prod_count=Count("products", filter=Q(products__is_deleted=False)),
                total_stock=Sum("products__current_stock", filter=Q(products__is_deleted=False)),
                val=Sum(F("products__current_stock") * F("products__purchase_price"), filter=Q(products__is_deleted=False)),
            )
            .filter(prod_count__gt=0)
            .order_by("-val")[:6]
        )

        recent_movements = movement_qs.select_related("product", "batch", "user").order_by("-movement_date", "-created_at")[:8]

        vendeur_data.update({
            "stock_total_value": stock_val,
            "stock_total_value_formatted": format_fcfa(stock_val),
            "total_products": total_products,
            "expired_batches_count": expired_batches_count,
            "period_entries_count": period_entries_count,
            "period_entries_value": period_entries_value,
            "period_entries_formatted": format_fcfa(period_entries_value),
            "category_stock": list(category_stock),
            "recent_movements": recent_movements,
        })
        return vendeur_data

    # =========================================================================
    # 6. DASHBOARD PROPRIÉTAIRE (DIRECTION)
    # =========================================================================
    @classmethod
    def get_proprietaire_data(
        cls,
        user: User | None,
        period: str = "today",
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Agrège les indicateurs de gouvernance, recettes réelles et activité hospitalière pour le Propriétaire."""
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        start_date, end_date = cls._resolve_period_range(
            period=period, local_now=local_now, custom_start=custom_start, custom_end=custom_end
        )

        paiement_qs = Paiement.objects.filter(paid_at__gte=start_date, paid_at__lte=end_date)
        total_caisse = paiement_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        sale_qs = Sale.objects.filter(sale_date__gte=start_date, sale_date__lte=end_date).exclude(status="CANCELLED")
        total_pharmacie = sale_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")

        total_revenue = total_caisse + total_pharmacie

        facture_qs = Facture.objects.all()
        unpaid_balance = facture_qs.filter(status__in=["UNPAID", "PARTIALLY_PAID"]).aggregate(
            rem=Sum(F("total_amount") - F("paid_amount"))
        )["rem"] or Decimal("0.00")
        total_invoiced_period = facture_qs.filter(issued_at__gte=start_date, issued_at__lte=end_date).aggregate(
            tot=Sum("total_amount")
        )["tot"] or Decimal("0.00")

        recovery_rate = 0.0
        if total_invoiced_period > 0:
            recovery_rate = round(float(total_caisse / total_invoiced_period) * 100, 1)

        patient_qs = Patient.objects.filter(is_deleted=False)
        total_patients = patient_qs.count()
        new_patients_period = patient_qs.filter(created_at__gte=start_date, created_at__lte=end_date).count()

        consultation_qs = Consultation.objects.filter(is_deleted=False)
        consultations_period = consultation_qs.filter(consultation_date__gte=start_date, consultation_date__lte=end_date).count()

        appointment_qs = Appointment.objects.filter(is_deleted=False, scheduled_at__gte=start_date, scheduled_at__lte=end_date)
        rdv_total_period = appointment_qs.count()
        rdv_completed_period = appointment_qs.filter(status=AppointmentStatusEnum.COMPLETED).count()

        product_qs = Product.objects.filter(is_deleted=False)
        stock_value = product_qs.aggregate(val=Sum(F("current_stock") * F("purchase_price")))["val"] or Decimal("0.00")
        out_of_stock_products_count = product_qs.filter(current_stock=0).count()

        departments_summary = [
            {
                "name": "Consultations & Soins Médicaux",
                "volume": f"{consultations_period} consultations",
                "indicator_label": "RDV Honorés",
                "indicator_value": f"{rdv_completed_period} / {rdv_total_period}",
                "status": "Actif",
                "badge_class": "bg-emerald-50 text-emerald-700 border-emerald-200",
            },
            {
                "name": "Caisse & Recouvrement",
                "volume": format_fcfa(total_caisse),
                "indicator_label": "Taux d'encaissement",
                "indicator_value": f"{recovery_rate}%",
                "status": "Solvable",
                "badge_class": "bg-teal-50 text-teal-700 border-teal-200",
            },
            {
                "name": "Pharmacie Hospitalière",
                "volume": format_fcfa(total_pharmacie),
                "indicator_label": "Valeur stock",
                "indicator_value": format_fcfa(stock_value),
                "status": f"{out_of_stock_products_count} ruptures" if out_of_stock_products_count else "Optimal",
                "badge_class": "bg-amber-50 text-amber-700 border-amber-200" if out_of_stock_products_count else "bg-emerald-50 text-emerald-700 border-emerald-200",
            },
        ]

        unpaid_top = facture_qs.filter(status__in=["UNPAID", "PARTIALLY_PAID"]).select_related("patient").order_by("-total_amount")[:8]
        recent_transactions = paiement_qs.select_related("facture__patient", "cashier").order_by("-paid_at")[:8]

        greeting = "Bonsoir" if local_now.hour >= 18 else "Bonjour"

        return {
            "greeting": greeting,
            "today_date": today.strftime("%d/%m/%Y"),
            "period": period,
            "period_label": cls._get_period_label(period, start_date=start_date, end_date=end_date),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "custom_start_date": start_date.strftime("%Y-%m-%d"),
            "custom_end_date": end_date.strftime("%Y-%m-%d"),
            "total_caisse": total_caisse,
            "total_caisse_formatted": format_fcfa(total_caisse),
            "total_pharmacie": total_pharmacie,
            "total_pharmacie_formatted": format_fcfa(total_pharmacie),
            "total_revenue": total_revenue,
            "total_revenue_formatted": format_fcfa(total_revenue),
            "total_patients": total_patients,
            "new_patients_period": new_patients_period,
            "consultations_period": consultations_period,
            "unpaid_balance": unpaid_balance,
            "unpaid_balance_formatted": format_fcfa(unpaid_balance),
            "stock_value": stock_value,
            "stock_value_formatted": format_fcfa(stock_value),
            "recovery_rate": recovery_rate,
            "departments_summary": departments_summary,
            "unpaid_top": unpaid_top,
            "recent_transactions": recent_transactions,
        }

