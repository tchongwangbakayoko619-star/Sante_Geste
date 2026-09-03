"""Validators pour les fichiers médias et uploads de SantéGeste."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_image_extension(file: Any) -> None:
    """Vérifie que l'extension du fichier fait partie des formats d'image autorisés (jpg, jpeg, png, webp)."""
    if file and hasattr(file, "name"):
        import os

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            msg = _(
                "Format de fichier non pris en charge. Extension reçue : '%(ext)s'. Formats autorisés : %(allowed)s."
            ) % {"ext": ext, "allowed": allowed}
            raise ValidationError(msg)


def validate_image_file_size(file: Any) -> None:
    """Vérifie que la taille d'un fichier image ne dépasse pas la limite maximale autorisée (5 Mo)."""
    max_size_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 5)
    max_size_bytes = max_size_mb * 1024 * 1024

    if file and hasattr(file, "size") and file.size > max_size_bytes:
        msg = _(
            "La taille du fichier ne doit pas dépasser %(max)s Mo (taille actuelle: %(size).2f Mo)."
        ) % {
            "max": max_size_mb,
            "size": file.size / (1024 * 1024),
        }
        raise ValidationError(msg)


def validate_avatar_image(file: Any) -> None:
    """Combine la validation de taille et d'extension pour les photos de profil."""
    validate_image_extension(file)
    validate_image_file_size(file)

