"""Tests complets pour le module patients et rendez-vous (modèles, services, RBAC, vues)."""

from datetime import date
from datetime import datetime
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.services import check_doctor_availability
from apps.patients.services import create_appointment
from apps.patients.services import create_patient
from apps.patients.services import generate_patient_number
from apps.patients.services import search_patients
from apps.patients.services import update_appointment_status
from apps.patients.services import update_patient
from utils.enums import AppointmentStatusEnum
from utils.enums import BloodGroupEnum
from utils.enums import GenderEnum

User = get_user_model()


@pytest.fixture
def agent_accueil(db):
    return User.objects.create_user(
        email="agent.accueil@santegeste.com",
        password="ValidPassword123!",
        first_name="Awa",
        last_name="Kone",
        is_agent_accueil=True,
    )


@pytest.fixture
def doctor_user(db):
    return User.objects.create_user(
        email="dr.traore@santegeste.com",
        password="ValidPassword123!",
        first_name="Ibrahim",
        last_name="Traore",
        is_personnel_medical=True,
    )


@pytest.fixture
def caissier_user(db):
    return User.objects.create_user(
        email="caissier@santegeste.com",
        password="ValidPassword123!",
        first_name="Moussa",
        last_name="Diallo",
        is_caissier=True,
    )


@pytest.fixture
def sample_patient(db):
    return Patient.objects.create(
        patient_number="PAT-2026-0001",
        first_name="Aminata",
        last_name="Touré",
        date_of_birth=date(1995, 5, 20),
        gender=GenderEnum.FEMALE,
        blood_group=BloodGroupEnum.O_POSITIVE,
        phone_number="+2250701020304",
        allergies="Pénicilline",
        chronic_diseases="Asthme modéré",
    )


# ==============================================================================
# 1. Tests des Modèles
# ==============================================================================

@pytest.mark.django_db
def test_patient_model_properties(sample_patient):
    """Vérifie le calcul des propriétés full_name, age, has_critical_alerts."""
    assert sample_patient.full_name == "TOURÉ Aminata"
    assert sample_patient.age is not None
    assert sample_patient.age >= 30
    assert sample_patient.has_critical_alerts is True
    assert "PAT-2026-0001" in str(sample_patient)
    assert sample_patient.get_absolute_url() == reverse(
        "patients:patient_detail", kwargs={"pk": sample_patient.pk}
    )


@pytest.mark.django_db
def test_patient_phone_number_model_validation():
    """Vérifie que la validation du numéro de téléphone au niveau du modèle Patient fonctionne."""
    # Numéro invalide (contient des lettres)
    invalid_patient = Patient(
        patient_number="PAT-2026-9999",
        first_name="Invalid",
        last_name="Phone",
        phone_number="0701020304ABCD",
    )
    with pytest.raises(ValidationError):
        invalid_patient.full_clean()

    # Numéro de contact d'urgence invalide
    invalid_emergency = Patient(
        patient_number="PAT-2026-9998",
        first_name="Invalid",
        last_name="Emergency",
        phone_number="+2250701020304",
        emergency_contact_phone="NOT_A_PHONE",
    )
    with pytest.raises(ValidationError):
        invalid_emergency.full_clean()


@pytest.mark.django_db
def test_patient_soft_delete(sample_patient):
    """Vérifie la suppression logique (Soft Delete) du patient."""
    patient_id = sample_patient.pk
    sample_patient.soft_delete()

    assert sample_patient.is_deleted is True
    assert sample_patient.deleted_at is not None
    # Patient.objects exclut les supprimés logiques
    assert not Patient.objects.filter(pk=patient_id).exists()
    # Patient.all_objects les inclut
    assert Patient.all_objects.filter(pk=patient_id).exists()

    sample_patient.restore()
    assert sample_patient.is_deleted is False
    assert Patient.objects.filter(pk=patient_id).exists()


@pytest.mark.django_db
def test_appointment_model_properties(sample_patient, doctor_user):
    """Vérifie les propriétés d'un rendez-vous médical."""
    now = timezone.now()
    apt = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=now + timedelta(hours=2),
        estimated_duration_minutes=45,
        reason="Consultation de routine",
        status=AppointmentStatusEnum.SCHEDULED,
    )

    assert apt.end_time == apt.scheduled_at + timedelta(minutes=45)
    assert apt.is_past is False
    assert "bg-blue-50" in apt.status_badge_class
    assert "RDV:" in str(apt)


# ==============================================================================
# 2. Tests des Services Métier
# ==============================================================================

@pytest.mark.django_db
def test_generate_patient_number_sequential():
    """Vérifie l'incrémentation séquentielle du matricule PAT-YYYY-XXXX."""
    current_year = timezone.now().year
    prefix = f"PAT-{current_year}-"

    num1 = generate_patient_number()
    assert num1.startswith(prefix)

    Patient.objects.create(
        patient_number=num1,
        first_name="Jean",
        last_name="Kouassi",
        phone_number="+2250102030405",
    )

    num2 = generate_patient_number()
    assert num2.startswith(prefix)
    seq1 = int(num1.split("-")[2])
    seq2 = int(num2.split("-")[2])
    assert seq2 == seq1 + 1


@pytest.mark.django_db
def test_create_and_update_patient_service(agent_accueil):
    """Vérifie la création et la mise à jour via les services métier."""
    patient = create_patient(
        data={
            "first_name": "Fatou",
            "last_name": "Bamba",
            "gender": GenderEnum.FEMALE,
            "phone_number": "+2250505050505",
        },
        created_by=agent_accueil,
    )
    assert patient.patient_number.startswith("PAT-")
    assert patient.created_by == agent_accueil
    assert patient.full_name == "BAMBA Fatou"

    updated = update_patient(
        patient=patient,
        data={"profession": "Architecte", "patient_number": "SHOULD_NOT_CHANGE"},
        updated_by=agent_accueil,
    )
    assert updated.profession == "Architecte"
    assert updated.patient_number == patient.patient_number  # Matricule protégé


@pytest.mark.django_db
def test_search_patients(sample_patient):
    """Vérifie la recherche multi-critères des patients."""
    # Par matricule
    res1 = search_patients("PAT-2026-0001")
    assert sample_patient in res1

    # Par nom
    res2 = search_patients("Touré")
    assert sample_patient in res2

    # Par prénom
    res3 = search_patients("Aminata")
    assert sample_patient in res3

    # Par nom et prénom combinés
    res4 = search_patients("Aminata Touré")
    assert sample_patient in res4

    # Par téléphone
    res5 = search_patients("0701020304")
    assert sample_patient in res5

    # Recherche sans résultat
    res6 = search_patients("Inexistant12345")
    assert not res6.exists()


@pytest.mark.django_db
def test_check_doctor_availability_and_collision(sample_patient, doctor_user):
    """Vérifie la détection de conflit d'agenda pour un praticien."""
    base_time = timezone.now() + timedelta(days=1)
    slot1_start = base_time.replace(hour=10, minute=0, second=0, microsecond=0)

    # Création du premier RDV de 10h00 à 10h30 (30 min)
    apt1 = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start,
        estimated_duration_minutes=30,
        reason="Première consultation",
    )
    assert apt1.status == AppointmentStatusEnum.SCHEDULED

    # Tentative d'un 2ème RDV chevauchant de 10h15 à 10h45 -> Doit être indisponible
    overlap_time = slot1_start + timedelta(minutes=15)
    assert check_doctor_availability(doctor_user, overlap_time, 30) is False

    with pytest.raises(ValidationError):
        create_appointment(
            patient=sample_patient,
            doctor=doctor_user,
            scheduled_at=overlap_time,
            estimated_duration_minutes=30,
            reason="Consultation conflictuelle",
        )

    # Créneau libre à 10h30 (juste après la fin) -> Disponible
    free_time = slot1_start + timedelta(minutes=30)
    assert check_doctor_availability(doctor_user, free_time, 30) is True

    # Si le RDV 1 est annulé, le créneau redevient disponible
    update_appointment_status(appointment=apt1, new_status=AppointmentStatusEnum.CANCELLED)
    assert check_doctor_availability(doctor_user, overlap_time, 30) is True


# ==============================================================================
# 3. Tests de Sécurité RBAC & Vues
# ==============================================================================

@pytest.mark.django_db
def test_patient_list_view_anonymous_redirect(client):
    """Un utilisateur non connecté doit être redirigé vers la page de connexion."""
    url = reverse("patients:patient_list")
    response = client.get(url)
    assert response.status_code == 302
    assert reverse("users:login") in response.url


@pytest.mark.django_db
def test_patient_list_view_unauthorized_role_403(client, caissier_user):
    """Un utilisateur sans rôle accueil ou médical (ex: caissier seul) reçoit un 403."""
    client.force_login(caissier_user)
    url = reverse("patients:patient_list")
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_patient_list_view_authorized_agent_accueil(client, agent_accueil, sample_patient):
    """Un agent d'accueil accède correctement à la liste des patients."""
    client.force_login(agent_accueil)
    url = reverse("patients:patient_list")
    response = client.get(url)
    assert response.status_code == 200
    assert sample_patient.patient_number in response.content.decode("utf-8")


@pytest.mark.django_db
def test_patient_detail_medical_privacy(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie le respect de la confidentialité médicale (RBAC) sur la fiche 360°."""
    url = sample_patient.get_absolute_url()

    # 1. Agent d'accueil : ne doit pas voir le détail médical confidentiel
    client.force_login(agent_accueil)
    resp_agent = client.get(url)
    assert resp_agent.status_code == 200
    assert resp_agent.context["can_view_medical_info"] is False
    content_agent = resp_agent.content.decode("utf-8")
    assert "Confidentialité médicale active" in content_agent

    # 2. Médecin : a accès aux détails des allergies et affections chroniques
    client.force_login(doctor_user)
    resp_doc = client.get(url)
    assert resp_doc.status_code == 200
    assert resp_doc.context["can_view_medical_info"] is True
    content_doc = resp_doc.content.decode("utf-8")
    assert "Pénicilline" in content_doc
    assert "Asthme modéré" in content_doc


@pytest.mark.django_db
def test_patient_create_view_post(client, agent_accueil):
    """Vérifie la création d'un patient via le formulaire web."""
    client.force_login(agent_accueil)
    url = reverse("patients:patient_create")
    post_data = {
        "first_name": "Sékou",
        "last_name": "Fofana",
        "date_of_birth": "1990-01-15",
        "gender": GenderEnum.MALE,
        "blood_group": BloodGroupEnum.B_POSITIVE,
        "phone_number": "+2250102030405",
        "email": "sekou.fofana@example.com",
        "address": "Abidjan, Cocody Angré",
        "profession": "Ingénieur",
        "emergency_contact_name": "Mariam Fofana",
        "emergency_contact_phone": "+2250708091011",
        "emergency_contact_relation": "Épouse",
        "allergies": "",
        "chronic_diseases": "",
    }
    response = client.post(url, data=post_data)
    assert response.status_code == 302

    created_patient = Patient.objects.get(first_name="Sékou", last_name="Fofana")
    assert created_patient.patient_number.startswith("PAT-")
    assert created_patient.created_by == agent_accueil
    assert response.url == created_patient.get_absolute_url()


@pytest.mark.django_db
def test_patient_create_and_update_forbidden_to_doctor(client, doctor_user, sample_patient):
    """Le personnel médical n'a PAS le droit de créer ou modifier un dossier patient (réservé agent d'accueil)."""
    client.force_login(doctor_user)

    # 1. Tentative d'accès à la page de création -> 403
    url_create = reverse("patients:patient_create")
    resp_get = client.get(url_create)
    assert resp_get.status_code == 403

    # 2. Tentative de POST création -> 403
    resp_post = client.post(url_create, data={"first_name": "Docteur", "last_name": "Test"})
    assert resp_post.status_code == 403

    # 3. Tentative d'accès à la modification -> 403
    url_update = reverse("patients:patient_update", kwargs={"pk": sample_patient.pk})
    resp_update = client.get(url_update)
    assert resp_update.status_code == 403


@pytest.mark.django_db
def test_patient_medical_update_view_doctor_allowed_agent_forbidden(client, doctor_user, agent_accueil, sample_patient):
    """La mise à jour clinique est autorisée aux médecins et formellement interdite aux agents d'accueil."""
    url_med = reverse("patients:patient_medical_update", kwargs={"pk": sample_patient.pk})

    # 1. Agent d'accueil tente d'accéder au formulaire médical -> 403
    client.force_login(agent_accueil)
    resp_agent_get = client.get(url_med)
    assert resp_agent_get.status_code == 403

    resp_agent_post = client.post(url_med, data={"allergies": "Tentative non autorisée"})
    assert resp_agent_post.status_code == 403

    # 2. Médecin accède au formulaire médical -> 200
    client.force_login(doctor_user)
    resp_doc_get = client.get(url_med)
    assert resp_doc_get.status_code == 200
    assert "Mise à jour du profil clinique" in resp_doc_get.content.decode("utf-8")

    # 3. Médecin met à jour les allergies et affections chroniques
    post_data = {
        "blood_group": BloodGroupEnum.AB_POSITIVE,
        "allergies": "Pénicilline, Ibuprofène",
        "chronic_diseases": "Diabète type 2, HTA",
    }
    resp_doc_post = client.post(url_med, data=post_data)
    assert resp_doc_post.status_code == 302
    assert resp_doc_post.url == sample_patient.get_absolute_url()

    sample_patient.refresh_from_db()
    assert sample_patient.blood_group == BloodGroupEnum.AB_POSITIVE
    assert "Ibuprofène" in sample_patient.allergies
    assert "Diabète type 2" in sample_patient.chronic_diseases
    assert sample_patient.updated_by == doctor_user




@pytest.mark.django_db
def test_appointment_create_and_status_update_view(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie la planification d'un RDV et le changement de statut via les vues."""
    client.force_login(agent_accueil)
    url_create = reverse("patients:appointment_create")

    scheduled_dt = (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT14:30")
    post_data = {
        "patient": str(sample_patient.pk),
        "doctor": str(doctor_user.pk),
        "scheduled_at": scheduled_dt,
        "estimated_duration_minutes": 30,
        "reason": "Contrôle post-opératoire",
        "notes": "Venir avec le carnet de santé",
    }
    response = client.post(url_create, data=post_data)
    assert response.status_code == 302

    apt = Appointment.objects.get(patient=sample_patient, reason="Contrôle post-opératoire")
    assert apt.status == AppointmentStatusEnum.SCHEDULED

    # Mise à jour du statut : Arrivé en salle d'attente
    url_status = reverse("patients:appointment_status_update", kwargs={"pk": apt.pk})
    resp_status = client.post(
        url_status,
        data={"status": AppointmentStatusEnum.WAITING, "next": url_create},
    )
    assert resp_status.status_code == 302
    apt.refresh_from_db()
    assert apt.status == AppointmentStatusEnum.WAITING


@pytest.mark.django_db
def test_create_patient_retry_on_integrity_error(agent_accueil, monkeypatch):
    """Vérifie que create_patient retente la génération de matricule en cas de collision concurrente."""
    from django.db import IntegrityError

    original_save = Patient.save
    call_count = 0

    def mock_save(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Échoue la première fois avec IntegrityError (collision simulée), puis réussit
        if call_count == 1:
            raise IntegrityError("duplicate key value violates unique constraint")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(Patient, "save", mock_save)

    patient = create_patient(
        data={"first_name": "Test", "last_name": "Retry", "phone_number": "+22501020304"},
        created_by=agent_accueil,
    )
    assert patient.pk is not None
    assert call_count == 2

