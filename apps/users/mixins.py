"""Mixins d'authentification, de contrôle d'accès et de redirection pour l'application users."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from apps.users.services.rbac import check_user_roles
from utils.enums import UserRoleEnum


class RedirectToNextOrReferrerMixin:
    """Mixin fournissant des redirections sécurisées contre les attaques d'Open Redirect.

    Ordre de priorité de redirection :
    1. Paramètre `next` dans POST ou GET (si présent et interne)
    2. En-tête `HTTP_REFERER` (si présent et interne)
    3. URL de repli `fallback_url` (ou settings.LOGIN_REDIRECT_URL, ou "home")
    """

    fallback_url: str | None = None
    redirect_authenticated_user: bool = False

    def get_fallback_url(self) -> str:
        """Résout dynamiquement l'URL de repli (fallback)."""
        return self.fallback_url or getattr(
            settings,
            "LOGIN_REDIRECT_URL",
            "home",
        )

    def is_safe_url(self, url: str | None) -> bool:
        """Vérifie si l'URL est interne et sûre (protection contre les failles Open Redirect)."""
        if not url:
            return False
        return url_has_allowed_host_and_scheme(
            url=url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        )

    def is_self_url(self, url: str | None) -> bool:
        """Vérifie si l'URL ciblée correspond à la page actuelle pour éviter les boucles d'infinites de redirection."""
        if not url:
            return False
        from urllib.parse import urlparse

        parsed = urlparse(url)
        target_path = parsed.path.rstrip("/")
        current_path = self.request.path.rstrip("/")
        return target_path == current_path

    def get_redirect_url(self) -> str:
        """Retourne l'URL de redirection prioritaire sécurisée sans boucle circulaire."""
        request: HttpRequest = self.request

        next_url = request.POST.get("next") or request.GET.get("next")
        if self.is_safe_url(next_url) and not self.is_self_url(next_url):
            return next_url

        referrer = request.META.get("HTTP_REFERER")
        if self.is_safe_url(referrer) and not self.is_self_url(referrer):
            return referrer

        fallback = self.get_fallback_url()
        if fallback.startswith("/") or fallback.startswith("http"):
            if not self.is_self_url(fallback):
                return fallback
            return reverse("home")

        resolved = reverse(fallback)
        if not self.is_self_url(resolved):
            return resolved
        return reverse("home")


    def get_success_url(self) -> str:
        """Méthode de redirection par défaut compatible avec FormView / CreateView / UpdateView."""
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and self.is_safe_url(next_url) and not self.is_self_url(next_url):
            return next_url

        if getattr(self, "success_url", None):
            return str(self.success_url)

        return self.get_redirect_url()

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        """Redirige les utilisateurs authentifiés uniquement si redirect_authenticated_user est activé."""
        if not hasattr(self, "request"):
            self.request = request
        if self.redirect_authenticated_user and request.user.is_authenticated:
            return HttpResponseRedirect(self.get_redirect_url())
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class AnonymousRequiredMixin(RedirectToNextOrReferrerMixin):
    """Mixin réservé aux utilisateurs non connectés (ex: vues de connexion/inscription).

    Si l'utilisateur est déjà connecté, il est redirigé vers l'URL de redirection sécurisée.
    """

    redirect_authenticated_user: bool = True

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        """Redirige les utilisateurs connectés avant l'affichage de la vue."""
        if not hasattr(self, "request"):
            self.request = request
        if request.user.is_authenticated:
            return HttpResponseRedirect(self.get_redirect_url())
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class RoleRequiredMixin(AccessMixin):
    """Mixin de base pour restreindre l'accès à une vue selon des rôles applicatifs (RBAC).

    Supporte:
    - required_roles: liste ou séquence de rôles (UserRoleEnum ou str).
    - require_all_roles: bool (True pour ET logique, False pour OU logique).
    - Redirection automatique vers login avec paramètre ?next= si non connecté ou inactif.
    - Levée de PermissionDenied (403) si l'utilisateur est connecté mais non autorisé.
    """

    required_roles: list[UserRoleEnum | str] = []
    require_all_roles: bool = False
    permission_denied_message: str = _(
        "Vous n'avez pas les permissions requises pour accéder à cette ressource."
    )

    def get_required_roles(self) -> list[UserRoleEnum | str]:
        """Retourne la liste des rôles requis pour accéder à la vue."""
        return list(self.required_roles)

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        """Vérifie l'authentification et les rôles attribués à l'utilisateur."""
        if not request.user.is_authenticated or not request.user.is_active:
            return self.handle_no_permission()

        required = self.get_required_roles()
        if required and not check_user_roles(
            request.user, required, require_all=self.require_all_roles
        ):
            raise PermissionDenied(self.get_permission_denied_message())

        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class ProprietaireRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux seuls propriétaires d'établissement (ou superuser)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.PROPRIETAIRE]


class ResponsablePharmacieRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux seuls responsables pharmacie (ou superuser)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.RESPONSABLE_PHARMACIE]


class VendeurPharmacieRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux vendeurs pharmacie (inclus les responsables pharmacie par héritage)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.VENDEUR_PHARMACIE]


class PharmacyAccessRequiredMixin(RoleRequiredMixin):
    """Accès générique au module pharmacie (vendeurs et responsables pharmacie)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.VENDEUR_PHARMACIE]


class CaissierRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux caissiers (ou superuser)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.CAISSIER]


class AgentAccueilRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux agents d'accueil (ou superuser)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.AGENT_ACCUEIL]


class PersonnelMedicalRequiredMixin(RoleRequiredMixin):
    """Restreint l'accès aux membres du personnel médical (ou superuser)."""

    required_roles: list[UserRoleEnum | str] = [UserRoleEnum.PERSONNEL_MEDICAL]


class PatientManagementRequiredMixin(RoleRequiredMixin):
    """Accès à la gestion des patients (agents d'accueil OU personnel médical)."""

    required_roles: list[UserRoleEnum | str] = [
        UserRoleEnum.AGENT_ACCUEIL,
        UserRoleEnum.PERSONNEL_MEDICAL,
    ]
    require_all_roles: bool = False


__all__ = [
    "AgentAccueilRequiredMixin",
    "AnonymousRequiredMixin",
    "CaissierRequiredMixin",
    "PatientManagementRequiredMixin",
    "PersonnelMedicalRequiredMixin",
    "PharmacyAccessRequiredMixin",
    "ProprietaireRequiredMixin",
    "RedirectToNextOrReferrerMixin",
    "ResponsablePharmacieRequiredMixin",
    "RoleRequiredMixin",
    "VendeurPharmacieRequiredMixin",
]