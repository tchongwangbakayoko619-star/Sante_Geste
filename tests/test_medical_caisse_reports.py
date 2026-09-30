"""Tests unitaires et d'intégration pour les fonctionnalités Consultation, Prestations, Caisse et Rapports."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import Appointment
from apps.patients.models import Consultation
from apps.patients.models import Facture
from apps.patients.models import Ordonnance
from apps.patients.models import Patient
from apps.patients.models import Prestation
from apps.patients.models import PrestationRealisee
from utils.enums import AppointmentStatusEnum
from utils.enums import PatientStatusEnum

User = get_user_model()


@pytest.fixture
def agent_accueil(db):
    return User.objects.create_user(
        email="agent@cs2health.org",
        password="Password123!",
        first_name="Agent",
        last_name="Accueil",
        is_agent_accueil=True,
    )


@pytest.fixture
def doctor_1(db):
    return User.objects.create_user(
        email="doc1@cs2health.org",
        password="Password123!",
        first_name="Jean",
        last_name="Valois",
        is_personnel_medical=True,
    )


@pytest.fixture
def doctor_2(db):
    return User.objects.create_user(
        email="doc2@cs2health.org",
        password="Password123!",
        first_name="Marie",
        last_name="Curie",
        is_personnel_medical=True,
    )


@pytest.fixture
def caissier(db):
    return User.objects.create_user(
        email="caisse@cs2health.org",
        password="Password123!",
        first_name="Paul",
        last_name="Caisse",
        is_caissier=True,
    )


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        first_name="Kouamé",
        last_name="Adjoua",
        gender="F",
        phone_number="+237690000000",
        status=PatientStatusEnum.ACTIVE,
    )


@pytest.fixture
def prestation(db):
    p, _ = Prestation.objects.get_or_create(
        name="Consultation Générale",
        defaults={
            "code": "CONS_GEN",
            "standard_price": 10000.00,
        },
    )
    return p


@pytest.mark.django_db
def test_parcours_complet_rdv_consultation_caisse(client, agent_accueil, doctor_1, caissier, patient, prestation):
    # 1. Agent d'accueil planifie un RDV
    client.force_login(agent_accueil)
    rdv = Appointment.objects.create(
        patient=patient,
        doctor=doctor_1,
        scheduled_at=timezone.now() + timezone.timedelta(hours=2),
        reason="Consultation de routine",
        status=AppointmentStatusEnum.SCHEDULED,
    )
    assert rdv.pk is not None

    # 2. Personnel médical consulte "Mes rendez-vous"
    client.force_login(doctor_1)
    response = client.get(reverse("patients:my_appointments"))
    assert response.status_code == 200
    assert rdv.patient.full_name in response.content.decode()

    # 3. Personnel médical démarre la consultation
    response = client.post(
        f"{reverse('patients:consultation_create')}?appointment={rdv.pk}",
        {
            "reason": "Consultation de routine",
            "symptoms": "Fièvre modérée",
            "tension": "12/8",
            "poids": "68",
            "temperature": "38.1",
            "pouls": "78",
            "diagnosis": "Paludisme simple",
            "status": "COMPLETED",
        },
    )
    assert response.status_code == 302
    consultation = Consultation.objects.get(appointment=rdv)
    assert consultation.diagnosis == "Paludisme simple"

    # Vérifie que le RDV a été marqué comme terminé
    rdv.refresh_from_db()
    assert rdv.status == AppointmentStatusEnum.COMPLETED

    # 4. Ajout d'une prestation réalisée
    response = client.post(
        reverse("patients:prestation_realisee_create", kwargs={"pk": consultation.pk}),
        {
            "prestation": prestation.pk,
            "quantity": 1,
            "unit_price": 10000,
        },
    )
    assert response.status_code == 302
    prestation_realisee = PrestationRealisee.objects.filter(consultation=consultation, prestation=prestation).first()
    assert prestation_realisee is not None
    assert prestation_realisee.status == "EN_ATTENTE_CAISSE"

    # 5. Création d'une ordonnance
    response = client.post(
        reverse("patients:ordonnance_create", kwargs={"pk": consultation.pk}),
        {
            "notes": "Prendre pendant les repas",
            "medication_name": ["Artemether 80mg"],
            "posology": ["1 cp 2x/jour"],
            "duration": ["3 jours"],
            "quantity": ["1"],
        },
    )
    assert response.status_code == 302
    assert Ordonnance.objects.filter(consultation=consultation).exists()

    # 6. Module Caisse : le caissier voit l'acte et génère la facture
    client.force_login(caissier)
    response = client.get(reverse("patients:caisse_pending_list"))
    assert response.status_code == 200
    assert patient.full_name in response.content.decode()

    # Génération de la facture
    response = client.post(reverse("patients:facture_create", kwargs={"patient_id": patient.pk}))
    assert response.status_code == 302
    facture = Facture.objects.get(patient=patient)
    assert facture.total_amount == 20000.00
    assert facture.status == "UNPAID"

    # Enregistrement du paiement à la caisse
    response = client.post(
        reverse("patients:paiement_create", kwargs={"pk": facture.pk}),
        {
            "amount": 20000,
            "payment_method": "ESPECES",
            "notes": "Paiement au comptoir",
        },
    )
    assert response.status_code == 302
    facture.refresh_from_db()
    assert facture.status == "PAID"
    assert facture.paid_amount == 20000.00


@pytest.mark.django_db
def test_rbac_doctor_access_restriction(client, doctor_1, doctor_2, patient):
    # Dr. 2 crée un rendez-vous et une consultation
    client.force_login(doctor_2)
    rdv_doc2 = Appointment.objects.create(
        patient=patient,
        doctor=doctor_2,
        scheduled_at=timezone.now(),
        reason="Examen gynéco",
    )
    consultation = Consultation.objects.create(
        appointment=rdv_doc2,
        patient=patient,
        doctor=doctor_2,
        reason="Examen gynéco",
        diagnosis="Normal",
    )

    # Dr. 1 essaie d'ouvrir la consultation de Dr. 2 -> Accès Refusé (HTTP 403)
    client.force_login(doctor_1)
    response = client.get(reverse("patients:consultation_detail", kwargs={"pk": consultation.pk}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_reports_access_and_export(client, agent_accueil, caissier):
    client.force_login(agent_accueil)

    # 1. Portail des rapports
    response = client.get(reverse("dashboard:reports_home"))
    assert response.status_code == 200

    # 2. Consultation d'un rapport
    response = client.get(reverse("dashboard:report_detail", kwargs={"report_code": "rdv_admin"}))
    assert response.status_code == 200

    # 3. Exports CSV, Excel, PDF
    response_csv = client.get(reverse("dashboard:report_export", kwargs={"report_code": "rdv_admin", "fmt": "csv"}))
    assert response_csv.status_code == 200
    assert response_csv["Content-Type"].startswith("text/csv")

    response_excel = client.get(reverse("dashboard:report_export", kwargs={"report_code": "rdv_admin", "fmt": "excel"}))
    assert response_excel.status_code == 200

    response_pdf = client.get(reverse("dashboard:report_export", kwargs={"report_code": "rdv_admin", "fmt": "pdf"}))
    assert response_pdf.status_code == 200
