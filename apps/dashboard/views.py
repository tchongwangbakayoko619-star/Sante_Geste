"""Vues du module Dashboard (HTML & API JSON)."""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.services.dashboard_service import DashboardService


class DashboardHomeView(TemplateView):
    """Vue principale du tableau de bord médical connecté ou vitrine d'accueil anonyme."""

    template_name = "pages/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        period = self.request.GET.get("period", "today")
        dashboard_data = DashboardService.get_dashboard_data(
            user=user,
            period=period,
        )

        context.update(dashboard_data)
        return context


class DashboardApiView(View):
    """Endpoint API JSON retournant les données du tableau de bord pour le frontend dynamique."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Non authentifié."}, status=401)

        period = request.GET.get("period", "today")
        data = DashboardService.get_dashboard_data(
            user=request.user,
            period=period,
        )

        # Copie et sérialisation pour le format JSON API
        api_data = dict(data)
        api_data["recent_appointments"] = [
            {
                "id": str(rdv.pk),
                "patient_name": rdv.patient.full_name,
                "patient_number": rdv.patient.patient_number,
                "doctor_name": rdv.doctor.full_name,
                "scheduled_at": rdv.scheduled_at.isoformat(),
                "status": rdv.status,
            }
            for rdv in data["recent_appointments"]
        ]
        api_data["recent_patients"] = [
            {
                "id": str(p.pk),
                "full_name": p.full_name,
                "patient_number": p.patient_number,
                "phone_number": p.phone_number,
                "created_at": p.created_at.isoformat(),
            }
            for p in data["recent_patients"]
        ]

        return JsonResponse(api_data, status=200)
