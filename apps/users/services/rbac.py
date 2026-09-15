"""Service centralisé de contrôle d'accès basé sur les rôles (RBAC) pour SantéGeste.

Note sur les superusers :
`get_effective_roles()` accorde l'intégralité des rôles déclarés dans
`ROLE_FIELD_MAP` à un superuser actif.

Séparation des pouvoirs :
- `can_prescribe()` est une exception volontaire au bypass superuser
  (responsabilité légale et pénale stricte sur les actes médicaux).
- `can_validate_sensitive_ops()` est une exception volontaire réservée au
  propriétaire légal de l'établissement (`is_proprietaire=True`).
Toutes les autres fonctions métier reposent sur `has_role()` et bénéficient
du statut superuser via `get_effective_roles()`.

Note sur is_staff :
L'attribut `is_staff` est strictement réservé à l'accès au site d'administration
Django (/admin/) et n'interfère pas avec les rôles applicatifs de ce service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.utils.translation import gettext_lazy as _

from utils.enums import UserRoleEnum

if TYPE_CHECKING:
    from collections.abc import Iterable

    from apps.users.models import User

# Correspondance unique entre rôles applicatifs et champs booléens du modèle User
ROLE_FIELD_MAP: dict[UserRoleEnum, str] = {
    UserRoleEnum.PROPRIETAIRE: "is_proprietaire",
    UserRoleEnum.RESPONSABLE_PHARMACIE: "is_responsable_pharmacie",
    UserRoleEnum.VENDEUR_PHARMACIE: "is_vendeur_pharmacie",
    UserRoleEnum.CAISSIER: "is_caissier",
    UserRoleEnum.AGENT_ACCUEIL: "is_agent_accueil",
    UserRoleEnum.PERSONNEL_MEDICAL: "is_personnel_medical",
}

# Hiérarchie et héritage métier des rôles
# Règle : Le Responsable Pharmacie hérite automatiquement des droits du
# Vendeur Pharmacie
ROLE_INHERITANCE: dict[UserRoleEnum, set[UserRoleEnum]] = {
    UserRoleEnum.RESPONSABLE_PHARMACIE: {UserRoleEnum.VENDEUR_PHARMACIE},
}


def _is_active_authenticated_user(user: User | Any | None) -> bool:
    """Vérifie si l'utilisateur est non nul, authentifié et actif.

    Garantit qu'aucun utilisateur anonyme, None ou inactif (is_active=False)
    ne puisse accéder aux permissions RBAC.
    """
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def normalize_role(role: UserRoleEnum | str) -> UserRoleEnum:
    """Normalise une valeur de rôle (UserRoleEnum ou chaîne) en UserRoleEnum.

    Ne matche que par .value exacte pour proscrire toute ambiguïté syntaxique.
    Lève ValueError si le rôle n'est pas reconnu.
    """
    if isinstance(role, UserRoleEnum):
        return role
    if isinstance(role, str):
        try:
            return UserRoleEnum(role)
        except ValueError:
            pass
    msg = _("Le rôle '%(role)s' n'est pas un rôle valide de SantéGeste.") % {
        "role": role,
    }
    raise ValueError(msg)


def get_direct_roles(user: User | Any | None) -> set[UserRoleEnum]:
    """Retourne les rôles directement attribués (booléens à True en base).

    Ne tient pas compte de l'héritage ni du statut de superuser.
    Retourne un ensemble vide si l'utilisateur est anonyme, None ou inactif.
    """
    if not _is_active_authenticated_user(user):
        return set()

    direct_roles: set[UserRoleEnum] = set()
    for role_enum, field_name in ROLE_FIELD_MAP.items():
        if getattr(user, field_name, False):
            direct_roles.add(role_enum)

    return direct_roles


def get_effective_roles(user: User | Any | None) -> set[UserRoleEnum]:
    """Calcule l'ensemble des rôles applicables à l'utilisateur en tenant compte :

    1. Du statut actif du compte (is_active=False retourne un ensemble vide).
    2. Du statut superuser (accès global à tous les rôles de ROLE_FIELD_MAP).
    3. Des rôles directs.
    4. De l'héritage métier (RESPONSABLE_PHARMACIE -> VENDEUR_PHARMACIE).
    """
    if not _is_active_authenticated_user(user):
        return set()

    # Un superuser actif possède tous les rôles applicatifs configurés
    if getattr(user, "is_superuser", False):
        return set(ROLE_FIELD_MAP.keys())

    direct = get_direct_roles(user)
    effective = set(direct)

    for role in direct:
        if role in ROLE_INHERITANCE:
            effective.update(ROLE_INHERITANCE[role])

    return effective


def has_role(user: User | Any | None, *roles: UserRoleEnum | str) -> bool:
    """Vérifie si l'utilisateur possède AU MOINS UN des rôles spécifiés (OU logique).

    Prend en compte l'héritage des rôles et le statut superuser via
    get_effective_roles().
    """
    if not _is_active_authenticated_user(user) or not roles:
        return False

    normalized_requested = {normalize_role(r) for r in roles}
    return bool(get_effective_roles(user) & normalized_requested)


def has_all_roles(user: User | Any | None, *roles: UserRoleEnum | str) -> bool:
    """Vérifie si l'utilisateur possède TOUS les rôles spécifiés (ET logique).

    Prend en compte l'héritage des rôles et le statut superuser via
    get_effective_roles().
    """
    if not _is_active_authenticated_user(user) or not roles:
        return False

    normalized_requested = {normalize_role(r) for r in roles}
    return normalized_requested.issubset(get_effective_roles(user))


def check_user_roles(
    user: User | Any | None,
    roles: Iterable[UserRoleEnum | str],
    *,
    require_all: bool = False,
) -> bool:
    """Fonction pivot pour vérifier les rôles (CBV, FBV et tags)."""
    role_list = list(roles)
    if require_all:
        return has_all_roles(user, *role_list)
    return has_role(user, *role_list)


# -----------------------------------------------------------------------------
# Propriétés et prédicats métier transverses
# -----------------------------------------------------------------------------


def can_manage_pharmacy(user: User | Any | None) -> bool:
    """Gestion complète de la pharmacie (stocks, inventaires, commandes).

    Réservé au responsable pharmacie et au superuser.
    """
    return has_role(user, UserRoleEnum.RESPONSABLE_PHARMACIE)


def can_sell_pharmacy(user: User | Any | None) -> bool:
    """Vente de médicaments au comptoir.

    Accessible au vendeur pharmacie ET au responsable pharmacie (par héritage).
    """
    return has_role(user, UserRoleEnum.VENDEUR_PHARMACIE)


def can_manage_cash(user: User | Any | None) -> bool:
    """Gestion de caisse (ouverture session, encaissements, clôture).

    Réservé au caissier et au superuser.
    """
    return has_role(user, UserRoleEnum.CAISSIER)


def can_manage_patients(user: User | Any | None) -> bool:
    """Gestion administrative des patients et prises de rendez-vous.

    Accessible à l'agent d'accueil et au personnel médical.
    """
    return has_role(user, UserRoleEnum.AGENT_ACCUEIL, UserRoleEnum.PERSONNEL_MEDICAL)


def can_prescribe(user: User | Any | None) -> bool:
    """Prescription d'ordonnance et actes médicaux.

    STRICTEMENT réservé au personnel médical actif.
    Règle de séparation des pouvoirs : un propriétaire ou superuser n'a PAS le
    droit de prescription sauf s'il est praticien médical (is_personnel_medical=True).
    """
    if not _is_active_authenticated_user(user):
        return False
    return bool(getattr(user, "is_personnel_medical", False))


def can_validate_sensitive_ops(user: User | Any | None) -> bool:
    """Validation finale des opérations sensibles (inventaires, ajustements).

    STRICTEMENT réservé au propriétaire de l'établissement.
    Règle de séparation des pouvoirs : un superuser n'a PAS le droit de valider
    ces opérations s'il n'est pas lui-même propriétaire (is_proprietaire=True).
    """
    if not _is_active_authenticated_user(user):
        return False
    return bool(getattr(user, "is_proprietaire", False))
