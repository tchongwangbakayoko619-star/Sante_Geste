"""QuerySets personnalisés pour les modèles du noyau core."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet fournissant les opérations de suppression logique (soft delete)."""

    def delete(self) -> int:
        """Effectue une suppression logique en masse sur le QuerySet."""
        return self.update(
            is_deleted=True,
            deleted_at=timezone.now(),
        )

    def restore(self) -> int:
        """Restaure tous les enregistrements supprimés logiquement dans le QuerySet."""
        return self.update(
            is_deleted=False,
            deleted_at=None,
        )

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Supprime définitivement de la base de données tous les enregistrements du QuerySet."""
        return super().delete()

    def alive(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements actifs (non supprimés)."""
        return self.filter(is_deleted=False)

    def dead(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements supprimés logiquement."""
        return self.filter(is_deleted=True)
