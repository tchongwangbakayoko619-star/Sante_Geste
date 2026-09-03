"""Tests unitaires pour la couche Vues (Views) et routage de l'application users."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_user_register_view_get(client) -> None:
    """Vérifie l'accès GET à la page d'inscription."""
    url = reverse("users:register")
    response = client.get(url)
    assert response.status_code == 200
    assert "users/register.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_user_login_view_get(client) -> None:
    """Vérifie l'accès GET à la page de connexion."""
    url = reverse("users:login")
    response = client.get(url)
    assert response.status_code == 200
    assert "users/login.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_user_login_view_post_valid(client) -> None:
    """Vérifie la connexion réussie via POST."""
    User.objects.create_user(
        email="view-login@santegeste.com",
        password="ValidPassword123!",
    )
    url = reverse("users:login")
    response = client.post(
        url,
        data={"email": "view-login@santegeste.com", "password": "ValidPassword123!"},
    )
    assert response.status_code == 302
    assert response.url == reverse("home")


@pytest.mark.django_db
def test_user_profile_detail_view_authenticated(client) -> None:
    """Vérifie l'accès au profil pour un utilisateur connecté."""
    user = User.objects.create_user(
        email="profile-view@santegeste.com",
        password="ValidPassword123!",
    )
    client.force_login(user)

    url = reverse("users:profile")
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["user"] == user


@pytest.mark.django_db
def test_user_profile_detail_view_anonymous(client) -> None:
    """Vérifie la redirection vers login pour un utilisateur non connecté."""
    url = reverse("users:profile")
    response = client.get(url)
    assert response.status_code == 302
    assert reverse("users:login") in response.url


@pytest.mark.django_db
def test_otp_verification_view_success(client) -> None:
    """Vérifie la validation réussie d'un OTP via la vue OTPVerificationView."""
    from apps.users.services import register_user

    user, raw_code, signed_token = register_user(
        email="otp-view@santegeste.com",
        password="ValidPassword123!",
    )
    session = client.session
    session["otp_signed_token"] = signed_token
    session["otp_user_id"] = str(user.id)
    session.save()

    url = reverse("users:otp-verify")
    response = client.post(url, data={"code": raw_code})
    assert response.status_code == 302
    assert response.url == reverse("users:login")

    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_otp_resend_view(client) -> None:
    """Vérifie le renvoi d'un nouveau code OTP via OTPResendView."""
    user = User.objects.create_user(
        email="resend-view@santegeste.com",
        password="ValidPassword123!",
    )
    session = client.session
    session["otp_user_id"] = str(user.id)
    session.save()

    url = reverse("users:otp-resend")
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse("users:otp-verify")
    assert "otp_signed_token" in client.session

