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


@pytest.mark.django_db
def test_otp_verification_view_via_direct_token_link_without_session_user_id(
    client,
) -> None:
    """Vérifie la validation OTP et l'activation du compte via le lien externe (GET ?token=) avec session vide."""
    from apps.users.services import register_user

    user, raw_code, signed_token = register_user(
        email="external-link@santegeste.com",
        password="ValidPassword123!",
    )
    assert user.is_active is False

    # Le client arrive avec un navigateur neuf / session vide, uniquement le paramètre token
    url = reverse("users:otp-verify") + f"?token={signed_token}"
    response_get = client.get(url)
    assert response_get.status_code == 200

    # Soumission du code
    response_post = client.post(reverse("users:otp-verify"), data={"code": raw_code})
    assert response_post.status_code == 302
    assert response_post.url == reverse("users:login")

    user.refresh_from_db()
    assert user.is_active is True
    assert user.is_verified is True


@pytest.mark.django_db
def test_password_reset_full_view_flow(client) -> None:
    """Vérifie le parcours complet de réinitialisation de mot de passe à travers les vues."""
    from apps.users.services import request_password_reset

    user = User.objects.create_user(
        email="reset-views@santegeste.com",
        password="InitialPassword123!",
    )

    # 1. Demande de réinitialisation
    reset_user, raw_code, signed_token = request_password_reset(
        "reset-views@santegeste.com"
    )
    session = client.session
    session["reset_signed_token"] = signed_token
    session["reset_email"] = user.email
    session.save()

    # 2. Étape 1 : Saisie et validation du code OTP
    url_step1 = reverse("users:password-reset-verify-otp")
    response_step1 = client.post(url_step1, data={"code": raw_code})
    assert response_step1.status_code == 302
    assert response_step1.url == reverse("users:password-reset-confirm")

    # Vérification que l'état de session est bien positionné
    assert client.session.get("reset_otp_verified") is True

    # 3. Étape 2 : Saisie du nouveau mot de passe
    url_step2 = reverse("users:password-reset-confirm")
    response_step2 = client.post(
        url_step2,
        data={
            "password1": "NewComplexPass2026!",
            "password2": "NewComplexPass2026!",
        },
    )
    assert response_step2.status_code == 302
    assert response_step2.url == reverse("users:login")

    # Vérification que l'utilisateur peut se connecter avec son nouveau mot de passe
    user.refresh_from_db()
    assert user.check_password("NewComplexPass2026!") is True

    # Vérification que la session temporaire a été nettoyée sans conserver de secret
    assert "reset_signed_token" not in client.session
    assert "reset_auth_ticket" not in client.session
    assert "reset_otp_code" not in client.session
    assert "reset_otp_verified" not in client.session


@pytest.mark.django_db
def test_user_login_rate_limiting(client) -> None:
    """Vérifie le blocage après 5 tentatives infructueuses (rate-limiting anti-brute-force)."""
    User.objects.create_user(
        email="ratelimit-target@santegeste.com",
        password="RealStrongPassword123!",
    )
    url = reverse("users:login")

    # 5 tentatives erronées consécutives
    for _ in range(5):
        response = client.post(
            url,
            data={"email": "ratelimit-target@santegeste.com", "password": "WrongPassword!"},
        )
        assert response.status_code == 200
        # Vérifie qu'on a le message d'erreur standard anti-énumération
        assert "Adresse email ou mot de passe incorrect." in response.content.decode()

    # 6ème tentative : doit être bloquée par le rate limiter
    response_locked = client.post(
        url,
        data={"email": "ratelimit-target@santegeste.com", "password": "RealStrongPassword123!"},
    )
    assert response_locked.status_code == 200
    content = response_locked.content.decode()
    assert "Trop de tentatives de connexion infructueuses." in content

    # Réinitialisation après succès ou délai
    from utils.rate_limit import reset_login_rate_limit
    from django.test import RequestFactory
    rf = RequestFactory().get(url)
    reset_login_rate_limit(rf, "ratelimit-target@santegeste.com")

