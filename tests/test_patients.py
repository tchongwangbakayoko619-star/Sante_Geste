"""Tests complets pour le module patients et rendez-vous (modèles, services, RBAC, vues)."""

from datetime import date
from datetime import datetime
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone

from apps.patients.forms import AppointmentCancelForm
from apps.patients.forms import AppointmentForm
from apps.patients.forms import PatientForm
from apps.patients.models import Allergen
from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.models import PatientAllergy
from apps.patients.presenters import AppointmentPresenter
from apps.patients.presenters import PatientPresenter
from apps.patients.services import add_patient_allergy
from apps.patients.services import cancel_appointment
from apps.patients.services import check_allergy_contraindication
from apps.patients.services import check_doctor_availability
from apps.patients.services import create_appointment
from apps.patients.services import create_patient
from apps.patients.services import generate_patient_number
from apps.patients.services import get_appointment_daily_stats
from apps.patients.services import remove_patient_allergy
from apps.patients.services import reschedule_appointment
from apps.patients.services import search_patients
from apps.patients.services import update_appointment_status
from apps.patients.services import update_patient
from utils.enums import AllergenCategoryEnum
from utils.enums import AllergyCriticalityEnum
from utils.enums import AllergyVerificationStatusEnum
from utils.enums import AppointmentStatusEnum
from utils.enums import BloodGroupEnum
from utils.enums import GenderEnum
from utils.enums import PatientStatusEnum

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
def test_patient_form_phone_validation():
    """Vérifie la validation des téléphones (principal et urgence) dans PatientForm."""
    valid_data = {
        "first_name": "Test",
        "last_name": "Form",
        "gender": GenderEnum.MALE,
        "blood_group": BloodGroupEnum.A_POSITIVE,
        "phone_number": "+237699000000",
        "emergency_contact_phone": "",
    }
    # Formulaire valide avec contact d'urgence vide
    form = PatientForm(data=valid_data)
    assert form.is_valid(), f"Form errors: {form.errors}"

    # Formulaire valide avec contact d'urgence valide
    valid_data["emergency_contact_phone"] = "+2250701020304"
    form = PatientForm(data=valid_data)
    assert form.is_valid()

    # Formulaire invalide avec contact d'urgence erroné
    valid_data["emergency_contact_phone"] = "NOT_A_VALID_PHONE"
    form = PatientForm(data=valid_data)
    assert not form.is_valid()
    assert "emergency_contact_phone" in form.errors


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
    assert not hasattr(apt, "status_badge_class")
    assert not hasattr(sample_patient, "status_badge_class")
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


@pytest.mark.django_db
def test_appointment_model_anti_double_booking(sample_patient, doctor_user):
    """Vérifie que le modèle Appointment empêche le double-booking au niveau ORM/save()."""
    base_time = timezone.now() + timedelta(days=2)
    slot1_start = base_time.replace(hour=14, minute=0, second=0, microsecond=0)

    # 1. Création d'un premier rendez-vous de 14h00 à 14h30 (30 min)
    apt1 = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start,
        estimated_duration_minutes=30,
        reason="Consultation initiale",
    )
    assert apt1.pk is not None

    # 2. Tentative de création d'un rendez-vous chevauchant en amont (13h45 - 14h15)
    overlap_before = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start - timedelta(minutes=15),
        estimated_duration_minutes=30,
        reason="Consultation amont chevauchante",
    )
    with pytest.raises(ValidationError) as exc_info:
        overlap_before.save()
    assert "scheduled_at" in exc_info.value.message_dict

    # 3. Tentative de création d'un rendez-vous chevauchant en aval (14h15 - 14h45)
    overlap_after = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start + timedelta(minutes=15),
        estimated_duration_minutes=30,
        reason="Consultation aval chevauchante",
    )
    with pytest.raises(ValidationError) as exc_info:
        overlap_after.save()
    assert "scheduled_at" in exc_info.value.message_dict

    # 4. Tentative de création d'un rendez-vous englobant (13h50 - 14h40)
    overlap_encompassing = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start - timedelta(minutes=10),
        estimated_duration_minutes=50,
        reason="Consultation englobante",
    )
    with pytest.raises(ValidationError) as exc_info:
        overlap_encompassing.save()
    assert "scheduled_at" in exc_info.value.message_dict

    # 5. Créneaux strictement contigus (13h30-14h00 et 14h30-15h00) -> Autorisés sans conflit
    adjacent_before = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start - timedelta(minutes=30),
        estimated_duration_minutes=30,
        reason="Consultation contiguë avant",
    )
    adjacent_after = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start + timedelta(minutes=30),
        estimated_duration_minutes=30,
        reason="Consultation contiguë après",
    )
    assert adjacent_before.pk is not None
    assert adjacent_after.pk is not None

    # 6. Mise à jour du RDV 1 sans modifier l'horaire (ex: notes ou motif) -> Pas de faux conflit
    apt1.reason = "Motif modifié"
    apt1.save()
    apt1.refresh_from_db()
    assert apt1.reason == "Motif modifié"

    # 7. Un RDV avec statut CANCELLED ne doit pas bloquer un créneau
    apt1.status = AppointmentStatusEnum.CANCELLED
    apt1.save()

    # Création sur le créneau libéré (14h00 - 14h30) -> Doit réussir
    rebooked = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=slot1_start,
        estimated_duration_minutes=30,
        reason="Nouveau rendez-vous sur créneau libéré",
    )
    assert rebooked.pk is not None


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
        data={"first_name": "Test", "last_name": "Retry", "phone_number": "+237699112233"},
        created_by=agent_accueil,
    )
    assert patient.pk is not None
    assert call_count == 2


# ==============================================================================
# 4. Tests des Allergies Codifiées & Contre-indications Pharmaceutiques (CDSS)
# ==============================================================================

@pytest.mark.django_db
def test_allergen_and_patient_allergy_model(sample_patient, doctor_user):
    """Vérifie le modèle Allergen, PatientAllergy et les contraintes relationnelles."""
    allergen = Allergen.objects.create(
        name="Amoxicilline Trihydrate",
        category=AllergenCategoryEnum.MEDICATION,
        atc_code="J01CA04",
        cross_reactivity_group="Bêta-lactamines",
    )
    assert str(allergen) == "Amoxicilline Trihydrate [J01CA04]"

    # Contrainte d'unicité sur le nom
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            Allergen.objects.create(name="Amoxicilline Trihydrate")

    # Association au patient
    pa = PatientAllergy.objects.create(
        patient=sample_patient,
        allergen=allergen,
        criticality=AllergyCriticalityEnum.HIGH,
        reaction="Œdème de Quincke",
        created_by=doctor_user,
    )
    assert pa.has_life_threatening_risk is True
    assert sample_patient.has_critical_alerts is True
    assert allergen in [a.allergen for a in sample_patient.critical_allergies]

    # Contrainte unique (patient, allergen)
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            PatientAllergy.objects.create(
                patient=sample_patient,
                allergen=allergen,
                criticality=AllergyCriticalityEnum.LOW,
            )


@pytest.mark.django_db
def test_patient_allergy_services(sample_patient, doctor_user):
    """Vérifie l'ajout, la suppression et la détection d'interactions/contre-indications."""
    allergen_peni = Allergen.objects.create(
        name="Pénicilline G",
        category=AllergenCategoryEnum.MEDICATION,
        atc_code="J01CE01",
        cross_reactivity_group="Bêta-lactamines",
    )

    # 1. Ajout via service
    pa = add_patient_allergy(
        patient=sample_patient,
        allergen=allergen_peni,
        criticality=AllergyCriticalityEnum.HIGH,
        reaction="Choc anaphylactique",
        created_by=doctor_user,
    )
    assert pa.pk is not None
    assert pa.created_by == doctor_user

    # 2. Détection par code ATC partiel (J01C)
    contra_atc = check_allergy_contraindication(
        patient=sample_patient,
        atc_code="J01C",
    )
    assert len(contra_atc) == 1
    assert contra_atc[0].allergen == allergen_peni

    # 3. Détection par groupe de réactivité croisée (Bêta-lactamines)
    contra_group = check_allergy_contraindication(
        patient=sample_patient,
        cross_reactivity_group="bêta-lactamines",
    )
    assert len(contra_group) == 1

    # 4. Détection par nom de substance
    contra_name = check_allergy_contraindication(
        patient=sample_patient,
        substance_name="Pénicilline",
    )
    assert len(contra_name) == 1

    # Absence de contre-indication pour un médicament sans rapport (ex: Paracétamol)
    contra_none = check_allergy_contraindication(
        patient=sample_patient,
        atc_code="N02BE01",
        cross_reactivity_group="Analgésiques",
        substance_name="Paracétamol",
    )
    assert len(contra_none) == 0

    # 5. Suppression de l'allergie
    removed = remove_patient_allergy(patient=sample_patient, allergen=allergen_peni)
    assert removed is True
    assert not sample_patient.patient_allergies.exists()


@pytest.mark.django_db
def test_patient_allergy_views_rbac(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie le contrôle d'accès RBAC des vues de gestion des allergies codifiées."""
    allergen = Allergen.objects.create(
        name="Sulfaméthoxazole",
        category=AllergenCategoryEnum.MEDICATION,
        atc_code="J01EE01",
    )
    url_add = reverse("patients:patient_allergy_create", kwargs={"pk": sample_patient.pk})

    # 1. Agent d'accueil : 403 Forbidden
    client.force_login(agent_accueil)
    resp_agent = client.post(url_add, data={"allergen": str(allergen.pk), "criticality": AllergyCriticalityEnum.HIGH})
    assert resp_agent.status_code == 403

    # 2. Médecin : Ajout autorisé
    client.force_login(doctor_user)
    resp_doc = client.post(
        url_add,
        data={
            "allergen": str(allergen.pk),
            "criticality": AllergyCriticalityEnum.HIGH,
            "verification_status": AllergyVerificationStatusEnum.CONFIRMED,
            "reaction": "Toxidermie",
        },
    )
    assert resp_doc.status_code == 302
    created_allergy = PatientAllergy.objects.get(patient=sample_patient, allergen=allergen)
    assert created_allergy.reaction == "Toxidermie"
    assert created_allergy.created_by == doctor_user

    # 3. Médecin : Suppression autorisée
    url_del = reverse(
        "patients:patient_allergy_delete",
        kwargs={"pk": sample_patient.pk, "allergy_id": created_allergy.pk},
    )
    resp_del = client.post(url_del)
    assert resp_del.status_code == 302
    assert not PatientAllergy.objects.filter(pk=created_allergy.pk).exists()


# ==============================================================================
# 5. Tests du Cycle de Vie Patient (PatientStatusEnum vs SoftDelete)
# ==============================================================================

@pytest.mark.django_db
def test_patient_status_lifecycle_and_appointment_blocking(sample_patient, doctor_user):
    """Vérifie le cycle de vie du patient (Actif, Décédé, Archivé) et l'interdiction de prise de RDV."""
    # 1. Par défaut, un patient créé est ACTIVE et is_active est True
    assert sample_patient.status == PatientStatusEnum.ACTIVE
    assert sample_patient.is_active is True
    assert sample_patient.deceased_at is None

    # 2. Déclaration du décès : status=DECEASED auto-remplit deceased_at
    sample_patient.status = PatientStatusEnum.DECEASED
    sample_patient.save()
    sample_patient.refresh_from_db()
    assert sample_patient.status == PatientStatusEnum.DECEASED
    assert sample_patient.is_active is False
    assert sample_patient.deceased_at is not None

    # 3. Tentative de programmation d'un RDV pour un patient décédé -> Rejeté par Appointment.clean()
    base_time = timezone.now() + timedelta(days=3)
    apt_deceased = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time,
        reason="Consultation interdite",
    )
    with pytest.raises(ValidationError) as exc_info:
        apt_deceased.save()
    assert "patient" in exc_info.value.message_dict
    assert "décédé" in str(exc_info.value.message_dict["patient"][0]).lower()

    # 4. Patient Archivé / Transféré -> RDV également rejeté tant que non réactivé
    sample_patient.status = PatientStatusEnum.ARCHIVED
    sample_patient.save()
    sample_patient.refresh_from_db()
    assert sample_patient.is_active is False
    assert sample_patient.deceased_at is None  # deceased_at automatiquement nettoyé quand réactivé/changé

    apt_archived = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time,
        reason="Consultation patient archivé",
    )
    with pytest.raises(ValidationError) as exc_archived:
        apt_archived.save()
    assert "patient" in exc_archived.value.message_dict
    assert "réactiver" in str(exc_archived.value.message_dict["patient"][0]).lower()

    # 5. Réactivation du dossier -> La prise de RDV redevient autorisée
    sample_patient.status = PatientStatusEnum.ACTIVE
    sample_patient.save()
    sample_patient.refresh_from_db()
    assert sample_patient.is_active is True

    valid_apt = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time,
        reason="Consultation valide après réactivation",
    )
    assert valid_apt.pk is not None


# ==============================================================================
# 6. Tests de Normalisation Téléphonique E.164 & Résolution de Recherche
# ==============================================================================

@pytest.mark.django_db
def test_patient_phone_e164_normalization_on_save_and_form():
    """Vérifie que les numéros de téléphone sont normalisés en E.164 à l'enregistrement et dans les formulaires."""
    # 1. Enregistrement direct via ORM : format local avec espaces -> normalisé en E.164 (+237...)
    patient = Patient(
        first_name="Paul",
        last_name="Biya",
        phone_number="699 11 22 33",
        emergency_contact_phone="237 677 44 55 66",
    )
    patient.save()
    patient.refresh_from_db()
    assert patient.phone_number == "+237699112233"
    assert patient.emergency_contact_phone == "+237677445566"

    # 2. Formulaire PatientForm : nettoyage et normalisation
    form = PatientForm(
        data={
            "first_name": "Samuel",
            "last_name": "Eto'o",
            "gender": GenderEnum.MALE,
            "blood_group": BloodGroupEnum.O_POSITIVE,
            "phone_number": "690 00 00 00",
            "emergency_contact_phone": "+237 670 00 00 00",
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert form.cleaned_data["phone_number"] == "+237690000000"
    assert form.cleaned_data["emergency_contact_phone"] == "+237670000000"

    saved_patient = form.save()
    assert saved_patient.phone_number == "+237690000000"
    assert saved_patient.emergency_contact_phone == "+237670000000"


@pytest.mark.django_db
def test_search_patients_by_various_phone_formats():
    """Vérifie que la recherche retrouve le patient quel que soit le format téléphonique saisi."""
    patient = Patient.objects.create(
        first_name="Chantal",
        last_name="Ayissi",
        phone_number="+237698765432",
        emergency_contact_phone="+237671234567",
    )

    # 1. Recherche avec le numéro local à 9 chiffres sans indicatif
    res_local = search_patients("698765432")
    assert patient in res_local

    # 2. Recherche avec espaces
    res_spaces = search_patients("698 76 54 32")
    assert patient in res_spaces

    # 3. Recherche avec indicatif international
    res_intl = search_patients("+237698765432")
    assert patient in res_intl

    # 4. Recherche par contact d'urgence avec espaces
    res_emergency = search_patients("671 23 45 67")
    assert patient in res_emergency


# ==============================================================================
# 7. Tests Gestion du Départ Praticien & Intégrité Médico-Légale (models.PROTECT)
# ==============================================================================

@pytest.mark.django_db
def test_practitioner_hard_deletion_blocked_by_protect(sample_patient, doctor_user):
    """Vérifie qu'un praticien ayant un historique de RDV ne peut JAMAIS être supprimé physiquement de la base."""
    # 1. Création d'un RDV associé au médecin
    apt = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=timezone.now() + timedelta(days=2),
        reason="Consultation initiale",
    )
    assert apt.doctor == doctor_user

    # 2. Tentative de suppression physique directe de l'instance User -> Levée de ProtectedError
    with pytest.raises(ProtectedError) as exc_info:
        doctor_user.delete()

    assert "historique de consultations" in str(exc_info.value) or "protected foreign keys" in str(exc_info.value)
    assert apt in exc_info.value.protected_objects

    # 3. Tentative de suppression via QuerySet bulk delete -> Bloquée également
    with pytest.raises(ProtectedError):
        User.objects.filter(pk=doctor_user.pk).delete()

    # Le praticien et son rendez-vous existent toujours intacts en base
    doctor_user.refresh_from_db()
    assert doctor_user.pk is not None
    assert Appointment.objects.filter(pk=apt.pk).exists()


@pytest.mark.django_db
def test_practitioner_departure_via_is_active_false_blocks_new_appointments(sample_patient, doctor_user):
    """Vérifie que le départ d'un praticien se gère via is_active=False et bloque toute nouvelle prise de RDV."""
    # 1. Historique préalable valide
    past_time = timezone.now() - timedelta(days=10)
    historic_apt = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=past_time,
        reason="Consultation historique",
        status=AppointmentStatusEnum.COMPLETED,
    )

    # 2. Départ du médecin : désactivation du compte
    doctor_user.deactivate()
    doctor_user.refresh_from_db()
    assert doctor_user.is_active is False

    # 3. check_doctor_availability retourne False pour un médecin inactif
    future_time = timezone.now() + timedelta(days=3)
    assert check_doctor_availability(doctor_user, future_time) is False

    # 4. create_appointment service refuse la prise de rendez-vous
    with pytest.raises(ValidationError) as exc_service:
        create_appointment(
            patient=sample_patient,
            doctor=doctor_user,
            scheduled_at=future_time,
            reason="Tentative RDV praticien parti",
        )
    assert "inactif ou ayant quitté" in str(exc_service.value).lower()

    # 5. Modèle Appointment.clean() bloque également au niveau ORM
    apt_invalid = Appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=future_time,
        reason="Tentative ORM direct",
    )
    with pytest.raises(ValidationError) as exc_clean:
        apt_invalid.clean()
    assert "doctor" in exc_clean.value.message_dict
    assert "n'est plus en activité" in str(exc_clean.value.message_dict["doctor"][0]).lower()

    # 6. Formulaire AppointmentForm : rejet à la validation
    form = AppointmentForm(
        data={
            "patient": sample_patient.pk,
            "doctor": doctor_user.pk,
            "scheduled_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            "estimated_duration_minutes": 30,
            "reason": "Consultation formulaire",
        }
    )
    assert not form.is_valid()
    assert "doctor" in form.errors

    # 7. L'historique clinique passé reste 100% accessible et consultable
    historic_apt.refresh_from_db()
    assert historic_apt.doctor == doctor_user
    assert historic_apt.doctor.full_name == doctor_user.full_name
    assert historic_apt.status == AppointmentStatusEnum.COMPLETED

    # 8. Mise à jour de notes sur un RDV existant reste autorisée sans bloquer
    historic_apt.notes = "Dossier archivé suite au départ du Dr."
    historic_apt.save(update_fields=["notes", "updated_at"])
    historic_apt.refresh_from_db()
    assert historic_apt.notes == "Dossier archivé suite au départ du Dr."


# ==============================================================================
# 8. Tests de la Couche Présentation (Presenters & Template Tags)
# ==============================================================================

@pytest.mark.django_db
def test_presenters_and_template_tags_separation(sample_patient, doctor_user):
    """Vérifie la stricte séparation entre le domaine et la présentation (Tailwind CSS)."""
    from django.template import Context, Template
    from apps.patients.presenters import (
        AppointmentPresenter,
        PatientPresenter,
        get_appointment_status_badge_class,
        get_patient_status_badge_class,
        get_patient_status_dot_class,
    )

    # 1. Vérification que les modèles de domaine n'ont AUCUNE classe de style Tailwind
    apt = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=timezone.now() + timedelta(hours=4),
        reason="Consultation présentation",
        status=AppointmentStatusEnum.SCHEDULED,
    )
    assert not hasattr(apt, "status_badge_class")
    assert not hasattr(sample_patient, "status_badge_class")

    # 2. AppointmentPresenter
    apt_presenter = AppointmentPresenter(apt)
    assert "bg-blue-50" in apt_presenter.status_badge_class
    assert "text-blue-700" in apt_presenter.status_badge_class

    # Vérification des autres statuts de RDV
    apt.status = AppointmentStatusEnum.WAITING
    assert "bg-amber-50" in apt_presenter.status_badge_class
    apt.status = AppointmentStatusEnum.IN_CONSULTATION
    assert "bg-purple-50" in apt_presenter.status_badge_class
    apt.status = AppointmentStatusEnum.COMPLETED
    assert "bg-emerald-50" in apt_presenter.status_badge_class
    apt.status = AppointmentStatusEnum.CANCELLED
    assert "bg-rose-50" in apt_presenter.status_badge_class

    # 3. PatientPresenter
    pat_presenter = PatientPresenter(sample_patient)
    assert "bg-emerald-50" in pat_presenter.status_badge_class
    assert pat_presenter.status_dot_class == "bg-emerald-500"

    sample_patient.status = PatientStatusEnum.DECEASED
    assert "bg-rose-50" in pat_presenter.status_badge_class
    assert pat_presenter.status_dot_class == "bg-rose-500"

    # 4. Rendu dans les templates Django via le template tag library patient_tags
    template_str = (
        "{% load patient_tags %}"
        "badge_apt:{{ apt|appointment_status_badge_class }}|"
        "badge_pat:{{ patient|patient_status_badge_class }}|"
        "dot_pat:{{ patient|patient_status_dot_class }}"
    )
    template = Template(template_str)
    rendered = template.render(Context({"apt": apt, "patient": sample_patient}))

    assert "badge_apt:bg-rose-50 text-rose-700" in rendered
    assert "badge_pat:bg-rose-50 text-rose-700" in rendered
    assert "dot_pat:bg-rose-500" in rendered


# ==============================================================================
# 9. Tests Habilitation Médicale Obligatoire & Non-Masquage des Erreurs Téléphone
# ==============================================================================

@pytest.mark.django_db
def test_appointment_requires_is_personnel_medical(sample_patient, agent_accueil, doctor_user):
    """Vérifie qu'un rendez-vous exige impérativement un praticien ayant is_personnel_medical=True."""
    future_time = timezone.now() + timedelta(days=2)

    # 1. Vérification au niveau du service create_appointment
    with pytest.raises(ValidationError) as exc_service:
        create_appointment(
            patient=sample_patient,
            doctor=agent_accueil,
            scheduled_at=future_time,
            reason="Tentative consultation avec agent accueil",
        )
    assert "pas habilité comme personnel médical" in str(exc_service.value).lower()

    # 2. Vérification au niveau du modèle Appointment.clean()
    invalid_apt = Appointment(
        patient=sample_patient,
        doctor=agent_accueil,
        scheduled_at=future_time,
        reason="Tentative modèle ORM",
    )
    with pytest.raises(ValidationError) as exc_clean:
        invalid_apt.clean()
    assert "doctor" in exc_clean.value.message_dict
    assert "pas habilité comme personnel médical" in str(exc_clean.value.message_dict["doctor"][0]).lower()

    # 3. Vérification au niveau du formulaire AppointmentForm
    form = AppointmentForm(
        data={
            "patient": sample_patient.pk,
            "doctor": agent_accueil.pk,
            "scheduled_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            "estimated_duration_minutes": 30,
            "reason": "Consultation formulaire",
        }
    )
    assert not form.is_valid()
    assert "doctor" in form.errors


@pytest.mark.django_db
def test_phone_normalization_errors_not_masked_on_save():
    """Vérifie que les erreurs de normalisation téléphonique ne sont plus masquées par pass à l'enregistrement."""
    # 1. Téléphone principal invalide avec lettres
    p1 = Patient(
        first_name="Jean",
        last_name="Invalide",
        phone_number="699000000XYZ",
    )
    with pytest.raises(ValidationError) as exc_p1:
        p1.save()
    assert "phone_number" in exc_p1.value.message_dict

    # 2. Contact d'urgence invalide
    p2 = Patient(
        first_name="Marie",
        last_name="Invalide",
        phone_number="+237699112233",
        emergency_contact_phone="PAS_UN_NUMERO",
    )
    with pytest.raises(ValidationError) as exc_p2:
        p2.save()
    assert "emergency_contact_phone" in exc_p2.value.message_dict


# ==============================================================================
# 10. Tests des Opérations Métier AppointmentService (Reschedule, Cancel, Stats)
# ==============================================================================

@pytest.mark.django_db
def test_appointment_service_reschedule_cancel_and_stats(sample_patient, doctor_user):
    """Vérifie les opérations métier complètes dans AppointmentService avec concurrence sérialisée."""
    base_time = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # 1. Création initiale
    apt = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time,
        estimated_duration_minutes=30,
        reason="Consultation initiale",
    )
    assert apt.status == AppointmentStatusEnum.SCHEDULED

    # 2. Reschedule vers un nouveau créneau disponible
    new_time = base_time + timedelta(hours=3)
    updated_apt = reschedule_appointment(
        appointment=apt,
        new_scheduled_at=new_time,
        new_duration_minutes=45,
        notes="Reporté à la demande du patient",
    )
    assert updated_apt.scheduled_at == new_time
    assert updated_apt.estimated_duration_minutes == 45
    assert updated_apt.notes == "Reporté à la demande du patient"

    # 3. Création d'un second RDV
    apt2 = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time + timedelta(hours=1),
        estimated_duration_minutes=30,
        reason="Deuxième consultation",
    )

    # 4. Tentative de reschedule créant un conflit d'agenda -> Rejeté par reschedule_appointment
    with pytest.raises(ValidationError):
        reschedule_appointment(
            appointment=updated_apt,
            new_scheduled_at=apt2.scheduled_at,
            new_duration_minutes=30,
        )

    # 5. Annulation via cancel_appointment -> Libère le créneau
    cancelled = cancel_appointment(
        appointment=apt2,
        cancellation_reason="Imprévu patient",
    )
    assert cancelled.status == AppointmentStatusEnum.CANCELLED
    assert "[ANNULÉ] Imprévu patient" in cancelled.notes

    # Le créneau de apt2 est désormais libre : updated_apt peut être déplacé dessus
    reassigned = reschedule_appointment(
        appointment=updated_apt,
        new_scheduled_at=apt2.scheduled_at,
        new_duration_minutes=30,
    )
    assert reassigned.scheduled_at == apt2.scheduled_at

    # 6. Statistiques journalières via get_appointment_daily_stats
    stats = get_appointment_daily_stats(target_date=reassigned.scheduled_at)
    assert "today_count" in stats
    assert "waiting_count" in stats
    assert "in_consultation_count" in stats
    assert "completed_count" in stats
    assert stats["today_count"] >= 1


@pytest.mark.django_db
def test_query_transform_tag(rf):
    """Vérifie le bon fonctionnement du template tag query_transform avec conservation des filtres."""
    from apps.patients.templatetags.patient_tags import query_transform

    request = rf.get("/patients/?q=Dupont&status=active&gender=M&page=1")
    context = {"request": request}

    # Changement de page : conserve q, status, gender et met à jour page=2
    result = query_transform(context, page=2)
    assert "page=2" in result
    assert "q=Dupont" in result
    assert "status=active" in result
    assert "gender=M" in result

    # Suppression d'un paramètre en passant None ou chaîne vide
    result_removed = query_transform(context, status=None, page=3)
    assert "status=" not in result_removed
    assert "page=3" in result_removed
    assert "q=Dupont" in result_removed


@pytest.mark.django_db
def test_patient_list_view_multi_filters(client, agent_accueil):
    """Vérifie les filtres multi-critères (statut, genre, groupe sanguin, tri) sur PatientListView."""
    client.force_login(agent_accueil)

    p1 = Patient.objects.create(
        patient_number="PAT-TEST-0001",
        first_name="Amadou",
        last_name="Diallo",
        date_of_birth=date(1990, 1, 1),
        gender=GenderEnum.MALE,
        blood_group=BloodGroupEnum.A_POSITIVE,
        status=PatientStatusEnum.ACTIVE,
    )
    p2 = Patient.objects.create(
        patient_number="PAT-TEST-0002",
        first_name="Fatou",
        last_name="Traore",
        date_of_birth=date(1995, 5, 10),
        gender=GenderEnum.FEMALE,
        blood_group=BloodGroupEnum.O_POSITIVE,
        status=PatientStatusEnum.ARCHIVED,
    )

    url = reverse("patients:patient_list")

    # 1. Filtre par statut = ACTIVE
    resp = client.get(url, {"status": PatientStatusEnum.ACTIVE})
    assert resp.status_code == 200
    patients = list(resp.context["patients"])
    assert p1 in patients
    assert p2 not in patients
    assert resp.context["active_filters_count"] == 1

    # 2. Filtre par genre = FEMALE
    resp = client.get(url, {"gender": GenderEnum.FEMALE})
    assert resp.status_code == 200
    patients = list(resp.context["patients"])
    assert p2 in patients
    assert p1 not in patients

    # 3. Filtre par groupe sanguin = A+
    resp = client.get(url, {"blood_group": BloodGroupEnum.A_POSITIVE})
    assert resp.status_code == 200
    patients = list(resp.context["patients"])
    assert p1 in patients
    assert p2 not in patients

    # 4. Tri par nom A-Z
    resp = client.get(url, {"ordering": "last_name"})
    assert resp.status_code == 200
    patients = list(resp.context["patients"])
    assert len(patients) >= 2
    # Diallo vient avant Traore
    assert patients[0].last_name <= patients[1].last_name

    # 5. Recherche textuelle 'Fatou'
    resp = client.get(url, {"q": "Fatou"})
    assert resp.status_code == 200
    patients = list(resp.context["patients"])
    assert p2 in patients
    assert p1 not in patients


@pytest.mark.django_db
def test_appointment_list_view_multi_filters(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie la recherche et les filtres multi-critères (médecin, statut, date précise) sur AppointmentListView."""
    client.force_login(agent_accueil)

    other_doctor = User.objects.create_user(
        email="dr.kone@santegeste.com",
        password="ValidPassword123!",
        first_name="Seydou",
        last_name="Kone",
        is_personnel_medical=True,
    )

    base_time = timezone.now() + timedelta(days=2)
    apt1 = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=base_time.replace(hour=9, minute=0, second=0, microsecond=0),
        reason="Consultation Cardiologie",
    )
    apt2 = create_appointment(
        patient=sample_patient,
        doctor=other_doctor,
        scheduled_at=base_time.replace(hour=11, minute=0, second=0, microsecond=0),
        reason="Bilan Pédiatrique",
    )

    url = reverse("patients:appointment_list")

    # 1. Filtre date_filter=all + doctor=doctor_user.id
    resp = client.get(url, {"date_filter": "all", "doctor": doctor_user.id})
    assert resp.status_code == 200
    appointments = list(resp.context["appointments"])
    assert apt1 in appointments
    assert apt2 not in appointments
    assert resp.context["active_filters_count"] >= 1

    # 2. Recherche par motif 'Cardiologie'
    resp = client.get(url, {"date_filter": "all", "q": "Cardiologie"})
    assert resp.status_code == 200
    appointments = list(resp.context["appointments"])
    assert apt1 in appointments
    assert apt2 not in appointments

    # 3. Filtre par date exacte
    exact_date_str = base_time.strftime("%Y-%m-%d")
    resp = client.get(url, {"date": exact_date_str})
    assert resp.status_code == 200
    appointments = list(resp.context["appointments"])
    assert apt1 in appointments
    assert apt2 in appointments

    # 4. Filtre par statut clinique
    apt2.status = AppointmentStatusEnum.IN_CONSULTATION
    apt2.save()
    resp_status = client.get(url, {"status": AppointmentStatusEnum.IN_CONSULTATION})
    assert resp_status.status_code == 200
    assert apt2 in list(resp_status.context["appointments"])
    assert apt1 not in list(resp_status.context["appointments"])

    # 5. Vérification de la présence de la barre de filtre harmonisée (identique à patients)
    content = resp.content.decode("utf-8")
    assert "appointment-filters-form" in content
    assert 'name="q"' in content
    assert 'name="status"' in content
    assert 'name="doctor"' in content
    assert 'name="date_filter"' in content
    assert 'name="date"' in content
    assert 'name="ordering"' in content


@pytest.mark.django_db
def test_appointment_list_planning_du_jour_vs_agenda_complet(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie la différence fondamentale entre 'Planning du jour' (?date_filter=today) et 'Agenda complet' (?date_filter=all / défaut)."""
    client.force_login(agent_accueil)
    now = timezone.now()

    # RDV d'aujourd'hui
    apt_today = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=now.replace(hour=14, minute=0, second=0, microsecond=0),
        reason="Consultation du jour",
    )
    # RDV dans 3 jours
    apt_future = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=(now + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0),
        reason="Consultation future",
    )
    # RDV il y a 3 jours
    apt_past = Appointment.objects.create(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=(now - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0),
        reason="Consultation passée",
        status=AppointmentStatusEnum.COMPLETED,
    )

    url = reverse("patients:appointment_list")

    # 1. Filtre Aujourd'hui (?date_filter=today) : uniquement le rendez-vous d'aujourd'hui
    resp_today = client.get(url, {"date_filter": "today"})
    assert resp_today.status_code == 200
    today_appointments = list(resp_today.context["appointments"])
    assert apt_today in today_appointments
    assert apt_future not in today_appointments
    assert apt_past not in today_appointments
    assert resp_today.context["date_filter"] == "today"
    assert "Agenda des Rendez-vous" in resp_today.content.decode("utf-8")
    assert "Planning du Jour" not in resp_today.content.decode("utf-8")
    assert "Planning du jour" not in resp_today.content.decode("utf-8")

    # 2. Agenda complet (par défaut sans paramètre) : TOUS les rendez-vous
    resp_default = client.get(url)
    assert resp_default.status_code == 200
    all_appointments = list(resp_default.context["appointments"])
    assert apt_today in all_appointments
    assert apt_future in all_appointments
    assert apt_past in all_appointments
    assert resp_default.context["date_filter"] == "all"
    assert "Agenda Complet" in resp_default.content.decode("utf-8")

    # 3. Agenda complet (explicite date_filter=all) : TOUS les rendez-vous
    resp_all = client.get(url, {"date_filter": "all"})
    assert resp_all.status_code == 200
    all_explicit = list(resp_all.context["appointments"])
    assert apt_today in all_explicit
    assert apt_future in all_explicit
    assert apt_past in all_explicit
    assert resp_all.context["date_filter"] == "all"


# ==============================================================================
# Tests du Formulaire et de la Vue d'Annulation de Rendez-vous
# ==============================================================================


def test_appointment_cancel_form_valid():
    """Vérifie qu'un motif prédéfini et la confirmation cochée rendent le formulaire valide."""
    form = AppointmentCancelForm(
        data={
            "reason_category": "patient_request",
            "reason_detail": "Voyage imprévu du patient",
            "confirm_cancellation": True,
        }
    )
    assert form.is_valid()
    assert "Demande ou empêchement du patient : Voyage imprévu du patient" in form.get_cancellation_reason()


def test_appointment_cancel_form_other_requires_detail():
    """Vérifie que la catégorie 'Autre motif' exige des précisions textuelles."""
    # Sans détail -> Invalide
    form = AppointmentCancelForm(
        data={
            "reason_category": "other",
            "reason_detail": "",
            "confirm_cancellation": True,
        }
    )
    assert not form.is_valid()
    assert "reason_detail" in form.errors

    # Avec détail -> Valide
    form_valid = AppointmentCancelForm(
        data={
            "reason_category": "other",
            "reason_detail": "Panne d'électricité dans le bloc",
            "confirm_cancellation": True,
        }
    )
    assert form_valid.is_valid()
    assert form_valid.get_cancellation_reason() == "Panne d'électricité dans le bloc"


def test_appointment_cancel_form_requires_confirmation():
    """Vérifie que la case de confirmation est obligatoire."""
    form = AppointmentCancelForm(
        data={
            "reason_category": "doctor_unavailable",
            "confirm_cancellation": False,
        }
    )
    assert not form.is_valid()
    assert "confirm_cancellation" in form.errors


@pytest.mark.django_db
def test_appointment_cancel_view_get(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie l'affichage du formulaire de validation d'annulation via GET."""
    client.force_login(agent_accueil)
    scheduled_dt = timezone.now() + timedelta(days=1)
    apt = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=scheduled_dt,
        reason="Consultation test annulation",
    )
    url = reverse("patients:appointment_cancel", kwargs={"pk": apt.pk})

    response = client.get(url)
    assert response.status_code == 200
    assert "patients/appointment_cancel.html" in [t.name for t in response.templates]
    assert response.context["appointment"] == apt
    assert response.context["patient"] == sample_patient
    content = response.content.decode("utf-8")
    assert "Annulation de Rendez-vous" in content
    assert sample_patient.full_name in content
    assert "Conserver le rendez-vous" in content
    assert "Confirmer l'annulation" in content


@pytest.mark.django_db
def test_appointment_cancel_view_post_success(client, agent_accueil, doctor_user, sample_patient):
    """Vérifie la validation de l'annulation d'un rendez-vous via POST."""
    client.force_login(agent_accueil)
    scheduled_dt = timezone.now() + timedelta(days=1)
    apt = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=scheduled_dt,
        reason="Consultation ORL",
        notes="Notes initiales",
    )
    url = reverse("patients:appointment_cancel", kwargs={"pk": apt.pk})

    post_data = {
        "reason_category": "patient_request",
        "reason_detail": "Patient alité à domicile",
        "confirm_cancellation": True,
        "next": reverse("patients:appointment_list"),
    }
    response = client.post(url, data=post_data)
    assert response.status_code == 302
    assert response.url == reverse("patients:appointment_list")

    apt.refresh_from_db()
    assert apt.status == AppointmentStatusEnum.CANCELLED
    assert "[ANNULÉ]" in apt.notes
    assert "Patient alité à domicile" in apt.notes
    assert apt.updated_by == agent_accueil


@pytest.mark.django_db
def test_appointment_cancel_view_cannot_cancel_already_cancelled_or_completed(
    client, agent_accueil, doctor_user, sample_patient
):
    """Vérifie qu'on ne peut pas ré-annuler un rendez-vous déjà annulé ou terminé."""
    client.force_login(agent_accueil)
    scheduled_dt = timezone.now() + timedelta(days=1)
    apt = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=scheduled_dt,
        reason="Consultation déjà annulée",
    )
    apt.status = AppointmentStatusEnum.CANCELLED
    apt.save()

    url = reverse("patients:appointment_cancel", kwargs={"pk": apt.pk})
    response = client.get(url)
    assert response.status_code == 302  # Redirection avec message d'information

    # Idem pour un rendez-vous déjà terminé
    apt.status = AppointmentStatusEnum.COMPLETED
    apt.save()
    response = client.get(url)
    assert response.status_code == 302


@pytest.mark.django_db
def test_appointment_cancel_view_rbac(client, caissier_user, doctor_user, sample_patient):
    """Vérifie que les utilisateurs non autorisés (ex: caissier) reçoivent une interdiction 403."""
    client.force_login(caissier_user)
    scheduled_dt = timezone.now() + timedelta(days=1)
    apt = create_appointment(
        patient=sample_patient,
        doctor=doctor_user,
        scheduled_at=scheduled_dt,
        reason="Consultation sécurité",
    )
    url = reverse("patients:appointment_cancel", kwargs={"pk": apt.pk})

    response = client.get(url)
    assert response.status_code == 403








