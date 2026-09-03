"""Tests unitaires pour les modèles du domaine utilisateur et les utilitaires OTP."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.users.models import OTP, MedicalProfile
from utils.enums import OTPPurposeEnum
from utils.otp import hash_otp_code, verify_otp_with_lock

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_user_creation_and_properties() -> None:
    """Teste la création d'un utilisateur et ses propriétés d'identité/rôles."""
    user = User.objects.create_user(
        email="doctor@santegeste.com",
        password="Password123!",
        first_name="John",
        last_name="Doe",
        is_personnel_medical=True,
    )
    assert str(user) == "doctor@santegeste.com"
    assert user.full_name == "John Doe"
    assert "personnel_medical" in user.active_roles


def test_user_manager_custom_methods() -> None:
    """Teste les méthodes personnalisées du UserManager (get_by_email, active, verified, personnel_medical)."""
    user = User.objects.create_user(
        email="ManagerTest@SanteGeste.com",
        password="Password123!",
        is_active=True,
        is_verified=True,
        is_personnel_medical=True,
    )

    found = User.objects.get_by_email("managertest@santegeste.com")
    assert found == user

    assert user in User.objects.active()
    assert user in User.objects.verified()
    assert user in User.objects.personnel_medical()
    assert user in User.objects.with_medical_profile()




def test_medical_profile_defensive_validation() -> None:
    """Teste la validation défensive de MedicalProfile (User.is_personnel_medical=True)."""
    user_doctor = User.objects.create_user(
        email="doctor@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    profile = MedicalProfile(
        user=user_doctor,
        specialite="Cardiologue",
        numero_ordre="MED-12345",
    )
    profile.full_clean()
    profile.save()
    assert profile.pk is not None

    user_civil = User.objects.create_user(
        email="civil@santegeste.com",
        password="Password123!",
        is_personnel_medical=False,
    )
    invalid_profile = MedicalProfile(
        user=user_civil,
        specialite="Cardiologue",
    )
    with pytest.raises(ValidationError):
        invalid_profile.full_clean()


def test_otp_active_record_methods() -> None:
    """Teste les méthodes métier Active Record d'OTP (verify_code, mark_as_used, increment_attempts)."""
    user = User.objects.create_user(
        email="patient@santegeste.com",
        password="Password123!",
    )
    raw_code = "654321"
    hashed = hash_otp_code(raw_code)
    future = timezone.now() + timezone.timedelta(minutes=10)

    otp = OTP.objects.create(
        user=user,
        code_hash=hashed,
        purpose=OTPPurposeEnum.REGISTRATION,
        expires_at=future,
    )

    assert otp.verify_code(raw_code) is True
    assert otp.verify_code("000000") is False

    # Incrémentation des tentatives
    otp.increment_attempts()
    assert otp.attempts == 1

    # Marquage comme consommé
    assert otp.is_used is False
    assert otp.used_at is None

    otp.mark_as_used()
    assert otp.is_used is True
    assert otp.used_at is not None
    assert otp.is_valid() is False


def test_verify_otp_with_lock() -> None:
    """Teste la fonction de vérification atomique d'OTP avec verrouillage pessimiste."""
    user = User.objects.create_user(
        email="lock@santegeste.com",
        password="Password123!",
    )
    raw_code = "123456"
    hashed = hash_otp_code(raw_code)
    future = timezone.now() + timezone.timedelta(minutes=10)

    otp = OTP.objects.create(
        user=user,
        code_hash=hashed,
        purpose=OTPPurposeEnum.PASSWORD_RESET,
        expires_at=future,
    )

    # Premier essai avec mauvais code
    assert verify_otp_with_lock(otp.id, "999999") is False

    # Vérification que la tentative a été incrémentée
    otp.refresh_from_db()
    assert otp.attempts == 1
    assert otp.is_used is False

    # Second essai avec bon code
    assert verify_otp_with_lock(otp.id, raw_code) is True

    # Vérification que l'OTP a été consommé de manière atomique
    otp.refresh_from_db()
    assert otp.is_used is True
    assert otp.used_at is not None

    # Troisième essai : doit échouer car déjà utilisé
    assert verify_otp_with_lock(otp.id, raw_code) is False
