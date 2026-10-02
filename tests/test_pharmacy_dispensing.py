"""Tests d'intégration pour le module Pharmacie et la délivrance des ordonnances."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.patients.models import Consultation, LigneOrdonnance, Ordonnance, Patient
from apps.users.models import User
from utils.enums import UserRoleEnum


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        first_name="Jean",
        last_name="Dupont",
        gender="M",
        phone_number="+237699999999",
    )


@pytest.fixture
def doctor(db):
    user = User.objects.create_user(
        email="doctor_pharmacy@santegeste.com",
        password="Password123!",
        first_name="Doc",
        last_name="House",
        is_personnel_medical=True,
    )
    return user


@pytest.fixture
def pharmacist(db):
    user = User.objects.create_user(
        email="pharmacist@santegeste.com",
        password="Password123!",
        first_name="Pharma",
        last_name="Cien",
        is_responsable_pharmacie=True,
    )
    return user


@pytest.fixture
def consultation(patient, doctor):
    return Consultation.objects.create(
        patient=patient,
        doctor=doctor,
        reason="Consultation test pharmacie",
        diagnosis="Infection",
    )


@pytest.fixture
def ordonnance(consultation, patient, doctor):
    ord_obj = Ordonnance.objects.create(
        consultation=consultation,
        patient=patient,
        doctor=doctor,
        notes="Prendre avec un grand verre d'eau",
        status="PENDING",
    )
    LigneOrdonnance.objects.create(
        ordonnance=ord_obj,
        medication_name="Amoxicilline 1g",
        posology="1 cp 2x/jour",
        duration="7 jours",
        quantity=2,
    )
    return ord_obj


@pytest.mark.django_db
class TestPharmacyDispensing:
    """Validation de la liste et du processus de délivrance des ordonnances à la pharmacie."""

    def test_pharmacy_ordonnance_list_access(self, client, pharmacist, ordonnance):
        client.force_login(pharmacist)
        url = reverse("patients:pharmacy_ordonnance_list")
        response = client.get(url)
        assert response.status_code == 200
        assert ordonnance in response.context["ordonnances"]
        assert "Amoxicilline 1g" in response.content.decode("utf-8")

    def test_pharmacy_dispense_action(self, client, pharmacist, ordonnance):
        client.force_login(pharmacist)
        url = reverse("patients:pharmacy_ordonnance_dispense", kwargs={"pk": ordonnance.pk})
        
        response = client.post(url)
        assert response.status_code == 302
        
        ordonnance.refresh_from_db()
        assert ordonnance.status == "DELIVERED"
        assert ordonnance.delivered_by == pharmacist
        assert ordonnance.delivered_at is not None

    def test_non_pharmacy_staff_access_denied(self, client, patient):
        user = User.objects.create_user(
            email="reception@santegeste.com",
            password="Password123!",
            is_agent_accueil=True,
        )
        client.force_login(user)
        url = reverse("patients:pharmacy_ordonnance_list")
        response = client.get(url)
        assert response.status_code in (403, 302)
