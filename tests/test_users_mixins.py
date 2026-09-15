"""Tests unitaires pour les mixins de l'application users."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.views.generic import View

from apps.users.mixins import (
    AnonymousRequiredMixin,
    PersonnelMedicalRequiredMixin,
    ProprietaireRequiredMixin,
    RedirectToNextOrReferrerMixin,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


class DummyRedirectView(RedirectToNextOrReferrerMixin, View):
    fallback_url = "home"


class DummyMedicalView(PersonnelMedicalRequiredMixin, View):
    pass


class DummyAnonymousView(AnonymousRequiredMixin, View):
    fallback_url = "/dashboard/"


def test_redirect_to_next_param_post_and_get() -> None:
    """Vérifie la priorité du paramètre next dans POST et GET."""
    factory = RequestFactory()

    # Case 1: GET ?next=/dashboard/
    request = factory.get("/login/?next=/dashboard/")
    view = DummyRedirectView()
    view.setup(request)
    assert view.get_redirect_url() == "/dashboard/"

    # Case 2: POST next=/profile/ overrides GET
    request = factory.post("/login/?next=/dashboard/", data={"next": "/profile/"})
    view = DummyRedirectView()
    view.setup(request)
    assert view.get_redirect_url() == "/profile/"


def test_redirect_to_open_redirect_attack_prevention() -> None:
    """Vérifie le rejet des URLs malveillantes externes (Open Redirect Attack)."""
    factory = RequestFactory()

    # Tentative d'Open Redirect externe
    request = factory.get("/login/?next=https://malicious-site.com/steal")
    view = DummyRedirectView()
    view.setup(request)
    # L'URL malveillante doit être rejetée et le fallback '/' utilisé
    assert view.get_redirect_url() == "/"


def test_redirect_to_referrer_fallback() -> None:
    """Vérifie l'utilisation du HTTP_REFERER interne quand next est absent."""
    factory = RequestFactory()

    request = factory.get("/login/", HTTP_REFERER="http://testserver/settings/")
    view = DummyRedirectView()
    view.setup(request)
    assert view.get_redirect_url() == "http://testserver/settings/"


def test_anonymous_required_mixin_redirects_authenticated_user() -> None:
    """Vérifie que AnonymousRequiredMixin redirige les utilisateurs déjà connectés."""
    factory = RequestFactory()
    user = User.objects.create_user(
        email="patient@santegeste.com",
        password="Password123!",
    )

    request = factory.get("/login/?next=/profile/")
    request.user = user

    view = DummyAnonymousView()
    view.setup(request)
    response = view.dispatch(request)

    assert response.status_code == 302
    assert response.url == "/profile/"


def test_personnel_medical_required_mixin_denies_non_medical_user() -> None:
    """Vérifie le rejet (PermissionDenied) pour un utilisateur non médical."""
    factory = RequestFactory()
    user_civil = User.objects.create_user(
        email="civil@santegeste.com",
        password="Password123!",
        is_personnel_medical=False,
    )

    request = factory.get("/medical/dashboard/")
    request.user = user_civil

    view = DummyMedicalView()
    with pytest.raises(PermissionDenied):
        view.dispatch(request)


def test_personnel_medical_required_mixin_allows_medical_user() -> None:
    """Vérifie l'accès autorisé pour un utilisateur ayant le rôle personnel médical."""
    factory = RequestFactory()
    user_doctor = User.objects.create_user(
        email="doctor@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )

    request = factory.get("/medical/dashboard/")
    request.user = user_doctor

    view = DummyMedicalView()

    def mock_dispatch(req: any) -> str:
        return "OK"

    view.get = mock_dispatch
    response = view.dispatch(request)
    assert response == "OK"


def test_redirect_fallback_invalid_route_recovers() -> None:
    """Vérifie que get_redirect_url intercepte NoReverseMatch et renvoie l'URL par défaut sécurisée."""
    factory = RequestFactory()
    request = factory.get("/login/")
    view = DummyRedirectView()
    view.fallback_url = "non_existent_route_404_error"
    view.setup(request)

    # Doit intercepter NoReverseMatch et renvoyer la résolution de 'home' ('/')
    assert view.get_redirect_url() == "/"


def test_role_required_mixin_redirects_when_raise_exception_false() -> None:
    """Vérifie que RoleRequiredMixin redirige vers redirect_url si raise_exception=False."""
    factory = RequestFactory()
    user_civil = User.objects.create_user(
        email="civil2@santegeste.com",
        password="Password123!",
        is_personnel_medical=False,
    )

    class SoftMedicalView(PersonnelMedicalRequiredMixin, View):
        raise_exception = False
        redirect_url = "/dashboard/"

    request = factory.get("/medical/sensitive/")
    request.user = user_civil

    view = SoftMedicalView()
    view.setup(request)
    response = view.dispatch(request)

    assert response.status_code == 302
    assert response.url == "/dashboard/"

