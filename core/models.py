"""Core framework base models."""

import uuid
from typing import Any

from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """Modèle abstrait de base : id UUID pour tous les modèles du projet."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(BaseModel):
    """BaseModel + horodatage created_at/updated_at."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """Custom QuerySet supporting soft deletion and restoration."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Perform bulk soft delete on queryset."""
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Permanently delete queryset from database."""
        return super().delete()

    def alive(self) -> models.QuerySet:
        """Filter non-deleted records."""
        return self.filter(is_deleted=False)

    def dead(self) -> models.QuerySet:
        """Filter soft-deleted records."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Default Manager filtering out soft-deleted objects."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return non-deleted objects by default."""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def all_with_deleted(self) -> SoftDeleteQuerySet:
        """Return all objects including soft-deleted ones."""
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self) -> SoftDeleteQuerySet:
        """Return only soft-deleted objects."""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=True)


class SoftDeleteModel(TimeStampedModel):
    """Modèle abstrait pour la suppression logique (Soft Delete)."""

    is_deleted = models.BooleanField(
        default=False,
        verbose_name="Supprimé (Soft delete)",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de suppression",
    )

    objects: SoftDeleteManager = SoftDeleteManager()
    all_objects: models.Manager = models.Manager()

    class Meta:
        abstract = True

    def delete(
        self,
        using: Any = None,
        keep_parents: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        """Perform soft delete by marking is_deleted=True."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self) -> None:
        """Restore a soft-deleted instance."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Permanently delete instance from database."""
        return super().delete()
