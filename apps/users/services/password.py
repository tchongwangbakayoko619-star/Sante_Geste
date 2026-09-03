"""Service de demande et confirmation de réinitialisation de mot de passe."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.users.services.otp import request_otp, verify_otp_by_token
from utils.enums import OTPPurposeEnum

if TYPE_CHECKING:
    from apps.users.models import User

User = get_user_model()


class PasswordResetError(ValueError):
    """Exception levée en cas d'erreur de réinitialisation de mot de passe."""


def request_password_reset(email: str) -> tuple[User | None, str | None, str | None]:
    """Traite une demande de mot de passe oublié (anti-énumération: pas d'erreur si email inexistant).

    Returns:
        tuple[User | None, str | None, str | None]: (user, raw_code, signed_token) ou (None, None, None)
    """
    user = User.objects.get_by_email(email)
    if not user or not user.is_active:
        # Anti-énumération : retourne silencieusement None sans lever d'erreur
        return None, None, None

    _, raw_code, signed_token = request_otp(user, OTPPurposeEnum.PASSWORD_RESET)
    return user, raw_code, signed_token



def verify_password_reset_otp(signed_token: str, raw_code: str) -> bool:
    """Vérifie le code OTP de réinitialisation de mot de passe sous verrouillage BDD."""
    return verify_otp_by_token(signed_token, raw_code, OTPPurposeEnum.PASSWORD_RESET)


@transaction.atomic
def confirm_password_reset(
    signed_token: str, raw_code: str | None, new_password: str
) -> bool:
    """Met à jour le mot de passe de l'utilisateur après validation de l'OTP."""
    from utils.otp import validate_otp_token

    # 1. Validation du jeton et extraction de l'utilisateur
    payload = validate_otp_token(signed_token, OTPPurposeEnum.PASSWORD_RESET)
    user_id = payload["user_id"]

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist as err:
        msg = _("Compte utilisateur introuvable ou désactivé.")
        raise PasswordResetError(msg) from err

    # 2. Validation de la complexité du nouveau mot de passe
    validate_password(new_password, user=user)

    # 3. Vérification atomique de l'OTP si un code brut est fourni
    if raw_code:
        is_valid = verify_otp_by_token(signed_token, raw_code, OTPPurposeEnum.PASSWORD_RESET)
        if not is_valid:
            msg = _("Code de vérification invalide ou expiré.")
            raise PasswordResetError(msg)

    # 4. Enregistrement du nouveau mot de passe haché
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    # Invalidation de tous les anciens codes OTP de réinitialisation pour cet utilisateur
    from apps.users.models import OTP
    from django.utils import timezone

    OTP.objects.filter(
        user=user,
        purpose=OTPPurposeEnum.PASSWORD_RESET,
        is_used=False,
    ).update(is_used=True, used_at=timezone.now())

    from apps.users.tasks import send_password_changed_notification_task

    transaction.on_commit(
        lambda: send_password_changed_notification_task.delay(str(user.id))
    )

    return True



