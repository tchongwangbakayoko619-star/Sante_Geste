"""QuerySets personnalisés pour les modèles du noyau core."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone



class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet fournissant les opérations de suppression logique (soft delete)."""

    def delete(self, user: Any | None = None) -> int:
        """Effectue une suppression logique en masse sur le QuerySet avec traçabilité d'auteur."""
        update_kwargs: dict[str, Any] = {
            "is_deleted": True,
            "deleted_at": timezone.now(),
        }
        if user is not None:
            update_kwargs["updated_by"] = user

        return self.update(**update_kwargs)

    def restore(self, user: Any | None = None) -> int:
        """Restaure tous les enregistrements supprimés logiquement dans le QuerySet."""
        update_kwargs: dict[str, Any] = {
            "is_deleted": False,
            "deleted_at": None,
        }
        if user is not None:
            update_kwargs["updated_by"] = user

        return self.update(**update_kwargs)


    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Supprime définitivement de la base de données tous les enregistrements du QuerySet."""
        return super().delete()

    def alive(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements actifs (non supprimés)."""
        return self.filter(is_deleted=False)

    def dead(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements supprimés logiquement."""
        return self.filter(is_deleted=True)
