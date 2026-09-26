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
