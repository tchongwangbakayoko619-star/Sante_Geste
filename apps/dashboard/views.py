"""Vues du module Dashboard (HTML & API JSON)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.services.dashboard_service import DashboardService
from apps.users.mixins import (
    AgentAccueilRequiredMixin,
    CaissierRequiredMixin,
    PersonnelMedicalRequiredMixin,
    ProprietaireRequiredMixin,
    VendeurPharmacieRequiredMixin,
)


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


def _extract_period_params(request) -> tuple[str, datetime | None, datetime | None]:
    """Extrait et normalise les paramètres temporels de requête."""
    period = request.GET.get("period", "today")
    start_date_param = request.GET.get("start_date") or request.GET.get("start")
    end_date_param = request.GET.get("end_date") or request.GET.get("end")

    custom_start, custom_end = parse_custom_dates(start_date_param, end_date_param)
    if period == "custom" and (not custom_start or not custom_end):
        now = timezone.localtime(timezone.now())
        custom_start = (now - timezone.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        custom_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif custom_start and custom_end and period != "custom":
        period = "custom"

    return period, custom_start, custom_end


class DashboardHomeView(TemplateView):
    """Vue principale routant dynamiquement vers le dashboard adapté au rôle ou la vitrine d'accueil anonyme."""

    def get_template_names(self) -> list[str]:
        user = self.request.user
        if not user.is_authenticated:
            return ["pages/home.html"]
        if user.is_proprietaire or user.is_superuser:
            return ["dashboard/proprietaire.html"]
        if user.is_responsable_pharmacie:
            return ["pharmacy/dashboard.html"]
        if user.is_vendeur_pharmacie:
            return ["dashboard/pharmacie_vendeur.html"]
        if user.is_caissier:
            return ["dashboard/caisse.html"]
        if user.is_personnel_medical:
            return ["dashboard/medical.html"]
        if user.is_agent_accueil:
            return ["dashboard/accueil.html"]
        return ["pages/home.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        period, custom_start, custom_end = _extract_period_params(self.request)

        if user.is_proprietaire or user.is_superuser:
            dashboard_data = DashboardService.get_proprietaire_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
        elif user.is_responsable_pharmacie:
            dashboard_data = DashboardService.get_pharmacie_responsable_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
        elif user.is_vendeur_pharmacie:
            dashboard_data = DashboardService.get_pharmacie_vendeur_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
        elif user.is_caissier:
            dashboard_data = DashboardService.get_caisse_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
        elif user.is_personnel_medical:
            dashboard_data = DashboardService.get_medical_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
            # Rétrocompatibilité avec les tests existants vérifiant les clés du dashboard générique
            legacy_data = DashboardService.get_dashboard_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
            for k, v in legacy_data.items():
                if k not in dashboard_data:
                    dashboard_data[k] = v
        elif user.is_agent_accueil:
            dashboard_data = DashboardService.get_accueil_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )
        else:
            dashboard_data = DashboardService.get_dashboard_data(
                user=user, period=period, custom_start=custom_start, custom_end=custom_end
            )

        context.update(dashboard_data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else dashboard_data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else dashboard_data.get("custom_end_date", "")
        return context


# =============================================================================
# VUES DÉDIÉES PAR RÔLE AVEC RESTRICTION STRICTE RBAC (HTTP 403 SUR VIOLATION)
# =============================================================================

class AccueilDashboardView(AgentAccueilRequiredMixin, TemplateView):
    """Tableau de bord dédié à l'Agent d'accueil (Gestion des flux, admissions et planning)."""

    template_name = "dashboard/accueil.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        period, custom_start, custom_end = _extract_period_params(self.request)
        data = DashboardService.get_accueil_data(
            user=self.request.user, period=period, custom_start=custom_start, custom_end=custom_end
        )
        context.update(data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else data.get("custom_end_date", "")
        return context


class MedicalDashboardView(PersonnelMedicalRequiredMixin, TemplateView):
    """Tableau de bord dédié au Personnel médical (Consultations, soins et dossiers)."""

    template_name = "dashboard/medical.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        period, custom_start, custom_end = _extract_period_params(self.request)
        data = DashboardService.get_medical_data(
            user=self.request.user, period=period, custom_start=custom_start, custom_end=custom_end
        )
        context.update(data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else data.get("custom_end_date", "")
        return context


class CaisseDashboardView(CaissierRequiredMixin, TemplateView):
    """Tableau de bord dédié au Caissier (Factures, encaissements et reçus)."""

    template_name = "dashboard/caisse.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        period, custom_start, custom_end = _extract_period_params(self.request)
        data = DashboardService.get_caisse_data(
            user=self.request.user, period=period, custom_start=custom_start, custom_end=custom_end
        )
        context.update(data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else data.get("custom_end_date", "")
        return context


class PharmacieVendeurDashboardView(VendeurPharmacieRequiredMixin, TemplateView):
    """Tableau de bord dédié au Vendeur pharmacie (Ventes au comptoir, délivrances)."""

    template_name = "dashboard/pharmacie_vendeur.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        period, custom_start, custom_end = _extract_period_params(self.request)
        data = DashboardService.get_pharmacie_vendeur_data(
            user=self.request.user, period=period, custom_start=custom_start, custom_end=custom_end
        )
        context.update(data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else data.get("custom_end_date", "")
        return context


class ProprietaireDashboardView(ProprietaireRequiredMixin, TemplateView):
    """Tableau de bord dédié au Propriétaire / Direction (Gouvernance, recettes réelles)."""

    template_name = "dashboard/proprietaire.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        period, custom_start, custom_end = _extract_period_params(self.request)
        data = DashboardService.get_proprietaire_data(
            user=self.request.user, period=period, custom_start=custom_start, custom_end=custom_end
        )
        context.update(data)
        context["custom_start_input"] = custom_start.strftime("%Y-%m-%d") if custom_start else data.get("custom_start_date", "")
        context["custom_end_input"] = custom_end.strftime("%Y-%m-%d") if custom_end else data.get("custom_end_date", "")
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
                "patient_number": getattr(p, "patient_number", ""),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in data.get("recent_patients", [])
        ]
        serialized_data["recent_consultations"] = [
            {
                "id": str(c.id),
                "consultation_date": c.consultation_date.isoformat() if c.consultation_date else None,
                "patient_name": f"{c.patient.first_name} {c.patient.last_name}" if getattr(c, "patient", None) else "",
                "reason": getattr(c, "reason", "") or "",
                "diagnosis": getattr(c, "diagnosis", "") or "",
            }
            for c in data.get("recent_consultations", [])
        ]

        return JsonResponse(serialized_data, status=200)

