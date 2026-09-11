"""Décorateurs de contrôle d'accès basé sur les rôles (RBAC) pour les Function-Based Views (FBV)."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from apps.users.services.rbac import check_user_roles
from utils.enums import UserRoleEnum

ViewFunc = Callable[..., HttpResponse]


def role_required(
    *roles: UserRoleEnum | str,
    require_all: bool = False,
    login_url: str | None = None,
    redirect_url: str | None = None,
    raise_exception: bool = True,
    message: str | None = None,
) -> Callable[[ViewFunc], ViewFunc]:
    """Décorateur pour restreindre l'accès à une FBV selon un ou plusieurs rôles.

    - Si l'utilisateur n'est pas connecté ou inactif, il est redirigé vers le login (avec ?next=).
    - Si l'utilisateur est connecté mais ne possède pas les rôles requis :
      - Si `raise_exception=True` (défaut strict), lève `PermissionDenied` (erreur 403 HTTP).
      - Si `raise_exception=False`, redirige vers `redirect_url` ou `settings.LOGIN_REDIRECT_URL`
        (sans boucle de connexion/next sur la page interdite).
    """
    error_message = message or _(
        "Vous n'avez pas les permissions requises pour accéder à cette ressource."
    )

    def decorator(view_func: ViewFunc) -> ViewFunc:
        @wraps(view_func)
        def _wrapped_view(
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> HttpResponse:
            user = getattr(request, "user", None)

            if (
                not user
                or not getattr(user, "is_authenticated", False)
                or not getattr(user, "is_active", False)
            ):
                return redirect_to_login(request.get_full_path(), login_url)

            if roles and not check_user_roles(
                user, roles, require_all=require_all
            ):
                if raise_exception:
                    raise PermissionDenied(error_message)

                target = (
                    redirect_url
                    or login_url
                    or getattr(settings, "LOGIN_REDIRECT_URL", "home")
                )
                return redirect(target)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def _create_role_decorator(
    *roles: UserRoleEnum | str,
    require_all: bool = False,
) -> Callable[..., Any]:
    """Fabrique de décorateur supportant la syntaxe avec ou sans parenthèses :
    @decorateur ou @decorateur(raise_exception=False, redirect_url=...)
    """

    def decorator_factory(
        view_func: ViewFunc | None = None,
        *,
        login_url: str | None = None,
        redirect_url: str | None = None,
        raise_exception: bool = True,
        message: str | None = None,
    ) -> Any:
        dec = role_required(
            *roles,
            require_all=require_all,
            login_url=login_url,
            redirect_url=redirect_url,
            raise_exception=raise_exception,
            message=message,
        )
        if view_func is not None and callable(view_func):
            return dec(view_func)
        return dec

    return decorator_factory


# Raccourcis par rôle applicatif
proprietaire_required = _create_role_decorator(UserRoleEnum.PROPRIETAIRE)
responsable_pharmacie_required = _create_role_decorator(
    UserRoleEnum.RESPONSABLE_PHARMACIE
)
vendeur_pharmacie_required = _create_role_decorator(
    UserRoleEnum.VENDEUR_PHARMACIE
)
pharmacy_access_required = _create_role_decorator(
    UserRoleEnum.VENDEUR_PHARMACIE
)  # Responsable hérite du Vendeur
caissier_required = _create_role_decorator(UserRoleEnum.CAISSIER)
agent_accueil_required = _create_role_decorator(UserRoleEnum.AGENT_ACCUEIL)
personnel_medical_required = _create_role_decorator(
    UserRoleEnum.PERSONNEL_MEDICAL
)
patient_management_required = _create_role_decorator(
    UserRoleEnum.AGENT_ACCUEIL,
    UserRoleEnum.PERSONNEL_MEDICAL,
)

__all__ = [
    "agent_accueil_required",
    "caissier_required",
    "patient_management_required",
    "personnel_medical_required",
    "pharmacy_access_required",
    "proprietaire_required",
    "responsable_pharmacie_required",
    "role_required",
    "vendeur_pharmacie_required",
]

