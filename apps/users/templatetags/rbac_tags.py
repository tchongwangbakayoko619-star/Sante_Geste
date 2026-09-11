"""Filtres et tags de gabarit pour le contrôle d'accès basé sur les rôles (RBAC)."""

from __future__ import annotations

from typing import Any

from django import template

from apps.users.services.rbac import (
    check_user_roles,
    has_all_roles as rbac_has_all_roles,
    has_role as rbac_has_role,
)

register = template.Library()


def _parse_role_args(value: Any) -> list[str]:
    """Parse une liste, un tuple ou une chaîne séparée par des virgules ou espaces."""
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if item]
    if isinstance(value, str):
        # Supporte "role1, role2" ou "role1 role2"
        raw_list = value.replace(",", " ").split()
        return [item.strip() for item in raw_list if item.strip()]
    return [str(value)]


@register.filter(name="has_role")
def has_role(user: Any, role: str) -> bool:
    """Filtre de gabarit vérifiant si l'utilisateur possède un rôle donné.

    Utilisation:
        {% if request.user|has_role:"proprietaire" %}
            ...
        {% endif %}
    """
    if not role or not user:
        return False
    try:
        return rbac_has_role(user, role)
    except ValueError:
        return False


@register.filter(name="has_any_role")
def has_any_role(user: Any, roles: Any) -> bool:
    """Filtre de gabarit vérifiant si l'utilisateur possède au moins un des rôles listés.

    Utilisation:
        {% if request.user|has_any_role:"agent_accueil,personnel_medical" %}
            ...
        {% endif %}
    """
    parsed = _parse_role_args(roles)
    if not parsed or not user:
        return False
    try:
        return check_user_roles(user, parsed, require_all=False)
    except ValueError:
        return False


@register.filter(name="has_all_roles")
def has_all_roles(user: Any, roles: Any) -> bool:
    """Filtre de gabarit vérifiant si l'utilisateur possède tous les rôles listés.

    Utilisation:
        {% if request.user|has_all_roles:"responsable_pharmacie,vendeur_pharmacie" %}
            ...
        {% endif %}
    """
    parsed = _parse_role_args(roles)
    if not parsed or not user:
        return False
    try:
        return check_user_roles(user, parsed, require_all=True)
    except ValueError:
        return False


@register.simple_tag(name="user_has_role")
def user_has_role(user: Any, *roles: str) -> bool:
    """Tag simple vérifiant si l'utilisateur a au moins un des rôles passés en arguments.

    Utilisation:
        {% user_has_role request.user "proprietaire" "personnel_medical" as can_access %}
    """
    if not roles or not user:
        return False
    try:
        return rbac_has_role(user, *roles)
    except ValueError:
        return False


@register.simple_tag(name="user_has_all_roles")
def user_has_all_roles(user: Any, *roles: str) -> bool:
    """Tag simple vérifiant si l'utilisateur possède l'intégralité des rôles passés en arguments.

    Utilisation:
        {% user_has_all_roles request.user "responsable_pharmacie" "caissier" as has_both %}
    """
    if not roles or not user:
        return False
    try:
        return rbac_has_all_roles(user, *roles)
    except ValueError:
        return False

