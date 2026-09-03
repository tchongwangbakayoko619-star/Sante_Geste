"""Tests unitaires pour les validateurs d'upload de fichiers."""

from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ValidationError

from utils.validators import validate_image_extension, validate_image_file_size


def test_validate_image_file_size_valid() -> None:
    """Vérifie qu'un fichier de 2 Mo est accepté."""
    mock_file = MagicMock()
    mock_file.size = 2 * 1024 * 1024  # 2 MB
    # Ne doit levée aucune exception
    validate_image_file_size(mock_file)


def test_validate_image_file_size_exceeded() -> None:
    """Vérifie le rejet d'un fichier dépassant 5 Mo."""
    mock_file = MagicMock()
    mock_file.size = 6 * 1024 * 1024  # 6 MB
    with pytest.raises(ValidationError) as exc_info:
        validate_image_file_size(mock_file)
    assert "ne doit pas dépasser 5 Mo" in str(exc_info.value)


def test_validate_image_extension_valid() -> None:
    """Vérifie que les extensions d'image autorisées (png, jpg, webp) sont acceptées."""
    for filename in ["profile.jpg", "avatar.PNG", "image.webp"]:
        mock_file = MagicMock()
        mock_file.name = filename
        validate_image_extension(mock_file)


def test_validate_image_extension_invalid() -> None:
    """Vérifie le rejet des extensions non autorisées (exe, pdf, html)."""
    for filename in ["malicious.exe", "document.pdf", "script.php"]:
        mock_file = MagicMock()
        mock_file.name = filename
        with pytest.raises(ValidationError) as exc_info:
            validate_image_extension(mock_file)
        assert "Format de fichier non pris en charge" in str(exc_info.value)

