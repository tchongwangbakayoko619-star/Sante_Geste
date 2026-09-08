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
        "role": "personnel_medical",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.email == "newpatient@santegeste.com"
    assert user.first_name == "Jean"
    assert user.is_personnel_medical is True


def test_user_register_form_missing_role() -> None:
    """Vérifie que l'inscription est rejetée si le rôle obligatoire n'est pas fourni."""
    data = {
        "email": "norole@santegeste.com",
        "first_name": "Jean",
        "last_name": "Dupont",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert not form.is_valid()
    assert "role" in form.errors


def test_user_register_form_telephone_with_letters() -> None:
    """Vérifie que l'inscription est rejetée si le numéro de téléphone contient des lettres."""
    data = {
        "email": "badphone@santegeste.com",
        "first_name": "Jean",
        "last_name": "Dupont",
        "telephone": "+237699abc99",
        "role": "personnel_medical",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert not form.is_valid()
    assert "telephone" in form.errors


def test_user_register_form_cameroon_phone_normalization() -> None:
    """Vérifie qu'un numéro local camerounais à 9 chiffres est normalisé au format E.164."""
    data = {
        "email": "localphone@santegeste.com",
        "first_name": "Samuel",
        "last_name": "Eto'o",
        "telephone": "6 70 12 34 56",
        "role": "personnel_medical",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["telephone"] == "+237670123456"


def test_user_register_form_cameroon_invalid_phone() -> None:
    """Vérifie le rejet d'un numéro camerounais avec préfixe ou longueur invalide."""
    # Préfixe invalide (7 au lieu de 6, 2 ou 3)
    data_bad_prefix = {
        "email": "badprefix@santegeste.com",
        "first_name": "Test",
        "last_name": "User",
        "telephone": "700000000",
        "role": "personnel_medical",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form = UserRegisterForm(data=data_bad_prefix)
    assert not form.is_valid()
    assert "telephone" in form.errors

    # Longueur invalide (8 chiffres)
    data_bad_len = {
        "email": "badlen@santegeste.com",
        "first_name": "Test",
        "last_name": "User",
        "telephone": "69999999",
        "role": "personnel_medical",
        "password1": "ComplexPass123!",
        "password2": "ComplexPass123!",
    }
    form2 = UserRegisterForm(data=data_bad_len)
    assert not form2.is_valid()
    assert "telephone" in form2.errors


def test_user_register_form_duplicate_email() -> None:
    """Vérifie le rejet d'une inscription si l'email existe déjà."""
    User.objects.create_user(email="existing@santegeste.com", password="Password123!")

    data = {
        "email": "EXISTING@santegeste.com",
        "first_name": "Jean",
        "last_name": "Dupont",
        "role": "personnel_medical",
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
