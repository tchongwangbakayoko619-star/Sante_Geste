"""Service de gestion et mise à jour de profil utilisateur et profil médical."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from django.db import transaction

from apps.users.models import MedicalProfile

if TYPE_CHECKING:
    from apps.users.models import User


@transaction.atomic
def update_user_profile(
    user: User,
    first_name: str | None = None,
    last_name: str | None = None,
    telephone: str | None = None,
    avatar: Any = None,
) -> User:
    """Met à jour les informations du profil utilisateur de manière atomique."""
    update_fields = ["updated_at"]

    if first_name is not None:
        user.first_name = first_name.strip()
        update_fields.append("first_name")

    if last_name is not None:
        user.last_name = last_name.strip()
        update_fields.append("last_name")

    if telephone is not None:
        user.telephone = telephone.strip()
        update_fields.append("telephone")

    if avatar is not None:
        user.avatar = avatar
        update_fields.append("avatar")

    user.full_clean(exclude=["password"])
    user.save(update_fields=update_fields)
    return user


@transaction.atomic
def update_medical_profile(
    user: User,
    specialite: str | None = None,
    numero_ordre: str | None = None,
) -> MedicalProfile:
    """Met à jour ou crée le profil médical d'un utilisateur du personnel médical."""
    profile, _ = MedicalProfile.objects.get_or_create(user=user)
    update_fields = ["updated_at"]

    if specialite is not None:
        profile.specialite = specialite.strip()
        update_fields.append("specialite")

    if numero_ordre is not None:
        profile.numero_ordre = numero_ordre.strip()
        update_fields.append("numero_ordre")

    profile.full_clean()
    profile.save(update_fields=update_fields)
    return profile
