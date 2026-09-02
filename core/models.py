"""Modèles abstraits du noyau framework SantéGeste."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import AllObjectsManager
from .managers import SoftDeleteManager

if TYPE_CHECKING:
    from apps.users.models import User


class BaseModel(models.Model):
    """Modèle abstrait de base partagé par les modèles concrets.

    Fournit :
    - Clé primaire UUID v4
    - Horodatage de création (indexé)
    - Horodatage de mise à jour (indexé)
    - Traçabilité d'auteur à la création (created_by)
    - Traçabilité d'auteur à la modification (updated_by)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("Identifiant unique"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Date de création"),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        verbose_name=_("Créé par"),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name=_("Date de dernière modification"),
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        verbose_name=_("Modifié par"),
    )

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.__class__.__name__} ({self.pk})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} pk={self.pk}>"

    def set_created_by(self, user: User | None) -> None:
        """Définit l'utilisateur responsable de la création de cette instance."""
        self.created_by = user

    def set_updated_by(self, user: User | None) -> None:
        """Définit l'utilisateur responsable de la modification de cette instance."""
        self.updated_by = user


class SoftDeleteModel(BaseModel):
    """Modèle abstrait fournissant la suppression logique (Soft Delete).

    Les enregistrements sont conservés en base de données et marqués comme supprimés
    au lieu d'être physiquement retirés.

    Note :
        Un champ avec unique=True reste unique sur toute la table, y compris les
        enregistrements supprimés logiquement. Si une valeur doit être réutilisable
        après suppression, utiliser une contrainte UniqueConstraint conditionnelle avec is_deleted=False.
    """

    is_deleted = models.BooleanField(
        default=False,
        verbose_name=_("Supprimé"),
        help_text=_(
            "Indique si l'enregistrement a été supprimé logiquement."
        ),
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Date de suppression"),
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(
                fields=["is_deleted", "-created_at"],
                name="%(class)s_active_created_idx",
            ),
        ]

    def soft_delete(
        self,
        user: User | None = None,
        using: str | None = None,
    ) -> None:
        """Effectue la suppression logique de cette instance."""
        if self.is_deleted:
            return

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.updated_by = user

        self.save(
            using=using,
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_by",
                "updated_at",
            ],
        )

    def restore(
        self,
        user: User | None = None,
        using: str | None = None,
    ) -> None:
        """Restaure cette instance supprimée logiquement."""
        if not self.is_deleted:
            return

        self.is_deleted = False
        self.deleted_at = None
        self.updated_by = user

        self.save(
            using=using,
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_by",
                "updated_at",
            ],
        )

    def hard_delete(
        self,
        using: str | None = None,
        keep_parents: bool = False,  # noqa: FBT001, FBT002
    ) -> tuple[int, dict[str, int]]:
        """Supprime définitivement cette instance de la base de données."""
        return super().delete(
            using=using,
            keep_parents=keep_parents,
        )
