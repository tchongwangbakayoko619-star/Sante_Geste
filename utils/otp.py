"""Utilitaires de génération, hachage, signature et cooldown des codes OTP."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.signing import BadSignature
from django.core.signing import SignatureExpired
from django.core.signing import TimestampSigner
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from uuid import UUID

_TOKEN_SEP = ":"  # noqa: S105


class OtpTokenError(ValueError):
    """Exception levée lorsqu'un jeton OTP ne peut pas être utilisé."""


class OtpTokenExpiredError(OtpTokenError):
    """Exception levée lorsqu'un jeton OTP a expiré."""


def generate_otp_code(length: int = 6) -> str:
    """Génère un code OTP numérique cryptographiquement sécurisé du nombre de chiffres demandé."""
    length = max(length, 4)
    upper_bound = 10**length
    return f"{secrets.randbelow(upper_bound):0{length}d}"


def hash_otp_code(code: str) -> str:
    """Hache un code OTP en clair à l'aide du hacheur de mots de passe de Django."""
    return make_password(code)


def verify_otp_code(code: str, hashed: str) -> bool:
    """Vérifie qu'un code OTP en clair correspond au hachage stocké."""
    if not hashed:
        return False
    return check_password(code, hashed)


def create_otp_token(otp_id: str | UUID, user_id: str | UUID, purpose: str) -> str:
    """Crée un jeton horodaté et signé cryptographiquement pour l'OTP."""
    payload = _TOKEN_SEP.join([str(otp_id), str(user_id), purpose])
    signer = TimestampSigner(salt=f"otp-token-{purpose}")
    return signer.sign(payload)


def validate_otp_token(signed_token: str, purpose: str) -> dict[str, str]:
    """Valide et déchiffre un jeton d'OTP signé."""
    max_age = getattr(settings, "OTP_VALID_MINUTES", 10) * 60
    signer = TimestampSigner(salt=f"otp-token-{purpose}")

    try:
        payload = signer.unsign(signed_token, max_age=max_age)
    except SignatureExpired as err:
        msg = _("Le code de vérification a expiré.")
        raise OtpTokenExpiredError(msg) from err
    except BadSignature as err:
        msg = _("Le lien de vérification est invalide.")
        raise OtpTokenError(msg) from err

    parts = payload.split(_TOKEN_SEP)
    if len(parts) != 3:  # noqa: PLR2004
        msg = _("Le lien de vérification est invalide.")
        raise OtpTokenError(msg)

    otp_id, user_id, embedded_purpose = parts
    if embedded_purpose != purpose:
        msg = _("Ce code ne correspond pas à cette opération.")
        raise OtpTokenError(msg)

    return {"otp_id": otp_id, "user_id": user_id, "purpose": purpose}


def verify_otp_with_lock(otp_id: str | UUID, raw_code: str) -> bool:
    """Vérifie un code OTP de manière atomique avec verrouillage pessimiste anti-concurrence."""
    from django.db import transaction
    from apps.users.models import OTP

    with transaction.atomic():
        try:
            otp = OTP.objects.select_for_update().get(id=otp_id)
        except OTP.DoesNotExist:
            return False

        if not otp.is_valid():
            return False

        if not otp.verify_code(raw_code):
            otp.increment_attempts()
            return False

        otp.mark_as_used()
        return True



def _cooldown_key(user_id: str | UUID, purpose: str) -> str:
    """Génère la clé de cache pour le cooldown des demandes d'OTP."""
    return f"otp_cooldown:{purpose}:{str(user_id)}"


def check_cooldown(user_id: str | UUID, purpose: str) -> tuple[bool, int]:
    """Vérifie si un délai d'attente (cooldown) est actif pour cet utilisateur et cet objectif."""
    key = _cooldown_key(user_id, purpose)
    remaining: Any = cache.ttl(key) if hasattr(cache, "ttl") else None
    if remaining is not None and remaining > 0:
        return True, int(remaining)
    if cache.get(key):
        return True, int(getattr(settings, "OTP_REQUEST_COOLDOWN_SECONDS", 60))
    return False, 0


def set_cooldown(user_id: str | UUID, purpose: str) -> None:
    """Définit un délai d'attente (cooldown) dans le cache pour cet utilisateur et cet objectif."""
    timeout = int(getattr(settings, "OTP_REQUEST_COOLDOWN_SECONDS", 60))
    cache.set(_cooldown_key(user_id, purpose), value=True, timeout=timeout)
