"""Utilitaires de validation et de normalisation des numéros de téléphone."""

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def normalize_phone_number(
    value: str,
    default_region: str | None = None,
) -> str:
    """Analyse et normalise un numéro de téléphone au format E.164.

    Args:
        value: Chaîne brute du numéro de téléphone. Peut inclure un préfixe
            international (ex: "+237699999999") ou un numéro local sans
            préfixe (ex: "699999999"), auquel cas `default_region` est
            utilisé pour le résoudre.
        default_region: Code pays ISO 3166-1 alpha-2 utilisé pour analyser
            les numéros sans préfixe international. S'appuie sur
            `settings.DEFAULT_PHONE_REGION` si non fourni.

    Returns:
        Le numéro de téléphone formaté en E.164 (ex: "+237699999999"),
        ou la valeur d'origine inchangée si elle est vide/blanche.

    Raises:
        ValidationError: Si le numéro ne peut pas être analysé ou n'est pas un
            numéro de téléphone valide pour la région résolue.
    """
    if not value:
        return value

    region = default_region or settings.DEFAULT_PHONE_REGION

    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError(
            _("Saisissez un numéro de téléphone valide (ex: +237699999999)."),
            code="unparseable_phone_number",
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(
            _("Saisissez un numéro de téléphone valide (ex: +237699999999)."),
            code="invalid_phone_number",
        )

    return phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )


def validate_phone_number(
    value: str,
    default_region: str | None = None,
) -> None:
    """Valide un numéro de téléphone sans modifier sa valeur.

    Args:
        value: Chaîne brute du numéro de téléphone à valider.
        default_region: Code pays ISO 3166-1 alpha-2 utilisé pour analyser
            les numéros sans préfixe international. S'appuie sur
            `settings.DEFAULT_PHONE_REGION` si non fourni.

    Raises:
        ValidationError: Si le numéro ne peut pas être analysé ou n'est pas un
            numéro de téléphone valide pour la région résolue.
    """
    if not value:
        return
    normalize_phone_number(value, default_region)
