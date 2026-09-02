"""Managers personnalisés pour les modèles du noyau core."""

from __future__ import annotations

from django.db import models

from .querysets import SoftDeleteQuerySet


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Manager retournant uniquement les enregistrements actifs par défaut."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements actifs (is_deleted=False)."""
        return super().get_queryset().filter(is_deleted=False)

    def all_with_deleted(self) -> SoftDeleteQuerySet:
        """Retourne tous les enregistrements, y compris ceux supprimés logiquement."""
        return super().get_queryset()

    def deleted_only(self) -> SoftDeleteQuerySet:
        """Retourne uniquement les enregistrements supprimés logiquement."""
        return super().get_queryset().filter(is_deleted=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Manager retournant tous les enregistrements (actifs et supprimés)."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Retourne tous les enregistrements sans filtrer sur is_deleted."""
        return super().get_queryset()
