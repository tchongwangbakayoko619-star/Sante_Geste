"""Tests unitaires pour la couche Service (services) de l'application users."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.users.models import OTP, MedicalProfile
from apps.users.services import (
    PasswordResetError,
    confirm_password_reset,
    confirm_registration_otp,
    register_user,
    request_otp,
    request_password_reset,
    update_medical_profile,
    update_user_profile,
    verify_otp_by_token,
    verify_password_reset_otp,
)
from utils.enums import OTPPurposeEnum

User = get_user_model()


@pytest.mark.django_db
def test_register_user_standard() -> None:
    """Vérifie l'inscription d'un utilisateur standard avec génération OTP."""
    user, raw_code, signed_token = register_user(
        email="patient@santegeste.com",
        password="ComplexPassword123!",
        first_name="Jean",
        last_name="Dupont",
    )

    assert user.email == "patient@santegeste.com"
    assert user.first_name == "Jean"
    assert not user.is_personnel_medical
    assert len(raw_code) == 6
    assert isinstance(signed_token, str)
    assert OTP.objects.filter(user=user, purpose=OTPPurposeEnum.REGISTRATION).exists()


@pytest.mark.django_db
def test_register_user_medical_personnel() -> None:
    """Vérifie l'inscription d'un personnel médical avec création automatique de profil médical."""
    user, raw_code, signed_token = register_user(
        email="doctor@santegeste.com",
        password="DoctorPassword123!",
        first_name="Alice",
        last_name="Mbarga",
        is_personnel_medical=True,
        specialite="Cardiologie",
        numero_ordre="MED-2026-101",
    )

    assert user.is_personnel_medical
    assert hasattr(user, "medical_profile")
    assert user.medical_profile.specialite == "Cardiologie"
    assert user.medical_profile.numero_ordre == "MED-2026-101"


@pytest.mark.django_db
def test_request_and_verify_otp_service() -> None:
    """Vérifie la demande et la validation atomique d'un OTP via la couche service."""
    user = User.objects.create_user(
        email="opt-service@santegeste.com",
        password="PassWord123!",
    )

    otp, raw_code, signed_token = request_otp(user, OTPPurposeEnum.REGISTRATION)

    assert otp.user == user
    assert otp.purpose == OTPPurposeEnum.REGISTRATION

    # Vérification valide
    is_valid = verify_otp_by_token(signed_token, raw_code, OTPPurposeEnum.REGISTRATION)
    assert is_valid is True

    # Deuxième tentative (code déjà consommé)
    is_valid_retry = verify_otp_by_token(
        signed_token, raw_code, OTPPurposeEnum.REGISTRATION
    )
    assert is_valid_retry is False


@pytest.mark.django_db
def test_password_reset_flow_service() -> None:
    """Vérifie le flux complet de réinitialisation de mot de passe via les services."""
    user = User.objects.create_user(
        email="reset-service@santegeste.com",
        password="OldPassword123!",
    )

    # Demande de réinitialisation
    reset_user, raw_code, signed_token = request_password_reset(
        "reset-service@santegeste.com"
    )
    assert reset_user == user
    assert raw_code is not None

    # Confirmation avec nouveau mot de passe
    success = confirm_password_reset(signed_token, raw_code, "NewComplexPass2026!")
    assert success is True

    # Vérification que le nouveau mot de passe fonctionne
    user.refresh_from_db()
    assert user.check_password("NewComplexPass2026!") is True


@pytest.mark.django_db
def test_password_reset_anti_enumeration() -> None:
    """Vérifie que la demande pour un email inexistant ne lève aucune exception (anti-énumération)."""
    user, raw_code, signed_token = request_password_reset("unknown@santegeste.com")
    assert user is None
    assert raw_code is None
    assert signed_token is None


@pytest.mark.django_db
def test_update_user_and_medical_profile_services() -> None:
    """Vérifie la mise à jour atomique des profils utilisateur et médical."""
    user = User.objects.create_user(
        email="profile-service@santegeste.com",
        password="PassWord123!",
        first_name="Marc",
        is_personnel_medical=True,
    )

    updated_user = update_user_profile(
        user=user,
        first_name="Marc-Antoine",
        telephone="+237699999999",
    )
    assert updated_user.first_name == "Marc-Antoine"
    assert updated_user.telephone == "+237699999999"

    medical_profile = update_medical_profile(
        user=user,
        specialite="Pédiatrie",
        numero_ordre="MED-5555",
    )
    assert medical_profile.specialite == "Pédiatrie"
    assert medical_profile.numero_ordre == "MED-5555"


@pytest.mark.django_db
def test_verify_otp_by_user_service() -> None:
    """Vérifie la validation d'un OTP directement par l'instance utilisateur sous verrou BDD."""
    from apps.users.services import verify_otp_by_user

    user = User.objects.create_user(
        email="verify-user-otp@santegeste.com",
        password="PassWord123!",
    )
    otp, raw_code, _ = request_otp(user, OTPPurposeEnum.REGISTRATION)

    # Tentative avec mauvais code
    is_valid_wrong = verify_otp_by_user(user, "000000", OTPPurposeEnum.REGISTRATION)
    assert is_valid_wrong is False
    otp.refresh_from_db()
    assert otp.attempts == 1

    # Tentative avec bon code
    is_valid = verify_otp_by_user(user, raw_code, OTPPurposeEnum.REGISTRATION)
    assert is_valid is True
    otp.refresh_from_db()
    assert otp.is_used is True


@pytest.mark.django_db
def test_password_reset_invalidates_old_otps() -> None:
    """Vérifie que la réinitialisation de mot de passe invalide tous les OTPs de réinitialisation non utilisés."""
    user = User.objects.create_user(
        email="invalidate-otps@santegeste.com",
        password="OldPassword123!",
    )
    reset_user, raw_code, signed_token = request_password_reset(
        "invalidate-otps@santegeste.com"
    )

    # Invalide et confirme le nouveau mot de passe
    success = confirm_password_reset(signed_token, raw_code, "BrandNewPassword2026!")
    assert success is True

    # Tous les OTPs PASSWORD_RESET doivent être marqués comme is_used=True ou supprimés
    assert not OTP.objects.filter(
        user=user, purpose=OTPPurposeEnum.PASSWORD_RESET, is_used=False
    ).exists()


@pytest.mark.django_db
def test_confirm_registration_otp_without_user_id_in_arguments() -> None:
    """Vérifie l'activation de compte lorsque user_id est vide (ex: lien direct)."""
    user, raw_code, signed_token = register_user(
        email="direct-link@santegeste.com",
        password="ValidPassword123!",
    )
    assert user.is_active is False
    assert user.is_verified is False

    # Appel sans user_id explicite (uniquement signed_token)
    is_valid, confirmed_user = confirm_registration_otp(
        signed_token=signed_token,
        user_id="",
        raw_code=raw_code,
    )
    assert is_valid is True
    assert confirmed_user is not None
    assert confirmed_user.id == user.id

    user.refresh_from_db()
    assert user.is_active is True
    assert user.is_verified is True


@pytest.mark.django_db
def test_confirm_password_reset_two_step_flow_service() -> None:
    """Vérifie que confirm_password_reset fonctionne après validation OTP à l'étape 1."""
    user = User.objects.create_user(
        email="two-step-reset@santegeste.com",
        password="OldPassword123!",
    )
    _, raw_code, signed_token = request_password_reset("two-step-reset@santegeste.com")

    # Étape 1 : Validation de l'OTP (qui le marque comme utilisé)
    step1_valid = verify_password_reset_otp(signed_token, raw_code)
    assert step1_valid is True

    # Étape 2 : Confirmation avec nouveau mot de passe
    success = confirm_password_reset(signed_token, raw_code, "NewSecurePassword2026!")
    assert success is True

    user.refresh_from_db()
    assert user.check_password("NewSecurePassword2026!") is True


@pytest.mark.django_db
def test_confirm_password_reset_wrong_code_fails() -> None:
    """Vérifie que confirm_password_reset échoue si le code est incorrect."""
    User.objects.create_user(
        email="wrong-code-reset@santegeste.com",
        password="OldPassword123!",
    )
    _, _, signed_token = request_password_reset("wrong-code-reset@santegeste.com")

    with pytest.raises(PasswordResetError):
        confirm_password_reset(signed_token, "000000", "NewSecurePassword2026!")
