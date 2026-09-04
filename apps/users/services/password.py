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
    signed_token: str,
    raw_code: str | None,
    new_password: str,
    *,
    reset_ticket: str | None = None,
) -> bool:
    """Met à jour le mot de passe de l'utilisateur après validation de l'OTP."""
    from django.conf import settings
    from django.utils import timezone
    from apps.users.models import OTP
    from utils.otp import validate_otp_token, validate_password_reset_ticket

    user_id = None
    otp_id = None

    if reset_ticket:
        try:
            ticket_payload = validate_password_reset_ticket(reset_ticket)
            user_id = ticket_payload["user_id"]
            otp_id = ticket_payload["otp_id"]
        except Exception as err:
            msg = _("Autorisation de réinitialisation invalide ou expirée.")
            raise PasswordResetError(msg) from err
    else:
        # 1. Validation du jeton et extraction de l'utilisateur et de l'OTP
        try:
            payload = validate_otp_token(signed_token, OTPPurposeEnum.PASSWORD_RESET)
            user_id = payload["user_id"]
            otp_id = payload["otp_id"]
        except Exception as err:
            msg = _("Code de vérification invalide ou expiré.")
            raise PasswordResetError(msg) from err

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist as err:
        msg = _("Compte utilisateur introuvable ou désactivé.")
        raise PasswordResetError(msg) from err

    # 2. Validation de la complexité du nouveau mot de passe
    validate_password(new_password, user=user)

    # 3. Vérification atomique de l'OTP sous verrouillage BDD
    try:
        otp = OTP.objects.select_for_update().get(
            id=otp_id, user=user, purpose=OTPPurposeEnum.PASSWORD_RESET
        )
    except OTP.DoesNotExist as err:
        msg = _("Code de vérification invalide ou expiré.")
        raise PasswordResetError(msg) from err

    max_age_seconds = getattr(settings, "OTP_VALID_MINUTES", 10) * 60

    if otp.is_used:
        # L'OTP a déjà été validé à l'étape 1 (flux web 2 étapes)
        # Vérification qu'il a été validé récemment
        if (
            not otp.used_at
            or (timezone.now() - otp.used_at).total_seconds() > max_age_seconds
        ):
            otp.increment_attempts()
            msg = _("Code de vérification invalide ou expiré.")
            raise PasswordResetError(msg)
        if not reset_ticket:
            if not raw_code or not otp.verify_code(raw_code):
                otp.increment_attempts()
                msg = _("Code de vérification invalide ou expiré.")
                raise PasswordResetError(msg)
    else:
        # L'OTP n'a pas encore été validé (flux direct 1 étape)
        if not raw_code or not otp.is_valid() or not otp.verify_code(raw_code):
            otp.increment_attempts()
            msg = _("Code de vérification invalide ou expiré.")
            raise PasswordResetError(msg)
        otp.mark_as_used()

    # 4. Enregistrement du nouveau mot de passe haché
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    # Invalidation définitive de tous les anciens codes OTP de réinitialisation pour cet utilisateur
    OTP.objects.filter(
        user=user,
        purpose=OTPPurposeEnum.PASSWORD_RESET,
    ).delete()

    from apps.users.tasks import send_password_changed_notification_task

    transaction.on_commit(
        lambda: send_password_changed_notification_task.delay(str(user.id))
    )

    return True
