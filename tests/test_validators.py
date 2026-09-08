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


def test_validate_phone_number_rejects_letters() -> None:
    """Vérifie que les numéros de téléphone contenant des lettres sont strictement rejetés."""
    from utils.phone import normalize_phone_number, validate_phone_number

    invalid_phones = [
        "1800FLOWERS",
        "+237699abc99",
        "abcdef",
        "+33 6 12 34 AB CD",
        "phone123",
    ]
    for phone in invalid_phones:
        with pytest.raises(ValidationError) as exc_info:
            validate_phone_number(phone)
        assert "lettres" in str(exc_info.value).lower() or "valide" in str(exc_info.value).lower()

        with pytest.raises(ValidationError):
            normalize_phone_number(phone)


def test_validate_phone_number_accepts_valid() -> None:
    """Vérifie que les numéros valides sans lettres sont acceptés."""
    from utils.phone import normalize_phone_number, validate_phone_number

    valid_phone = "+237699999999"
    validate_phone_number(valid_phone)
    normalized = normalize_phone_number(valid_phone)
    assert normalized == "+237699999999"


def test_cameroon_mobile_phone_formats() -> None:
    """Vérifie la validation et normalisation des mobiles camerounais (9 chiffres commençant par 6)."""
    from utils.phone import normalize_phone_number, validate_phone_number

    valid_mobiles = [
        ("699999999", "+237699999999"),
        ("6 70 12 34 56", "+237670123456"),
        ("6-80-00-11-22", "+237680001122"),
        ("+237699999999", "+237699999999"),
        ("+237 6 99 99 99 99", "+237699999999"),
        ("00237 699999999", "+237699999999"),
        ("237699999999", "+237699999999"),
    ]
    for raw, expected in valid_mobiles:
        validate_phone_number(raw)
        assert normalize_phone_number(raw) == expected


def test_cameroon_fixed_phone_formats() -> None:
    """Vérifie la validation des téléphones fixes Camtel (9 chiffres commençant par 2 ou 3)."""
    from utils.phone import normalize_phone_number, validate_phone_number

    valid_fixed = [
        ("222123456", "+237222123456"),
        ("2 22 12 34 56", "+237222123456"),
        ("+237 2 22 12 34 56", "+237222123456"),
        ("333123456", "+237333123456"),
        ("3 33 12 34 56", "+237333123456"),
        ("+237 3 33 12 34 56", "+237333123456"),
    ]
    for raw, expected in valid_fixed:
        validate_phone_number(raw)
        assert normalize_phone_number(raw) == expected


def test_cameroon_phone_invalid_length() -> None:
    """Vérifie le rejet des numéros camerounais qui ne font pas exactement 9 chiffres."""
    from utils.phone import normalize_phone_number, validate_phone_number

    invalid_lengths = [
        "69999999",       # 8 chiffres
        "6999999999",     # 10 chiffres
        "+237 699 99",    # 5 chiffres
        "+2376999999999", # 10 chiffres nationaux
    ]
    for raw in invalid_lengths:
        with pytest.raises(ValidationError) as exc_info:
            validate_phone_number(raw)
        assert "exactement 9 chiffres" in str(exc_info.value)

        with pytest.raises(ValidationError):
            normalize_phone_number(raw)


def test_cameroon_phone_invalid_prefix() -> None:
    """Vérifie le rejet des numéros camerounais ne commençant pas par 6, 2 ou 3."""
    from utils.phone import normalize_phone_number, validate_phone_number

    invalid_prefixes = [
        "700000000",       # commence par 7
        "500000000",       # commence par 5
        "123456789",       # commence par 1
        "800000000",       # commence par 8
        "+237 700 00 00 00",
        "+237 512 34 56 78",
    ]
    for raw in invalid_prefixes:
        with pytest.raises(ValidationError) as exc_info:
            validate_phone_number(raw)
        assert "commencer par 6" in str(exc_info.value)

        with pytest.raises(ValidationError):
            normalize_phone_number(raw)


