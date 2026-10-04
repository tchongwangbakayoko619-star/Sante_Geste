"""Tests automatisés pour la création et la modification d'une consultation médicale et l'accès login."""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import Appointment, Consultation, Patient, Prestation
from utils.enums import AppointmentStatusEnum, PatientStatusEnum

User = get_user_model()


@pytest.fixture
def medecin(db):
    return User.objects.create_user(
        email="docteur.consultation@cs2health.org",
        password="Password123!",
        first_name="Docteur",
        last_name="Martin",
        is_personnel_medical=True,
    )


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        first_name="Fatou",
        last_name="Traore",
        patient_number="PAT-TEST-001",
        status=PatientStatusEnum.ACTIVE,
    )


@pytest.fixture
def prestation_standard(db):
    obj, _ = Prestation.objects.get_or_create(
        code="CONS-GEN",
        defaults={
            "name": "Consultation Générale Spéciale",
            "standard_price": Decimal("5000.00"),
            "is_active": True,
        },
    )
    return obj


@pytest.mark.django_db
def test_login_page_renders_without_template_error(client):
    """Vérifie que la page de login s'affiche sans aucune TemplateSyntaxError."""
    response = client.get(reverse("users:login"))
    assert response.status_code == 200
    assert "SantéGeste" in response.content.decode()


@pytest.mark.django_db
def test_consultation_creation_and_automatic_prestation(
    client, medecin, patient, prestation_standard
):
    """Vérifie la création complète d'une consultation par un médecin et la redirection."""
    client.force_login(medecin)

    # 1. Accès au formulaire de consultation
    url_get = f"{reverse('patients:consultation_create')}?patient={patient.pk}"
    response = client.get(url_get)
    assert response.status_code == 200
    assert patient.full_name in response.content.decode()

    # 2. Soumission de la consultation avec constantes
    post_data = {
        "patient": str(patient.pk),
        "reason": "Fièvre élevée et céphalées intenses",
        "symptoms": "Température 39°C, frissons, asthénie",
        "diagnosis": "Suspicion de paludisme simple",
        "notes": "Repos strict et hydratation",
        "tension": "12/8",
        "poids": "68",
        "temperature": "39.1",
        "pouls": "84",
        "frequence_respiratoire": "19",
        "vital_param_name[]": ["Tension artérielle", "Poids", "Température"],
        "vital_param_value[]": ["12/8", "68", "39.1"],
        "vital_param_unit[]": ["mmHg", "kg", "°C"],
    }
    response_post = client.post(reverse("patients:consultation_create"), data=post_data)
    if response_post.status_code != 302:
        form = response_post.context.get("form")
        print("\nFORM ERRORS:", form.errors if form else "No form in context")
    assert response_post.status_code == 302

    # Vérification en base de données
    consultation = Consultation.objects.filter(patient=patient).first()
    assert consultation is not None
    assert consultation.doctor == medecin
    assert consultation.reason == "Fièvre élevée et céphalées intenses"
    assert consultation.diagnosis == "Suspicion de paludisme simple"
    assert consultation.vital_signs.get("tension") == "12/8"
    assert consultation.vital_signs.get("temperature") == "39.1"

    # Vérification de la redirection vers le détail
    assert response_post.url == reverse("patients:consultation_detail", kwargs={"pk": consultation.pk})


@pytest.mark.django_db
def test_consultation_list_contains_nouvelle_consultation_button(client, medecin):
    """Vérifie que la liste des consultations affiche le bouton d'action 'Nouvelle Consultation'."""
    client.force_login(medecin)
    response = client.get(reverse("patients:consultation_list"))
    assert response.status_code == 200
    assert reverse("patients:consultation_create") in response.content.decode()
    assert "Nouvelle Consultation" in response.content.decode()
