"""Tâches d'arrière-plan Celery pour l'application users de SantéGeste."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.models import OTP

from utils.email import (
    send_otp_email_helper,
    send_security_alert_email_helper,
    send_welcome_email_helper,
)

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_otp_email_task(
    self: Any, user_id: str, raw_code: str, purpose: str, token: str = ""
) -> bool:
    """Envoie de manière asynchrone un e-mail contenant le code OTP à un utilisateur."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("Impossible d'envoyer l'OTP: Utilisateur ID %s introuvable.", user_id)
        return False

    name = user.full_name or user.email
    try:
        return send_otp_email_helper(user.email, name, raw_code, purpose, token=token)
    except Exception as exc:
        logger.warning("Échec de l'envoi de l'OTP à %s: %s. Nouvelle tentative...", user.email, exc)
        raise self.retry(exc=exc)



@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email_task(self: Any, user_id: str) -> bool:
    """Envoie un e-mail de bienvenue après l'activation réussie du compte."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("Impossible d'envoyer l'e-mail de bienvenue: Utilisateur ID %s introuvable.", user_id)
        return False

    name = user.full_name or user.email
    try:
        return send_welcome_email_helper(user.email, name)
    except Exception as exc:
        logger.warning("Échec d'envoi e-mail de bienvenue à %s: %s. Re-essai...", user.email, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_changed_notification_task(self: Any, user_id: str) -> bool:
    """Alerte de sécurité envoyée lorsque le mot de passe est modifié."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("Alerte mot de passe échouée: Utilisateur ID %s introuvable.", user_id)
        return False

    name = user.full_name or user.email
    try:
        return send_security_alert_email_helper(user.email, name, "Modification du mot de passe")
    except Exception as exc:
        logger.warning("Échec d'envoi alerte mot de passe à %s: %s.", user.email, exc)
        raise self.retry(exc=exc)



@shared_task
def cleanup_expired_otps_task() -> int:
    """Tâche périodique de nettoyage des codes OTP expirés ou déjà utilisés."""
    now = timezone.now()
    deleted_count, _ = OTP.objects.filter(expires_at__lt=now).delete()
    deleted_used, _ = OTP.objects.filter(is_used=True).delete()
    total_deleted = deleted_count + deleted_used
    logger.info("Nettoyage BDD Celery: %d enregistrements OTP expirés/utilisés supprimés.", total_deleted)
    return total_deleted

