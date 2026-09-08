import re

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


_CLEAN_SEPARATORS_REGEX = re.compile(r"[\s\-\(\).]+")
_HAS_LETTERS_REGEX = re.compile(r"[a-zA-Z]")
_ALLOWED_CHARS_REGEX = re.compile(r"^[\d\s+\-().]+$")


def normalize_phone_number(
    value: str,
    default_region: str | None = None,
) -> str:
    """Analyse et normalise un numéro de téléphone au format E.164.

    Prend en charge le plan de numérotation camerounais (exactement 9 chiffres
    pour les appels locaux : mobile débutant par 6, fixe Camtel débutant par 2 ou 3)
    ainsi que les formats internationaux (+237...).

    Args:
        value: Chaîne brute du numéro de téléphone. Peut inclure un préfixe
            international (ex: "+237 699 99 99 99") ou un numéro local sans
            préfixe (ex: "699999999"), auquel cas `default_region` est
            utilisé pour le résoudre.
        default_region: Code pays ISO 3166-1 alpha-2 utilisé pour analyser
            les numéros sans préfixe international. S'appuie sur
            `settings.DEFAULT_PHONE_REGION` si non fourni.

    Returns:
        Le numéro de téléphone formaté en E.164 (ex: "+237699999999"),
        ou la valeur d'origine inchangée si elle est vide/blanche.

    Raises:
        ValidationError: Si le numéro contient des lettres, des caractères
            interdits, n'a pas la bonne longueur (9 chiffres au Cameroun) ou
            ne commence pas par le bon préfixe (6 pour mobile, 2 ou 3 pour fixe).
    """
    if not value:
        return value

    # Rejeter explicitement toute présence de lettres dans le numéro
    if _HAS_LETTERS_REGEX.search(value):
        raise ValidationError(
            _("Le numéro de téléphone ne doit pas contenir de lettres."),
            code="phone_number_contains_letters",
        )

    # Rejeter les caractères interdits (uniquement chiffres, +, espaces, tirets, parenthèses et points)
    if not _ALLOWED_CHARS_REGEX.match(value):
        raise ValidationError(
            _("Saisissez un numéro de téléphone valide (ex: +237 6XX XX XX XX)."),
            code="invalid_phone_characters",
        )

    cleaned = _CLEAN_SEPARATORS_REGEX.sub("", value.strip())
    region = default_region or getattr(settings, "DEFAULT_PHONE_REGION", "CM")

    is_cameroon = False
    national_number = ""

    if cleaned.startswith("+237"):
        is_cameroon = True
        national_number = cleaned[4:]
    elif cleaned.startswith("00237"):
        is_cameroon = True
        national_number = cleaned[5:]
    elif cleaned.startswith("237") and len(cleaned) == 12:
        is_cameroon = True
        national_number = cleaned[3:]
    elif not cleaned.startswith("+") and region == "CM":
        is_cameroon = True
        national_number = cleaned

    if is_cameroon:
        if not national_number.isdigit():
            raise ValidationError(
                _("Saisissez un numéro de téléphone valide (ex: +237 6XX XX XX XX)."),
                code="invalid_phone_number",
            )
        if len(national_number) != 9:
            raise ValidationError(
                _(
                    "Le format d'un numéro de téléphone au Cameroun comporte exactement 9 chiffres "
                    "(ex: 6XX XX XX XX ou +237 6XX XX XX XX)."
                ),
                code="invalid_cameroon_phone_length",
            )
        if national_number[0] not in ("2", "3", "6"):
            raise ValidationError(
                _(
                    "Au Cameroun, le numéro doit commencer par 6 (mobile), "
                    "ou par 2 ou 3 (téléphone fixe Camtel)."
                ),
                code="invalid_cameroon_phone_prefix",
            )
        return f"+237{national_number}"

    # Numéro international hors Cameroun (ou avec autre indicatif)
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError(
            _("Saisissez un numéro de téléphone valide (ex: +237 6XX XX XX XX)."),
            code="unparseable_phone_number",
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(
            _("Saisissez un numéro de téléphone valide (ex: +237 6XX XX XX XX)."),
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
