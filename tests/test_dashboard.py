"""Tests unitaires et d'intégration pour le module Dashboard."""

from datetime import timedelta
import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.services.dashboard_service import DashboardService
from apps.patients.models import Appointment
from apps.patients.models import Patient
from utils.enums import AppointmentStatusEnum

User = get_user_model()


@pytest.mark.django_db
class TestDashboardService:
    """Tests du service d'agrégation DashboardService."""

    def test_get_dashboard_data_empty_database(self, db):
        """Vérifie que le service retourne des données zéro propres sans erreur quand la BDD est vide."""
        data = DashboardService.get_dashboard_data(user=None, period="today")

        assert data["rdv_today_count"] == 0
        assert data["rdv_confirmed_count"] == 0
        assert data["total_patients"] == 0
        assert data["status_breakdown"]["has_data"] is False
        assert data["weekly_activity"]["has_data"] is False

    def test_get_dashboard_data_with_appointments(self, db):
        """Vérifie le calcul exact des KPIs avec des rendez-vous en base."""
        doctor = User.objects.create_user(
            email="doctor@santegeste.com",
            password="Password123!",
            is_personnel_medical=True,
        )
        patient = Patient.objects.create(
            first_name="Jean",
            last_name="Dupont",
            phone_number="+237699000000",
        )
        now = timezone.now()

        # RDV 1 : Honoré aujourd'hui
        Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            scheduled_at=now,
            status=AppointmentStatusEnum.COMPLETED,
            reason="Consultation de routine",
        )
        # RDV 2 : Annulé aujourd'hui
        Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            scheduled_at=now,
            status=AppointmentStatusEnum.CANCELLED,
            reason="Annulation patient",
        )
        # RDV 3 : Planifié à venir demain
        Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            scheduled_at=now + timedelta(days=1),
            status=AppointmentStatusEnum.SCHEDULED,
            reason="Suivi",
        )

        data = DashboardService.get_dashboard_data(user=doctor, period="today")

        assert data["rdv_today_count"] == 2
        assert data["rdv_confirmed_count"] == 1
        assert data["rdv_cancelled_count"] == 1
        assert data["rdv_upcoming_count"] == 1
        assert data["status_breakdown"]["has_data"] is True
        assert data["weekly_activity"]["has_data"] is True
        assert "planned_path" in data["weekly_activity"]
        assert data["weekly_activity"]["planned_path"].startswith("M 60")
        assert len(data["weekly_activity"]["points"]) == 7
        assert len(data["weekly_activity"]["y_ticks"]) == 5

    def test_get_dashboard_data_periods(self, db):
        """Vérifie le calcul pour les filtres month, year et custom."""
        doctor = User.objects.create_user(
            email="specialist@santegeste.com",
            password="Password123!",
            is_personnel_medical=True,
        )
        patient = Patient.objects.create(
            first_name="Paul",
            last_name="Biya",
            phone_number="+237699000001",
        )
        now = timezone.now()
        Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            scheduled_at=now,
            status=AppointmentStatusEnum.COMPLETED,
            reason="Contrôle périodique",
        )

        # 1. Période Month
        data_month = DashboardService.get_dashboard_data(user=doctor, period="month")
        assert data_month["activity_chart"]["has_data"] is True
        assert len(data_month["activity_chart"]["points"]) in [28, 29, 30, 31]
        assert "Mois" in data_month["period_label"] or "mois" in data_month["period_label"]

        # 2. Période Year
        data_year = DashboardService.get_dashboard_data(user=doctor, period="year")
        assert data_year["activity_chart"]["has_data"] is True
        assert len(data_year["activity_chart"]["points"]) == 12
        assert "Année" in data_year["period_label"] or "année" in data_year["period_label"]

        # 3. Période Custom
        start_custom = now - timedelta(days=5)
        end_custom = now + timedelta(days=5)
        data_custom = DashboardService.get_dashboard_data(
            user=doctor,
            period="custom",
            custom_start=start_custom,
            custom_end=end_custom,
        )
        assert data_custom["activity_chart"]["has_data"] is True
        assert len(data_custom["activity_chart"]["points"]) == 11
        assert "Du " in data_custom["period_label"]


@pytest.mark.django_db
class TestDashboardViews:
    """Tests d'intégration pour les vues HTML et API du Dashboard."""

    def test_dashboard_home_anonymous(self, client):
        """Un utilisateur non authentifié voit la landing page institutionnelle."""
        response = client.get(reverse("home"))
        assert response.status_code == 200
        assert "rdv_today_count" not in response.context

    def test_dashboard_home_authenticated(self, client):
        """Un utilisateur connecté reçoit le contexte du dashboard."""
        user = User.objects.create_user(
            email="agent@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        client.force_login(user)

        response = client.get(reverse("home"))
        assert response.status_code == 200
        assert "rdv_today_count" in response.context
        assert response.context["rdv_today_count"] == 0

    def test_dashboard_home_with_period_filters(self, client):
        """Vérifie le chargement avec les paramètres GET period=month, year et custom."""
        user = User.objects.create_user(
            email="director@santegeste.com",
            password="Password123!",
            is_proprietaire=True,
        )
        client.force_login(user)

        # Test period=month
        resp_m = client.get(reverse("home") + "?period=month")
        assert resp_m.status_code == 200
        assert resp_m.context["period"] == "month"

        # Test period=year
        resp_y = client.get(reverse("home") + "?period=year")
        assert resp_y.status_code == 200
        assert resp_y.context["period"] == "year"

        # Test period=custom avec start_date et end_date
        resp_c = client.get(
            reverse("home") + "?period=custom&start_date=2026-01-01&end_date=2026-01-15"
        )
        assert resp_c.status_code == 200
        assert resp_c.context["period"] == "custom"
        assert resp_c.context["custom_start_date"] == "2026-01-01"
        assert resp_c.context["custom_end_date"] == "2026-01-15"

    def test_dashboard_api_unauthorized(self, client):
        """L'API JSON refuse l'accès anonyme (401)."""
        response = client.get(reverse("dashboard:api_data"))
        assert response.status_code == 401

    def test_dashboard_api_authenticated(self, client):
        """L'API JSON retourne les statistiques réelles pour un utilisateur connecté."""
        user = User.objects.create_user(
            email="accueil@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        client.force_login(user)

        response = client.get(reverse("dashboard:api_data"))
        assert response.status_code == 200
        json_data = response.json()
        assert "rdv_today_count" in json_data
        assert json_data["rdv_today_count"] == 0

    def test_dashboard_api_custom_period(self, client):
        """L'API JSON supporte les requêtes avec période personnalisée."""
        user = User.objects.create_user(
            email="accueil2@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        client.force_login(user)

        response = client.get(
            reverse("dashboard:api_data")
            + "?period=custom&start_date=2026-02-01&end_date=2026-02-14"
        )
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["period"] == "custom"
        assert json_data["custom_start_date"] == "2026-02-01"
        assert json_data["custom_end_date"] == "2026-02-14"
        assert "activity_chart" in json_data

