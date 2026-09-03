"""Service de gestion, génération et vérification atomique des OTP pour l'application users."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.models import OTP
from utils.constants.otp import OTP_VALIDITY_MINUTES
from utils.otp import (
    OtpTokenError,
    check_cooldown,
    create_otp_token,
    generate_otp_code,
    hash_otp_code,
    set_cooldown,
    validate_otp_token,
    verify_otp_with_lock,
)

if TYPE_CHECKING:
    from apps.users.models import User


class OtpCooldownError(ValueError):
    """Exception levée lorsqu'une demande d'OTP est soumise pendant le délai de cooldown."""


@transaction.atomic
def request_otp(user: User, purpose: str) -> tuple[OTP, str, str]:
    """Génère un nouvel OTP pour un utilisateur et un objectif donnés (registration, reset_password, 2fa).

    Returns:
        tuple[OTP, str, str]: (instance_otp, code_en_clair, jeton_signé)
    """
    is_on_cooldown, remaining = check_cooldown(user.id, purpose)
    if is_on_cooldown:
        msg = _(
            "Veuillez attendre %(seconds)s secondes avant de demander un nouveau code."
        ) % {"seconds": remaining}
        raise OtpCooldownError(msg)

    # Invalidation des anciens codes OTP non consommés pour le même objectif
    OTP.objects.filter(user=user, purpose=purpose, is_used=False).update(
        is_used=True, used_at=timezone.now()
    )

    raw_code = generate_otp_code()
    code_hash = hash_otp_code(raw_code)
    expires_at = timezone.now() + timezone.timedelta(minutes=OTP_VALIDITY_MINUTES)

    otp = OTP.objects.create(
        user=user,
        code_hash=code_hash,
        purpose=purpose,
        expires_at=expires_at,
    )

    set_cooldown(user.id, purpose)
    signed_token = create_otp_token(otp.id, user.id, purpose)

    from apps.users.tasks import send_otp_email_task

    transaction.on_commit(
        lambda: send_otp_email_task.delay(str(user.id), raw_code, purpose, signed_token)
    )

    return otp, raw_code, signed_token


def verify_otp_by_token(signed_token: str, raw_code: str, purpose: str) -> bool:
    """Valide le jeton signé d'OTP et vérifie le code soumis sous verrouillage anti-concurrence."""
    payload = validate_otp_token(signed_token, purpose)
    otp_id = payload["otp_id"]
    return verify_otp_with_lock(otp_id, raw_code)


@transaction.atomic
def verify_otp_by_user(user: User, raw_code: str, purpose: str) -> bool:
    """Vérifie le dernier OTP actif pour un utilisateur sous verrouillage pessimiste."""
    now = timezone.now()
    otp_obj = (
        OTP.objects.select_for_update()
        .filter(user=user, purpose=purpose, is_used=False, expires_at__gt=now)
        .order_by("-created_at")
        .first()
    )
    if not otp_obj or not otp_obj.is_valid():
        return False

    if otp_obj.verify_code(raw_code):
        otp_obj.mark_as_used()
        return True

    otp_obj.increment_attempts()
    return False


