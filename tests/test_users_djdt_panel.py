from unittest.mock import MagicMock

from debug_toolbar.toolbar import DebugToolbar
from django.contrib.auth import get_user_model
from django.test import RequestFactory
import pytest

from apps.users.panels import UserLogoutPanel

User = get_user_model()


@pytest.mark.django_db
def test_user_logout_panel_properties_authenticated(rf: RequestFactory):
    user = User.objects.create_user(
        email="doctor@santegeste.com",
        password="Password123!",
        first_name="Jean",
        last_name="Dupont",
    )
    request = rf.get("/")
    request.user = user

    toolbar = DebugToolbar(request, lambda req: None)
    panel = UserLogoutPanel(toolbar, lambda req: None)
    panel.process_request(request)

    assert panel.nav_title == "Utilisateur / Auth"
    assert panel.title == "Utilisateur & Déconnexion"
    assert panel.nav_subtitle == "doctor@santegeste.com"

    response = MagicMock()
    panel.generate_stats(request, response)
    stats = panel.get_stats()

    assert stats["is_authenticated"] is True
    assert stats["user"] == user
    assert stats["logout_url"] == "/users/logout/"
    assert stats["login_url"] == "/users/login/"


@pytest.mark.django_db
def test_user_logout_panel_properties_anonymous(rf: RequestFactory):
    from django.contrib.auth.models import AnonymousUser

    request = rf.get("/")
    request.user = AnonymousUser()

    toolbar = DebugToolbar(request, lambda req: None)
    panel = UserLogoutPanel(toolbar, lambda req: None)
    panel.process_request(request)

    assert panel.nav_subtitle == "Déconnecté"

    response = MagicMock()
    panel.generate_stats(request, response)
    stats = panel.get_stats()

    assert stats["is_authenticated"] is False
    assert stats["logout_url"] == "/users/logout/"
    assert stats["login_url"] == "/users/login/"
