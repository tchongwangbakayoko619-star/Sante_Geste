"""Tests unitaires pour les formulaires de l'application users."""

import pytest
from django.contrib.auth import get_user_model

from apps.users.forms import (
    MedicalProfileForm,
    OTPVerificationForm,
    UserLoginForm,
    UserRegisterForm,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_user_register_form_valid_data() -> None:
    """Vérifie qu'un formulaire de création avec des données valides est accepté."""
    data = {
        "email": "newpatient@santegeste.com",
        "first_name": "Jean",
        "last_name": "Dupont",
        "telephone": "+237699999999",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.email == "newpatient@santegeste.com"
    assert user.first_name == "Jean"


def test_user_register_form_duplicate_email() -> None:
    """Vérifie le rejet d'une inscription si l'email existe déjà."""
    User.objects.create_user(email="existing@santegeste.com", password="Password123!")

    data = {
        "email": "EXISTING@santegeste.com",
        "first_name": "Jean",
        "last_name": "Dupont",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert not form.is_valid()
    assert "email" in form.errors


def test_user_login_form_authentication() -> None:
    """Vérifie que le formulaire de connexion valide correctement les identifiants."""
    user = User.objects.create_user(
        email="login@santegeste.com",
        password="ValidPassword123!",
    )

    # Identifiants valides
    form_valid = UserLoginForm(
        data={"email": "login@santegeste.com", "password": "ValidPassword123!"}
    )
    assert form_valid.is_valid(), form_valid.errors
    assert form_valid.get_user() == user

    # Mot de passe incorrect
    form_invalid = UserLoginForm(
        data={"email": "login@santegeste.com", "password": "WrongPassword!"}
    )
    assert not form_invalid.is_valid()


def test_otp_verification_form() -> None:
    """Vérifie le nettoyage et la validation du code OTP."""
    # Code valide 6 chiffres
    form_valid = OTPVerificationForm(data={"code": " 123456 "})
    assert form_valid.is_valid(), form_valid.errors
    assert form_valid.cleaned_data["code"] == "123456"

    # Code avec lettres
    form_invalid = OTPVerificationForm(data={"code": "12345a"})
    assert not form_invalid.is_valid()
    assert "code" in form_invalid.errors



def test_medical_profile_form() -> None:
    """Vérifie la création d'un profil médical via formulaire."""
    data = {
        "specialite": "Chirurgien",
        "numero_ordre": "MED-9999",
    }
    form = MedicalProfileForm(data=data)
    assert form.is_valid(), form.errors
