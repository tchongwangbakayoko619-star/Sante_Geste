"""Service d'inscription d'utilisateur et création de profil pour l'application users."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.models import OTP, MedicalProfile
from utils.constants.otp import OTP_VALIDITY_MINUTES
from utils.enums import OTPPurposeEnum
from utils.otp import (
    OtpTokenError,
    OtpTokenExpiredError,
    check_cooldown,
    create_otp_token,
    generate_otp_code,
    hash_otp_code,
    set_cooldown,
)


User = get_user_model()


class RegistrationCooldownError(ValueError):
    """Exception levée lorsqu'une demande d'OTP est effectuée pendant un délai d'attente (cooldown)."""


@transaction.atomic
def register_user(
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    telephone: str = "",
    is_personnel_medical: bool = False,
    specialite: str = "",
    numero_ordre: str = "",
    avatar: Any = None,
) -> tuple[User, str, str]:
    """Crée un utilisateur de manière atomique, génère son profil médical si applicable et émet un OTP.

    Returns:
        tuple[User, str, str]: (utilisateur_créé, code_otp_en_clair, jeton_signé_otp)
    """
    # 1. Création de l'utilisateur
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        telephone=telephone,
        is_personnel_medical=is_personnel_medical,
        is_active=False,
        is_verified=False,
        avatar=avatar,
    )

    # 2. Création automatique du profil médical si la personne est du personnel médical
    if is_personnel_medical:
        MedicalProfile.objects.create(
            user=user,
            specialite=specialite,
            numero_ordre=numero_ordre,
        )

    # 3. Génération et émission du code OTP d'activation/vérification
    purpose = OTPPurposeEnum.REGISTRATION
    is_on_cooldown, remaining = check_cooldown(user.id, purpose)
    if is_on_cooldown:
        msg = _(
            "Veuillez attendre %(seconds)s secondes avant de demander un nouveau code."
        ) % {"seconds": remaining}
        raise RegistrationCooldownError(msg)

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

    return user, raw_code, signed_token


@transaction.atomic
def confirm_registration_otp(
    signed_token: str,
    user_id: str,
    raw_code: str,
) -> tuple[bool, User | None]:
    """Vérifie le code OTP d'inscription, active le compte utilisateur et déclenche l'e-mail de bienvenue."""
    from apps.users.services.otp import verify_otp_by_token, verify_otp_by_user

    purpose = OTPPurposeEnum.REGISTRATION
    is_valid = False
    user: User | None = None

    if signed_token:
        from utils.otp import validate_otp_token, verify_otp_with_lock

        try:
            payload = validate_otp_token(signed_token, purpose)
            token_user_id = payload.get("user_id")
            otp_id = payload.get("otp_id")
            if verify_otp_with_lock(otp_id, raw_code):
                is_valid = True
                if not user_id and token_user_id:
                    user_id = token_user_id
        except (OtpTokenError, OtpTokenExpiredError, ValueError):
            is_valid = False

    if not is_valid and not signed_token and user_id:
        try:
            user_obj = User.objects.get(id=user_id)
            if verify_otp_by_user(user_obj, raw_code, purpose):
                is_valid = True
                user = user_obj
        except User.DoesNotExist:
            pass

    if is_valid:
        if not user and user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                user = None

        if user:
            user.is_active = True
            user.is_verified = True
            user.save(update_fields=["is_active", "is_verified", "updated_at"])

            from apps.users.tasks import send_welcome_email_task

            transaction.on_commit(lambda: send_welcome_email_task.delay(str(user.id)))

        return True, user

    return False, None
