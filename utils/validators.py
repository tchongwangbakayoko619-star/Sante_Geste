"""Generic reusable validators for SanteGeste."""

import phonenumbers
from django.core.exceptions import ValidationError
from phonenumbers.phonenumberutil import NumberParseException


def validate_phone_number(value: str, default_region: str = "CM") -> None:
    """Validate a phone number string using the phonenumbers library.

    Args:
        value (str): Raw phone number string to validate.
        default_region (str, optional): Default ISO 2-letter country code. Defaults to "CM".

    Raises:
        ValidationError: If the phone number is invalid or unparseable.
    """
    if not value:
        return

    try:
        parsed_number = phonenumbers.parse(value, default_region)
        if not phonenumbers.is_valid_number(parsed_number):
            raise ValidationError(
                f"Le numéro de téléphone '{value}' n'est pas un numéro valide.",
                code="invalid_phone_number",
            )
    except NumberParseException as exc:
        raise ValidationError(
            f"Impossible d'analyser le numéro de téléphone '{value}'.",
            code="unparseable_phone_number",
        ) from exc


def format_phone_number(value: str, default_region: str = "CM") -> str:
    """Format a phone number to international E.164 format (e.g. +237612345678).

    Args:
        value (str): Raw phone number.
        default_region (str, optional): Default ISO country code. Defaults to "CM".

    Returns:
        str: Formatted phone number in E.164 format or original string if invalid.
    """
    if not value:
        return value
    try:
        parsed_number = phonenumbers.parse(value, default_region)
        if phonenumbers.is_valid_number(parsed_number):
            return phonenumbers.format_number(
                parsed_number,
                phonenumbers.PhoneNumberFormat.E164,
            )
    except NumberParseException:
        pass
    return value
