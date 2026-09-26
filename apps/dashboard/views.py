"""Vues du module Dashboard (HTML & API JSON)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.services.dashboard_service import DashboardService


def parse_custom_dates(start_str: str | None, end_str: str | None) -> tuple[datetime | None, datetime | None]:
    """Valide et convertit deux chaînes 'YYYY-MM-DD' en datetime aware."""
    if not start_str or not end_str:
        return None, None
    try:
        tz = timezone.get_current_timezone()
        d_start = datetime.strptime(start_str.strip(), "%Y-%m-%d")
        d_end = datetime.strptime(end_str.strip(), "%Y-%m-%d")
        aware_start = timezone.make_aware(d_start, tz)
        aware_end = timezone.make_aware(d_end, tz)
        return aware_start, aware_end
    except (ValueError, TypeError):
        return None, None


class DashboardHomeView(TemplateView):
    """Vue principale du tableau de bord médical connecté ou vitrine d'accueil anonyme."""

    template_name = "pages/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        period = self.request.GET.get("period", "today")
        start_date_param = self.request.GET.get("start_date") or self.request.GET.get("start")
        end_date_param = self.request.GET.get("end_date") or self.request.GET.get("end")

        custom_start, custom_end = parse_custom_dates(start_date_param, end_date_param)
        if period == "custom" and (not custom_start or not custom_end):
            # Si custom sans dates valides, initialiser sur les 30 derniers jours jusqu'à aujourd'hui
            now = timezone.localtime(timezone.now())
            custom_start = (now - timezone.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
            custom_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif custom_start and custom_end and period != "custom":
            period = "custom"

        dashboard_data = DashboardService.get_dashboard_data(
            user=user,
            period=period,
            custom_start=custom_start,
            custom_end=custom_end,
        )

        context.update(dashboard_data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else dashboard_data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else dashboard_data.get("custom_end_date", "")
        return context


class DashboardApiView(View):
    """Endpoint API JSON retournant les données du tableau de bord pour le frontend dynamique."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Non authentifié."}, status=401)

        period = request.GET.get("period", "today")
        start_date_param = request.GET.get("start_date") or request.GET.get("start")
        end_date_param = request.GET.get("end_date") or request.GET.get("end")

        custom_start, custom_end = parse_custom_dates(start_date_param, end_date_param)
        if custom_start and custom_end:
            period = "custom"

        data = DashboardService.get_dashboard_data(
            user=request.user,
            period=period,
            custom_start=custom_start,
            custom_end=custom_end,
        )

        serialized_data = dict(data)
        serialized_data["recent_appointments"] = [
            {
                "id": str(app.id),
                "scheduled_at": app.scheduled_at.isoformat() if app.scheduled_at else None,
                "patient_name": f"{app.patient.first_name} {app.patient.last_name}" if getattr(app, "patient", None) else "",
                "status": app.status,
                "reason": app.reason,
            }
            for app in data.get("recent_appointments", [])
        ]
        serialized_data["recent_patients"] = [
            {
                "id": str(p.id),
                "first_name": p.first_name,
                "last_name": p.last_name,
                "nup": p.nup,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in data.get("recent_patients", [])
        ]

        return JsonResponse(serialized_data, status=200)
