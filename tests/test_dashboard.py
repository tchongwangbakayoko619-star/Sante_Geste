"""Tests unitaires et d'intégration pour le module Dashboard."""

from datetime import timedelta
from decimal import Decimal
import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.services.dashboard_service import DashboardService
from apps.patients.models import Appointment, Consultation, Patient
from apps.users.models import MedicalProfile
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

    def test_dashboard_home_medical_staff(self, client):
        """Le dashboard d'un médecin affiche ses métriques cliniques sans boutons administratifs 403."""
        doctor = User.objects.create_user(
            email="dr.martin@santegeste.com",
            first_name="Paul",
            last_name="Martin",
            password="Password123!",
            is_personnel_medical=True,
        )
        MedicalProfile.objects.create(
            user=doctor,
            specialite="Cardiologie",
            numero_ordre="MED-9999",
        )
        client.force_login(doctor)

        response = client.get(reverse("home"))
        assert response.status_code == 200
        assert response.context["is_medical_staff"] is True
        assert response.context["is_doctor_only"] is True
        assert "doctor_consultations_count" in response.context
        assert "recent_consultations" in response.context

        content = response.content.decode("utf-8")
        assert ("Bonjour," in content or "Bonsoir," in content)
        assert "Paul MARTIN" in content
        assert "Cardiologie" in content
        assert "MES RDV DU JOUR" in content
        assert "EN SALLE D'ATTENTE" in content
        # Le bouton d'admission administrative "+ Nouveau patient" qui causerait un 403 ne doit pas être présent
        assert 'href="/patients/nouveau/"' not in content

    def test_dashboard_api_doctor_with_consultation(self, client):
        """L'API JSON sérialise correctement les consultations récentes du médecin."""
        doctor = User.objects.create_user(
            email="dr.clara@santegeste.com",
            first_name="Clara",
            last_name="Oswald",
            password="Password123!",
            is_personnel_medical=True,
        )
        patient = Patient.objects.create(
            first_name="Arthur",
            last_name="Dent",
            phone_number="+237699112233",
        )
        Consultation.objects.create(
            patient=patient,
            doctor=doctor,
            reason="Contrôle tension",
            diagnosis="Normal",
        )
        client.force_login(doctor)

        response = client.get(reverse("dashboard:api_data"))
        assert response.status_code == 200
        json_data = response.json()
        assert "recent_consultations" in json_data
        assert len(json_data["recent_consultations"]) == 1
        assert json_data["recent_consultations"][0]["patient_name"] == "Arthur Dent"
        assert json_data["recent_consultations"][0]["reason"] == "Contrôle tension"


@pytest.mark.django_db
class TestRoleBasedDashboardsRBAC:
    """Vérifie l'accès et les restrictions RBAC strictes (HTTP 403) pour chaque vue de dashboard."""

    def test_accueil_dashboard_access(self, client):
        agent = User.objects.create_user(
            email="agent.accueil@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        medecin = User.objects.create_user(
            email="docteur.test@santegeste.com",
            password="Password123!",
            is_personnel_medical=True,
        )

        client.force_login(agent)
        res = client.get(reverse("dashboard:accueil"))
        assert res.status_code == 200
        assert "appointments_today_count" in res.context

        client.force_login(medecin)
        res_forbidden = client.get(reverse("dashboard:accueil"))
        assert res_forbidden.status_code == 403

    def test_medical_dashboard_access(self, client):
        medecin = User.objects.create_user(
            email="docteur.med@santegeste.com",
            password="Password123!",
            is_personnel_medical=True,
        )
        caissier = User.objects.create_user(
            email="caissier.test@santegeste.com",
            password="Password123!",
            is_caissier=True,
        )

        client.force_login(medecin)
        res = client.get(reverse("dashboard:medical"))
        assert res.status_code == 200
        assert "my_rdv_today" in res.context

        client.force_login(caissier)
        res_forbidden = client.get(reverse("dashboard:medical"))
        assert res_forbidden.status_code == 403

    def test_caisse_dashboard_access(self, client):
        caissier = User.objects.create_user(
            email="caissier.bank@santegeste.com",
            password="Password123!",
            is_caissier=True,
        )
        agent = User.objects.create_user(
            email="agent.test@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        # Test avec une prestation réalisée pour vérifier que le template s'affiche sans VariableDoesNotExist
        from apps.patients.models.prestation import Prestation, PrestationRealisee
        doctor = User.objects.create_user(
            email="dr.presta@santegeste.com",
            password="Password123!",
            is_personnel_medical=True,
        )
        patient = Patient.objects.create(
            first_name="Jean",
            last_name="Presta",
            phone_number="+237699887766",
        )
        prestation = Prestation.objects.create(
            name="Consultation Généraliste",
            code="CONS-001",
            standard_price=Decimal("5000.00"),
        )
        PrestationRealisee.objects.create(
            patient=patient,
            doctor=doctor,
            prestation=prestation,
            unit_price=Decimal("5000.00"),
            quantity=1,
            total_price=Decimal("5000.00"),
        )

        client.force_login(caissier)
        # 1. Accès via / (qui route vers caisse pour le caissier)
        res_home = client.get(reverse("home"))
        assert res_home.status_code == 200
        assert "5000" in res_home.content.decode("utf-8")

        # 2. Accès direct via dashboard:caisse
        res = client.get(reverse("dashboard:caisse"))
        assert res.status_code == 200
        assert "today_collected_amount" in res.context
        assert "5000" in res.content.decode("utf-8")

        client.force_login(agent)
        res_forbidden = client.get(reverse("dashboard:caisse"))
        assert res_forbidden.status_code == 403

    def test_pharmacie_vendeur_dashboard_access(self, client):
        vendeur = User.objects.create_user(
            email="vendeur.pharma@santegeste.com",
            password="Password123!",
            is_vendeur_pharmacie=True,
        )
        caissier = User.objects.create_user(
            email="caissier.pharma@santegeste.com",
            password="Password123!",
            is_caissier=True,
        )

        client.force_login(vendeur)
        res = client.get(reverse("dashboard:pharmacie_vendeur"))
        assert res.status_code == 200
        assert "today_sales_count" in res.context

        client.force_login(caissier)
        res_forbidden = client.get(reverse("dashboard:pharmacie_vendeur"))
        assert res_forbidden.status_code == 403

    def test_proprietaire_dashboard_access(self, client):
        proprietaire = User.objects.create_user(
            email="boss@santegeste.com",
            password="Password123!",
            is_proprietaire=True,
        )
        agent = User.objects.create_user(
            email="agent.boss@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )

        client.force_login(proprietaire)
        res = client.get(reverse("dashboard:proprietaire"))
        assert res.status_code == 200
        assert "total_revenue" in res.context

        client.force_login(agent)
        res_forbidden = client.get(reverse("dashboard:proprietaire"))
        assert res_forbidden.status_code == 403


@pytest.mark.django_db
class TestRoleBasedDashboardServicesAggregation:
    """Vérifie l'exactitude des calculs métier par service sans données fictives."""

    def test_caisse_service_empty_and_populated(self):
        data = DashboardService.get_caisse_data(user=None, period="today")
        assert data["today_collected_amount"] == 0
        assert "0 FCFA" in data["today_collected_formatted"]
        assert data["pending_acts_count"] == 0

    def test_pharmacie_vendeur_service_empty(self):
        data = DashboardService.get_pharmacie_vendeur_data(user=None, period="today")
        assert data["today_sales_count"] == 0
        assert data["today_sales_amount"] == 0
        assert "0 FCFA" in data["today_sales_formatted"]

    def test_pharmacie_responsable_service_empty(self):
        data = DashboardService.get_pharmacie_responsable_data(user=None, period="today")
        assert data["total_products"] == 0
        assert data["stock_total_value"] == 0
        assert "0 FCFA" in data["stock_total_value_formatted"]

    def test_proprietaire_service_empty(self):
        data = DashboardService.get_proprietaire_data(user=None, period="today")
        assert data["total_revenue"] == 0
        assert data["total_caisse"] == 0
        assert data["total_pharmacie"] == 0
        assert data["recovery_rate"] == 0.0


